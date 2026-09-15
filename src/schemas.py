"""PRD 7장/3장 기준 구조화 출력 스키마.

DJ 체크리스트 3번(필요한 만큼만 받기): 후보마다 원문 대조 가능한 칸(기관명/직급/
마감일/링크)과 해석 칸(추천이유)을 분리해서 요구한다.
DJ 체크리스트 5번(근거 요구): confirmed_facts/unconfirmed_claims를 분리해서
"그럴듯한 결론"만 오는 걸 막는다.
"""

# ---------- 1단계: 수집(Collect) + 관문(Gate) ----------
# WebSearch로 후보를 찾고 WebFetch로 실제 본문을 열어(G1) 관문을 통과한 것만 반환하게 한다.
RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["public", "company"],
                    },
                    "org_name": {"type": "string"},
                    "title": {"type": "string"},
                    "position_level": {"type": "string"},
                    "date": {"type": "string"},
                    "deadline": {"type": "string"},
                    "source_url": {"type": "string"},
                    "summary": {"type": "string"},
                    "confirmed_facts": {"type": "array", "items": {"type": "string"}},
                    "unconfirmed_claims": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "candidate_id",
                    "category",
                    "org_name",
                    "title",
                    "position_level",
                    "date",
                    "deadline",
                    "source_url",
                    "summary",
                    "confirmed_facts",
                    "unconfirmed_claims",
                ],
            },
        },
    },
    "required": ["candidates"],
}

# ---------- 2단계: 등급(Score) ----------
# 이미 확인된 confirmed_facts만 근거로 점수/추천이유를 매기게 한다(새 검색·조회 불필요).
SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "scored": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "reason": {"type": "string"},
                },
                "required": ["candidate_id", "score", "reason"],
            },
        },
    },
    "required": ["scored"],
}
