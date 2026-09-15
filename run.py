"""JobNewsLite 실행 스크립트 — graph.py의 5단계 노드를 순서대로 호출하고,
진행 상황을 콘솔에 출력하며, 실행 기록을 store/metrics.jsonl에 남긴 뒤
리포트를 브라우저에 자동으로 연다.

바탕화면 run.bat에서 `uv run python run.py`로 실행된다.
"""

import asyncio
import json
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

import graph  # noqa: E402

REPORT_PATH = ROOT / "data" / "report_latest.html"
METRICS_PATH = ROOT / "store" / "metrics.jsonl"


def log(msg: str) -> None:
    print(msg, flush=True)


def append_metrics(record: dict) -> None:
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(METRICS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


async def run() -> None:
    started_at = datetime.now(timezone.utc)
    audience = graph.load_audience(ROOT / "audience.yaml")
    metrics: dict = {
        "run_at": started_at.isoformat(),
        "audience_file": "audience.yaml",
    }

    log("[1/4] 채용 뉴스 검색 중... (소스 3갈래)")
    candidates, collect_metrics = await graph.stage_collect(audience, on_event=log)
    metrics.update(collect_metrics)
    total_collected = len(candidates)

    candidates, dedup_metrics = graph.dedup_candidates(candidates)
    metrics.update(dedup_metrics)

    if not candidates:
        log("검색 결과가 없습니다. 리포트에 '오늘은 없음'으로 표시합니다.")
        metrics["outcome"] = "no_candidates"
        graph.stage_publish([], REPORT_PATH)
        append_metrics(metrics)
        webbrowser.open(REPORT_PATH.as_uri())
        return

    filtered, select_metrics = graph.stage_select(candidates)
    metrics.update(select_metrics)
    log(
        f"[2/4] 관문(Gate) 통과 확인 중... "
        f"{total_collected}건 수집(중복 제거 후 {dedup_metrics['dedup_output']}건) 중 "
        f"{len(filtered)}건 통과"
    )

    if not filtered:
        metrics["outcome"] = "no_candidates_after_gate"
        graph.stage_publish([], REPORT_PATH)
        append_metrics(metrics)
        log("[4/4] 리포트 생성 완료 — 브라우저를 엽니다")
        webbrowser.open(REPORT_PATH.as_uri())
        return

    log("[3/4] 관련도 평가 및 추천 이유(인사이트) 작성 중...")
    scores_by_id, score_metrics = await graph.stage_summarize(filtered, audience, on_event=log)
    metrics.update(score_metrics)

    passed, verify_metrics = graph.stage_verify(filtered, scores_by_id, audience)
    metrics.update(verify_metrics)
    log(
        f"    검수 완료 — 마감 지남 {len(verify_metrics['skipped_expired_deadline'])}건 제외, "
        f"임계치 미달 {verify_metrics['below_threshold']}건 제외, 최종 {verify_metrics['final_passed']}건"
    )

    publish_metrics = graph.stage_publish(passed, REPORT_PATH)
    metrics.update(publish_metrics)
    metrics["outcome"] = "published" if passed else "no_candidates_after_verify"

    append_metrics(metrics)
    log("[4/4] 리포트 생성 완료 — 브라우저를 엽니다")
    webbrowser.open(REPORT_PATH.as_uri())


if __name__ == "__main__":
    asyncio.run(run())
