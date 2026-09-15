"""audience.yaml의 include_keywords/exclude_keywords를 읽어 1~2차 키워드
게이트를 적용한다. 선별 기준의 단일 출처는 audience.yaml이고, 이 파일은 그 기준을
코드로 적용하는 역할만 한다 — 조건을 바꾸고 싶으면 이 파일이 아니라 audience.yaml을
고친다."""

import functools
from pathlib import Path

import yaml

_AUDIENCE_PATH = Path(__file__).resolve().parents[2] / "audience.yaml"


@functools.lru_cache(maxsize=1)
def _load_keywords() -> tuple[list[str], list[str], list[str], list[str]]:
    with open(_AUDIENCE_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    include = data["include_keywords"]
    exclude = data["exclude_keywords"]
    return include["position"], include["field"], exclude["level"], exclude["field"]


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def passes_keyword_filter(title: str, body: str = "") -> bool:
    """1~2차 필터를 모두 통과하면 True."""
    position_keywords, field_keywords, exclude_level, exclude_field = _load_keywords()
    combined = f"{title}\n{body}"

    if not _contains_any(combined, position_keywords):
        return False
    if not _contains_any(combined, field_keywords):
        return False

    if _contains_any(combined, exclude_level):
        return False
    if _contains_any(combined, exclude_field):
        return False

    return True
