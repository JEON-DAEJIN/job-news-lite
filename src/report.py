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
    return f"""<div class="callout example">
  <p><span class="label">[{escape(job.get('org_name', ''))}]</span> {escape(job.get('title', ''))}{warn_badge}
  {f" ({escape(job.get('position_level', ''))})" if job.get('position_level') else ""}</p>
  <p>• 마감일: {escape(job.get('deadline', '') or '미상')}</p>
  <p>• 요약: {escape(_excerpt(job.get('summary', '')))}</p>
  <p>• 추천 이유: {escape(job.get('reason', ''))}</p>
  <p>• 관련도 점수: {job.get('score', 0)}점</p>
  <p>• 링크: <a href="{escape(job.get('source_url', ''))}" target="_blank">{escape(job.get('source_url', ''))}</a></p>
</div>"""


def build_report_body(
    public_jobs: list[dict],
    company_jobs: list[dict],
    *,
    title_warnings: dict[str, bool] | None = None,
) -> str:
    title_warnings = title_warnings or {}
    today = date.today().isoformat()
    parts = [f"<h1>채용뉴스 파인더 — {today} 리포트</h1>"]

    all_jobs = public_jobs + company_jobs
    if not all_jobs:
        parts.append(f'<div class="callout warning"><p>{EMPTY_NOTICE}</p></div>')
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

    parts.append(f'<p class="footer-note">생성 시각: {today} · JobNewsLite v2</p>')
    return "\n".join(parts)


def write_report(body_html: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body_tmp = out_path.parent / "_body_tmp.html"
    body_tmp.write_text(body_html, encoding="utf-8")

    assemble_js = LECTURE_ASSETS / "assemble-html.js"
    subprocess.run(
        ["node", str(assemble_js), "채용뉴스 파인더 리포트", str(body_tmp), str(out_path)],
        check=True,
    )
    body_tmp.unlink(missing_ok=True)
    return out_path
