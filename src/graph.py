"""JobNewsLite 파이프라인 — 5단계(수집→선별→요약/인사이트→검수→발행) 노드 함수 모음.

LangGraph의 StateGraph 대신 Claude Agent SDK를 직접 오케스트레이션한다 — 이유는
REPORT.md "프레임워크 선택" 절 참고. 대신 각 함수를 LangGraph의 노드(node)에 대응하는
단위(입력 상태 조각을 받아 출력 상태 조각 + metrics 조각을 반환)로 나눠서, 나중에
LangGraph로 옮기더라도 이 함수들을 노드 바디로 거의 그대로 재사용할 수 있게 했다.
run.py가 이 노드들을 순서대로 호출하는 것이 LangGraph의 엣지(edge)에 해당한다.
"""

import re
from datetime import date
from pathlib import Path

import yaml

from filters.rules import passes_keyword_filter
from report import build_report_body, write_report
from schemas import RESEARCH_SCHEMA, SCORE_SCHEMA
from sdk_client import run_structured_query
from verify import apply_korean_retry_to_scores, title_language_warnings

MODEL = "claude-sonnet-5"


def load_audience(path: str | Path = "audience.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------- 1단계: 수집(Collect) ----------
# "최소 3개 이상 소스" 요건을 audience.yaml의 sources 트랙 3개로 채운다. 트랙마다
# 독립된 WebSearch/WebFetch 호출을 보내 서로 다른 채용 채널(공공기관/채용플랫폼/
# 인사뉴스)에서 수집하고, 각 트랙의 수집 건수를 metrics에 남겨 "소스가 실제로
# 기여했는지"를 증명한다(REPORT.md 소스 채택표 근거).


def _collect_prompt(audience: dict, source: dict) -> str:
    persona = audience["persona"]
    return f"""다음 조건에 맞는 채용 공고/채용 관련 뉴스를 최근 {audience['recency_days']}일 이내
기준으로 찾아줘. 이 요청은 아래 소스 트랙 전용이야 — 다른 트랙과 겹치지 않게 이 트랙
성격에 맞는 곳 위주로 검색해.

[이번 트랙] {source['label']}
{source['query_hint']}

[대상 독자] {persona['background']}
1. 정부·공공·대학: {persona['target_groups']['public']}
2. 일반기업: {persona['target_groups']['company']}

각 후보는 WebFetch로 공고/기사 원문을 실제로 열어서 본문을 확인한 것만 포함해(추측 금지).
낮은 직급이나 무관 직무는 제외해. 후보가 없으면 candidates를 빈 배열로 반환해."""


async def stage_collect(audience: dict, on_event=None) -> tuple[list[dict], dict]:
    all_candidates: list[dict] = []
    per_source_counts: dict[str, int] = {}
    errors: dict[str, str] = {}

    for source in audience["sources"]:
        if on_event:
            on_event(f"  - [{source['label']}] 검색 중...")
        result = await run_structured_query(
            _collect_prompt(audience, source),
            RESEARCH_SCHEMA,
            model=MODEL,
            tools=["WebSearch", "WebFetch"],
            max_turns=40,
            timeout_s=900,
            max_budget_usd=3.0,
        )
        if not result.ok:
            errors[source["id"]] = result.error or "unknown error"
            per_source_counts[source["id"]] = 0
            if on_event:
                on_event(f"    실패: {result.error}")
            continue
        candidates = result.data.get("candidates", [])
        for c in candidates:
            c["source_id"] = source["id"]
        all_candidates.extend(candidates)
        per_source_counts[source["id"]] = len(candidates)

    metrics = {"collected_by_source": per_source_counts, "collect_errors": errors}
    return all_candidates, metrics


def dedup_candidates(candidates: list[dict]) -> tuple[list[dict], dict]:
    """3개 트랙이 같은 공고/기사를 중복으로 찾아올 수 있다(N036 실습에서 실제로
    겪은 "같은 사건 중복 선정" 문제와 같은 종류) — source_url이 같으면 먼저 온 것만
    남긴다."""
    seen: set[str] = set()
    deduped: list[dict] = []
    duplicate_ids: list[str] = []
    for c in candidates:
        key = (c.get("source_url") or "").strip()
        if key and key in seen:
            duplicate_ids.append(c["candidate_id"])
            continue
        if key:
            seen.add(key)
        deduped.append(c)
    metrics = {
        "dedup_input": len(candidates),
        "dedup_output": len(deduped),
        "duplicate_ids": duplicate_ids,
    }
    return deduped, metrics


# ---------- 2단계: 선별(Gate) ----------


def stage_select(candidates: list[dict]) -> tuple[list[dict], dict]:
    """1~2차 키워드 게이트. audience.yaml에서 로드된 키워드를 rules.py가 그대로 쓴다."""
    passed, rejected_ids = [], []
    for c in candidates:
        if passes_keyword_filter(c.get("title", ""), c.get("summary", "")):
            passed.append(c)
        else:
            rejected_ids.append(c["candidate_id"])
    metrics = {
        "gate_input": len(candidates),
        "gate_passed": len(passed),
        "gate_rejected_ids": rejected_ids,
    }
    return passed, metrics


# ---------- 3단계: 요약(Draft) + 인사이트 ----------


def _score_prompt(audience: dict, candidates: list[dict]) -> str:
    persona = audience["persona"]
    lines = "\n".join(
        f"- candidate_id={c['candidate_id']}, title={c['title']}, "
        f"position_level={c.get('position_level', '')}, confirmed_facts={c.get('confirmed_facts', [])}"
        for c in candidates
    )
    return (
        f"다음 채용 후보들에 대해 {persona['name']}({persona['background']})과의 관련도를 "
        "0~100점으로 채점하고, 단순 요약이 아니라 이분 관점에서 왜 지금 주목할 만한지 "
        "인사이트를 담아 한국어로 추천 이유(reason)를 작성해줘. 반드시 아래 confirmed_facts에 "
        "있는 내용만 근거로 삼고, 새로 검색하거나 조회하지 마 — 없는 사실을 지어내지 마.\n\n"
        + lines
    )


async def stage_summarize(
    candidates: list[dict], audience: dict, on_event=None
) -> tuple[dict, dict]:
    if not candidates:
        return {}, {"score_error": None, "korean_retry": False}

    prompt = _score_prompt(audience, candidates)
    result = await run_structured_query(prompt, SCORE_SCHEMA, model=MODEL, tools=[])
    retried = False
    if result.ok:
        before_session = result.session_id
        result = await apply_korean_retry_to_scores(prompt, MODEL, result, on_event=on_event)
        retried = result.session_id != before_session

    if not result.ok:
        return {}, {"score_error": result.error, "korean_retry": retried}

    scores_by_id = {s["candidate_id"]: s for s in result.data.get("scored", [])}
    return scores_by_id, {"score_error": None, "korean_retry": retried}


# ---------- 4단계: 검수(Verify) — 할루시네이션/오류 검증 + 예외 처리 ----------

_DATE_RE = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")


def _is_past_deadline(deadline_text: str, today: date) -> bool:
    """N036 실습에서 실제로 겪은 '오래된 공고/기사 유입'을 마지막 관문이 걸러낸 것과
    같은 원리 — 파싱 가능한 마감일이 오늘보다 이전이면 탈락시킨다. 파싱 불가(마감
    상시, 표기 없음)는 보수적으로 통과시키고 리포트에서 사람이 직접 확인하게 둔다."""
    m = _DATE_RE.search(deadline_text or "")
    if not m:
        return False
    try:
        y, mo, d = (int(x) for x in m.groups())
        return date(y, mo, d) < today
    except ValueError:
        return False


def stage_verify(
    candidates: list[dict], scores_by_id: dict, audience: dict
) -> tuple[list[dict], dict]:
    """점수를 못 받은 후보(할루시네이션 검증 실패로 간주)와 마감일이 지난 후보는
    스킵(예외 처리)하고, 나머지만 임계치로 최종 통과 여부를 가른다."""
    today = date.today()
    threshold = audience["score_threshold"]

    merged, skipped_no_score, skipped_expired = [], [], []
    for c in candidates:
        s = scores_by_id.get(c["candidate_id"])
        if s is None:
            skipped_no_score.append(c["candidate_id"])
            continue
        if _is_past_deadline(c.get("deadline", ""), today):
            skipped_expired.append(c["candidate_id"])
            continue
        merged.append({**c, "score": s["score"], "reason": s["reason"]})

    passed = [j for j in merged if j["score"] >= threshold]
    passed.sort(key=lambda j: j["score"], reverse=True)

    metrics = {
        "verify_input": len(candidates),
        "skipped_no_score": skipped_no_score,
        "skipped_expired_deadline": skipped_expired,
        "below_threshold": len(merged) - len(passed),
        "final_passed": len(passed),
    }
    return passed, metrics


# ---------- 5단계: 발행(Publish) ----------


def stage_publish(passed: list[dict], report_path: Path) -> dict:
    public_jobs = [j for j in passed if j.get("category") == "public"]
    company_jobs = [j for j in passed if j.get("category") == "company"]
    title_warnings = title_language_warnings(passed)

    body = build_report_body(public_jobs, company_jobs, title_warnings=title_warnings)
    write_report(body, report_path)

    return {
        "published_public": len(public_jobs),
        "published_company": len(company_jobs),
        "report_path": str(report_path),
    }
