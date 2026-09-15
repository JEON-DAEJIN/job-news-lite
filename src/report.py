"""PRD 4장/7장 화면 구성대로 리포트 body.html을 조립하고, 검증된 강의기록 자산
(assemble-html.js + html-shell.html)으로 자체완결형 단일 HTML을 만든다."""

import subprocess
from datetime import date
from html import escape
from pathlib import Path

LECTURE_ASSETS = Path.home() / ".claude" / "lecture-assets"

EMPTY_NOTICE = "오늘은 조건에 맞는 신규 공고가 없습니다."


def _excerpt(text: str, limit: int = 200) -> str:
    text = " ".join((text or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _entry_html(job: dict, *, title_warning: bool = False) -> str:
    warn_badge = (
        ' <span style="font-size:12px;color:var(--warn-text)">'
        "⚠ 원문 제목이 한국어가 아닐 수 있음</span>"
        if title_warning
        else ""
    )
    unconfirmed = job.get("unconfirmed_claims") or []
    unconfirmed_html = (
        f'<p>• <span style="color:var(--text-muted)">확인 안 된 내용(참고용): '
        f'{escape("; ".join(unconfirmed))}</span></p>'
        if unconfirmed
        else ""
    )
    return f"""<div class="callout example">
  <p><span class="label">[{escape(job.get('org_name', ''))}]</span> {escape(job.get('title', ''))}{warn_badge}
  {f" ({escape(job.get('position_level', ''))})" if job.get('position_level') else ""}</p>
  <p>• 마감일: {escape(job.get('deadline', '') or '미상')}</p>
  <p>• 요약: {escape(_excerpt(job.get('summary', '')))}</p>
  <p>• 추천 이유: {escape(job.get('reason', ''))}</p>
  <p>• 관련도 점수: {job.get('score', 0)}점</p>
  <p>• 링크: <a href="{escape(job.get('source_url', ''))}" target="_blank">{escape(job.get('source_url', ''))}</a></p>
{unconfirmed_html}</div>"""


def _source_summary_html(source_summary: list[dict]) -> str:
    """트랙별 수집 건수를 리포트에도 남긴다 — 지금까지는 store/metrics.jsonl에만 있어서,
    REPORT.md를 안 읽는 실사용자 입장에서는 "오늘 조건에 맞는 게 없다"와 "이 소스를
    아직 못 본다"를 구분할 수 없었다(피어리뷰 지적)."""
    if not source_summary:
        return ""
    items = []
    for s in source_summary:
        if s.get("error"):
            note = f"실패 — {escape(s['error'])}"
        else:
            note = f"{s['count']}건 수집"
        items.append(f"<li>{escape(s['label'])}: {note}</li>")
    return (
        '<h2>수집 소스 현황</h2>\n<ul class="source-summary">\n' + "\n".join(items) + "\n</ul>"
    )


def build_report_body(
    public_jobs: list[dict],
    company_jobs: list[dict],
    *,
    title_warnings: dict[str, bool] | None = None,
    source_summary: list[dict] | None = None,
) -> str:
    title_warnings = title_warnings or {}
    today = date.today().isoformat()
    parts = [f"<h1>채용뉴스 파인더 — {today} 리포트</h1>"]

    all_jobs = public_jobs + company_jobs
    if not all_jobs:
        parts.append(f'<div class="callout warning"><p>{EMPTY_NOTICE}</p></div>')
        parts.append(_source_summary_html(source_summary or []))
        return "\n".join(parts)

    top1 = max(all_jobs, key=lambda j: j.get("score", 0))
    parts.append('<h2>💡 오늘의 추천 TOP 1</h2>')
    parts.append(_entry_html(top1, title_warning=title_warnings.get(top1.get("candidate_id"), False)))

    parts.append("<h2>🏛️ 정부기관 / 공공기관 / 대학</h2>")
    if public_jobs:
        parts.extend(
            _entry_html(job, title_warning=title_warnings.get(job.get("candidate_id"), False))
            for job in public_jobs
        )
    else:
        parts.append("<p>해당 없음</p>")

    parts.append("<h2>🏢 일반기업 (임원급 / C-Level)</h2>")
    if company_jobs:
        parts.extend(
            _entry_html(job, title_warning=title_warnings.get(job.get("candidate_id"), False))
            for job in company_jobs
        )
    else:
        parts.append("<p>해당 없음</p>")

    parts.append(_source_summary_html(source_summary or []))
    parts.append(f'<p class="footer-note">생성 시각: {today} · JobNewsLite v2</p>')
    return "\n".join(parts)


def _plain_html(title: str, body_html: str) -> str:
    """assemble-html.js를 못 쓸 때의 대체 셸. 스타일 없는 최소 HTML이지만
    내용(발행 결과)은 살아남는다 — 저장소 밖 자산(~/.claude/lecture-assets)이 없는
    환경(예: 이 저장소를 clone만 한 다른 사람의 PC)에서도 발행이 죽지 않게 한다."""
    return f"<!DOCTYPE html>\n<html lang='ko'><head><meta charset='utf-8'><title>{escape(title)}</title></head><body>\n{body_html}\n</body></html>\n"


def write_report(body_html: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    assemble_js = LECTURE_ASSETS / "assemble-html.js"

    if not assemble_js.exists():
        print(
            f"[경고] {assemble_js} 를 찾을 수 없어 스타일 없는 기본 HTML로 발행합니다 "
            "(내용은 정상입니다 — 이 저장소 밖의 개인 자산 폴더가 없는 환경으로 보입니다)."
        )
        out_path.write_text(_plain_html("채용뉴스 파인더 리포트", body_html), encoding="utf-8")
        return out_path

    body_tmp = out_path.parent / "_body_tmp.html"
    body_tmp.write_text(body_html, encoding="utf-8")
    try:
        subprocess.run(
            ["node", str(assemble_js), "채용뉴스 파인더 리포트", str(body_tmp), str(out_path)],
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[경고] assemble-html.js 실행 실패({e}) — 스타일 없는 기본 HTML로 대체합니다.")
        out_path.write_text(_plain_html("채용뉴스 파인더 리포트", body_html), encoding="utf-8")
    finally:
        body_tmp.unlink(missing_ok=True)
    return out_path
