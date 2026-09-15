> **완료 (2026-09-15)**: 이 핸드오프의 Phase 1 로드맵은 전부 구현·검증 완료했습니다. 이후
> 이 프로젝트는 아이펠 N036 실습 과제 제출물로도 겸용하게 되면서 `audience.yaml`/`graph.py`/
> `run.py`/`store/metrics.jsonl`/`REPORT.md` 구조로 한 번 더 정리됐습니다 — 최신 설계 판단과
> 실행 기록은 [`REPORT.md`](./REPORT.md)를 참고하세요. 이 문서는 그 이전 경위 기록으로 보관합니다.

# 핸드오프 — 채용뉴스 파인더(JobNewsLite) 다음 세션 시작용

작성일: 2026-09-14 → 다음 세션: JobNewsLite 실제 구현 시작

> 이번 세션은 N036 강의(뉴스레터 에이전트) 정리·실습 전용으로 남겨두기로 해서, JobNewsLite
> 구현은 **새 세션에서** 이어갑니다. 이 폴더(`SearchingJobs/JobNewsLite/`)가 v2 작업의 독립
> 관리 공간입니다 — v1(`SearchingJobs/` 루트, 어제 만든 워크넷+Gmail 자동발송 버전)과는
> 완전히 분리해서 다룹니다.

## 오늘 있었던 일 요약 (이 프로젝트와 관련된 부분만)

1. **N036 강의노트 완성 + 챕터8 실습(Colab)** — `Aiffel_Quest/강의정리/N036/`. 실제 Hacker News
   기사로 실습하며 두 가지를 실증했습니다: ① 프롬프트에 "한국어로"를 두 곳에 적어도 특정 필드만
   원문 언어로 새는 "언어 이탈"이 재현됨 ② 그걸 검사하는 코드조차 `headline+summary`를 합쳐서
   검사하면 착시가 생기고, **필드별로 따로 검사해야** 진짜 결과(1/2건 재시도 필요)가 드러남.
2. **card-news-agent의 `ai_news` 로직에 위 교훈을 실제로 반영** — `Aiffel_Quest/card-news-agent/`.
   `app/engine.py`에 `_korean_check_failures()`/`_apply_korean_retry()`를 추가해 카드마다
   headline·body를 각각 검사하고, 실패한 카드만 지목해 1회 재요청하도록 고쳤습니다. 아직
   **실제 실행으로는 검증 안 함**(단위 테스트로 로직만 확인) — 다음에 이 프로젝트를 다시 열면
   실제 run으로 한 번 확인해볼 것.
3. **이 PRD v2 작성** — 어제 만든 v1(JobAlert, 워크넷 스크래핑+Gmail OAuth+GitHub Actions
   매일 자동발송)이 채용정보 건수에 비해 과한 구조라고 판단해서, "바탕화면 더블클릭 →
   WebSearch로 뉴스 검색 → 로컬 HTML 리포트"로 가볍게 다시 설계했습니다. N036의 5단계
   파이프라인(수집→선별→요약→검수→발행)을 그대로 가져다 썼습니다.

## 다음 세션에서 할 일 — PRD v2 Phase 1 구현

PRD 원문: [`PRD_v2_가벼운버전(JobNewsLite).md`](./PRD_v2_가벼운버전(JobNewsLite).md) (같은 폴더)

구현 순서 제안:

1. **폴더 구조 확정** — 이 `JobNewsLite/` 안에 `src/`, `data/`(있다면) 등을 새로 만들지, 아니면
   v1의 `src/filters/rules.py`(1~2차 키워드 필터)를 그대로 가져와 재사용할지부터 정할 것
   (PRD 11장 "v1과의 관계" 참고 — rules.py는 재사용 가능, worknet.py/gmail_sender.py/db.py는
   이 버전에서 안 씀).
2. **수집(Collect)** — Claude Agent SDK `WebSearch`로 DJ님 조건에 맞는 채용 뉴스를 찾는 함수부터
   작성. **card-news-agent의 `app/sdk_client.py`를 그대로 참고할 것** — `run_structured_query()`
   패턴(구조화 출력 + 실패 시 1회 재시도 정책)이 이미 검증돼 있으니 새로 설계하지 말고 재사용.
3. **선별(Gate→Score)** — PRD 7장의 1~2차 키워드 게이트 + 3차 관련도 스코어링. 후보가 적으므로
   예선/본선 없이 전체 비교(N036 6장 "③ 전체 비교" 방식).
4. **요약+검수(Draft+Verify)** — 출력 스키마를 원문 대조 가능한 칸(기관명/직급/마감일/링크)과
   해석 칸(추천이유)으로 분리. **오늘 card-news-agent에 추가한 `_korean_check_failures()` 패턴을
   여기서도 그대로 재사용**(헤드라인/추천이유 필드별 한국어 검사 + 1회 재요청).
5. **발행(Publish)** — 정적 HTML 리포트 생성. `Aiffel_Quest/강의정리/lecture-assets/`의
   `html-shell.html`+`assemble-html.js`를 그대로 갖다 쓸 수 있음(콜아웃·표 스타일이 이미
   검증돼 있어 새로 디자인할 필요 없음).
6. **트리거** — Windows `.bat` 파일 작성, 끝나면 `webbrowser.open()`으로 리포트 자동 오픈.
   바탕화면에 바로가기 배치까지 확인.
7. **실제로 한 번 끝까지 돌려서 검증** — DJ 체크리스트 6번("실제로 시켜본다") 원칙대로, 가짜
   데이터가 아니라 실제 DJ님 조건으로 최소 1회 end-to-end 실행해서 리포트가 제대로 나오는지
   확인할 것.

## 참고할 것

- **card-news-agent가 가장 좋은 참고 구현체**입니다 — Claude Agent SDK 호출 패턴
  (`app/sdk_client.py`), 구조화 출력 스키마 설계(`app/schemas.py`), confirmed_facts/
  unconfirmed_claims 분리(DJ 체크리스트 5번), 실패해도 부분 결과는 남기는 패턴
  (`app/engine.py`의 `run_image_generation_stage` 주석 참고) — 전부 이미 실전 검증됨.
- N036 강의노트: `Aiffel_Quest/강의정리/N036/N036_뉴스레터에이전트(newsletter-agent).md`
  (특히 챕터 4·5의 관문/등급, 챕터 6·7의 절대평가/상대평가, 챕터 8의 스키마 분리 원칙)
- N036 챕터8 실습 리포트(오늘 실제로 검증한 것들):
  `Aiffel_Quest/강의정리/N036/실습/report.md`
- 메모리 `feedback-dj-tool-design-checklist` — 새 도구/프롬프트 설계 시작할 때 7개 체크리스트
  적용 제안할 것(이미 PRD 6장에 초안 반영해둠, 코드 작성 시 다시 한번 대입해서 구체화)
- 이 핸드오프 문서 자체는 1회성이니, 다음 세션에서 Phase 1을 다 구현했으면 지워도 됨
  (또는 "완료" 표시만 남기고 보관).
