"""Claude Agent SDK 호출 래퍼.

DJ 체크리스트 적용:
- 1) 언제 쓰고 안 쓰는지: tools를 WebSearch/WebFetch로 명시 제한한다. 다른 도구는
  애초에 호출조차 불가능하다 (permission_mode는 승인 프롬프트를 받을 사람이 없는
  헤드리스 서버 특성상 bypassPermissions로 두지만, 실행 가능한 도구 자체가 이미
  두 개로 제한돼 있어 실질적 위험은 크지 않다).
- 2) 실패 시 대응: 구조화 출력 파싱 실패 시 같은 세션에 1회만 엄격 재요청하고,
  그래도 실패하면 예외를 던지지 않고 error 문자열을 반환해 호출자가 run을 failed로
  기록하게 한다 (추측으로 계속 루프 돌지 않는다).
"""

import asyncio
import json
import re
from dataclasses import dataclass

from claude_agent_sdk import (
    CLIConnectionError,
    CLIJSONDecodeError,
    ClaudeAgentOptions,
    ProcessError,
    ResultError,
    ResultMessage,
    query,
)

FENCE_RE = re.compile(r"```json\s*(.*?)```", re.DOTALL)

STRICT_RETRY_SUFFIX = (
    "\n\nYour previous reply did not contain valid JSON matching the requested schema. "
    "Reply again with ONLY a single fenced ```json code block containing the JSON object "
    "matching the schema — no other text before or after it."
)

# 어떤 실패만 "형식을 다시 강하게 요청"하면 회복 가능한지 판단한다. 예산 초과/타임아웃/
# max_turns 초과처럼 같은 조건으로 재시도해도 반드시 다시 실패할 오류는 재시도하지
# 않는다 — 실제로 max_budget_usd=0.5로 테스트했을 때 재시도가 예산을 두 배로 태우고도
# 다시 같은 이유로 실패하는 것을 확인했다(DJ 체크리스트 2번: 실패를 실제로 시켜보고
# 그 결과로 재시도 정책을 정함).
def _is_recoverable_by_reformat(error: str) -> bool:
    return "no structured_output" in error or "json_decode_error" in error


@dataclass
class StructuredResult:
    data: dict | None
    session_id: str | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.data is not None and self.error is None


def _extract_json(result_message: ResultMessage | None) -> dict | None:
    if result_message is None:
        return None
    if result_message.structured_output is not None:
        return result_message.structured_output
    if result_message.result:
        m = FENCE_RE.search(result_message.result)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                return None
    return None


async def _single_call(
    prompt: str,
    json_schema: dict,
    *,
    model: str,
    resume: str | None,
    max_turns: int,
    timeout_s: int,
    max_budget_usd: float,
    tools: list[str],
) -> StructuredResult:
    options = ClaudeAgentOptions(
        model=model,
        tools=tools,
        permission_mode="bypassPermissions",
        resume=resume,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        output_format={"type": "json_schema", "schema": json_schema},
        system_prompt=(
            "You are a careful research assistant. Do not fabricate facts, dates, or URLs. "
            "End your final reply with a fenced ```json code block containing ONLY the JSON "
            "object matching the requested schema, as a backup in case structured output "
            "is not applied."
        ),
    )

    last: ResultMessage | None = None
    session_id = resume

    async def _drive() -> None:
        nonlocal last, session_id
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                last = message
                session_id = message.session_id

    try:
        await asyncio.wait_for(_drive(), timeout=timeout_s)
    except ResultError as e:
        return StructuredResult(None, e.session_id or session_id, f"{e.subtype}: {e.result or e}")
    except (ProcessError, CLIConnectionError, CLIJSONDecodeError) as e:
        return StructuredResult(None, session_id, f"{type(e).__name__}: {e}")
    except TimeoutError:
        return StructuredResult(None, session_id, "timeout")

    data = _extract_json(last)
    if data is None:
        return StructuredResult(None, session_id, "no structured_output and no parseable json fence")
    return StructuredResult(data, session_id, None)


async def run_structured_query(
    prompt: str,
    json_schema: dict,
    *,
    model: str,
    resume: str | None = None,
    max_turns: int = 20,
    timeout_s: int = 600,
    max_budget_usd: float = 2.0,
    tools: list[str] | None = None,
) -> StructuredResult:
    """구조화 출력을 요구하는 단발 호출. JSON 형식 실패일 때만 같은 세션에 1회 엄격
    재요청한다 — 예산 초과/타임아웃처럼 재시도해도 반드시 다시 실패할 오류는 즉시
    반환한다(비용을 헛되이 두 배로 태우지 않는다)."""
    resolved_tools = ["WebSearch", "WebFetch"] if tools is None else tools
    result = await _single_call(
        prompt,
        json_schema,
        model=model,
        resume=resume,
        max_turns=max_turns,
        timeout_s=timeout_s,
        max_budget_usd=max_budget_usd,
        tools=resolved_tools,
    )
    if result.ok:
        return result
    if not _is_recoverable_by_reformat(result.error or ""):
        return result

    # 1회 엄격 재요청 (DJ 체크리스트 2번: 실패 시 무한 재시도가 아니라 정해진 횟수만,
    # 그리고 재시도로 회복 가능한 실패 유형에만 한정한다)
    retry_session = result.session_id
    retry = await _single_call(
        prompt + STRICT_RETRY_SUFFIX,
        json_schema,
        model=model,
        resume=retry_session,
        max_turns=max_turns,
        timeout_s=timeout_s,
        max_budget_usd=max_budget_usd,
        tools=resolved_tools,
    )
    if retry.ok:
        return retry
    # 재시도도 실패 — 세션 ID는 보존해서 호출자가 나중에 이어갈 수 있게 한다.
    return StructuredResult(None, retry.session_id or retry_session, retry.error or result.error)
