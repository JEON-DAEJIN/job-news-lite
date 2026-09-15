"""PRD 3장/9장 검수(Verify) 단계 — card-news-agent app/engine.py의
_korean_check_failures/_apply_korean_retry 패턴을 그대로 이식.

헤드라인(공고 제목)과 추천 이유를 **필드별로 따로** 검사한다 — 합쳐서 검사하면
한쪽 필드의 한국어 이탈을 가릴 수 있다는 걸 N036 실습으로 확인했기 때문이다.

다만 제목(title)은 원문과 대조 가능한 칸(실제 공고 원문에서 그대로 가져온 값)이라
번역·재작성으로 "고치지" 않는다 — 한국어가 아니면 리포트에 표시만 하고 원문 그대로
둔다. 추천 이유(reason)는 AI가 새로 작성하는 해석 칸이라 재요청으로 교정 가능하다.
"""

import re

from schemas import SCORE_SCHEMA
from sdk_client import run_structured_query

_KOREAN_RE = re.compile(r"[가-힣]")


def title_language_warnings(candidates: list[dict]) -> dict[str, bool]:
    """candidate_id -> 제목에 한국어가 없으면 True (원문이 다른 언어일 수 있음, 참고용)."""
    return {
        c["candidate_id"]: not bool(_KOREAN_RE.search(c.get("title", "")))
        for c in candidates
    }


def _reason_check_failures(scored: list[dict]) -> list[str]:
    return [s["candidate_id"] for s in scored if not _KOREAN_RE.search(s.get("reason", ""))]


async def apply_korean_retry_to_scores(
    prompt: str,
    model: str,
    result,
    *,
    on_event=None,
):
    """추천 이유(reason)가 한국어가 아닌 candidate만 지목해 1회 재요청한다.
    재요청도 실패하면 원래 result를 그대로 쓴다(런 자체를 죽이지 않음)."""
    if not result.ok:
        return result

    scored = result.data.get("scored", [])
    failed = _reason_check_failures(scored)
    if not failed:
        return result

    if on_event:
        on_event(f"한국어 검사 실패(candidate {failed}) — 추천 이유 재요청 1회")

    retry_prompt = (
        prompt
        + f"\n\nCandidates {failed} had a non-Korean 'reason' field last time. "
        "Rewrite ONLY those candidates' reason field in Korean; keep every other "
        "candidate and every other field exactly the same."
    )
    retry = await run_structured_query(
        retry_prompt,
        SCORE_SCHEMA,
        model=model,
        resume=result.session_id,
        tools=[],
    )
    if not retry.ok:
        if on_event:
            on_event(f"한국어 재요청 실패: {retry.error} (원래 결과로 진행)")
        return result

    still_failed = _reason_check_failures(retry.data.get("scored", []))
    if on_event:
        fixed = len(failed) - len(still_failed)
        msg = f"한국어 재요청 완료 — {len(failed)}건 중 {fixed}건 교정됨"
        if still_failed:
            msg += f", {len(still_failed)}건은 재요청 후에도 미흡"
        on_event(msg)
    return retry
