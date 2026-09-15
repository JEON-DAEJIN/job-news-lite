# JobNewsLite — 채용뉴스 파인더

콘텐츠산업/신규사업 분야 임원급 채용·인사 정보를 WebSearch/WebFetch로 수집·선별·검수해
로컬 HTML 리포트로 발행하는 개인용 에이전트. 아이펠 N036 "나만의 뉴스레터 에이전트
구축하기" 실습 과제 제출물이기도 합니다.

**전체 설계 판단·소스 채택 근거·실행 기록은 [`REPORT.md`](./REPORT.md)에 있습니다.**

## 실행 방법

```bash
uv sync
uv run python run.py
```

(또는 `pip install -r requirements.txt && python run.py`)

바탕화면에서는 [`run.bat`](./run.bat) 더블클릭으로 실행합니다. 완료되면 `data/report_latest.html`이
생성되고 브라우저가 자동으로 열립니다.

### 선택 의존성 — 스타일이 입혀진 리포트

`src/report.py`는 기본적으로 `~/.claude/lecture-assets/assemble-html.js`(Node.js 필요)를
써서 스타일이 입혀진 리포트를 만듭니다. 이 폴더는 이 저장소 밖에 있는 개인 자산이라
**clone만 받은 환경에는 없습니다** — 없어도 실행이 죽지 않고, 스타일 없는 기본 HTML로
자동 대체됩니다(콘솔에 경고만 출력). 이 저장소를 그대로 복제해 실행하는 것만으로는
스타일이 안 입혀진 리포트를 보게 된다는 뜻이며, 이는 의도된 동작입니다.

## 구조

| 파일 | 역할 |
|---|---|
| [`audience.yaml`](./audience.yaml) | 타깃 독자, 키워드 게이트, 점수 임계치, 소스 3트랙 — 선별 기준의 단일 출처 |
| [`src/graph.py`](./src/graph.py) | 5단계(수집→선별→요약→검수→발행) 노드 함수 |
| [`run.py`](./run.py) | 노드를 순서대로 호출하고 `store/metrics.jsonl`에 실행 기록을 남기는 진입점 |
| [`src/sdk_client.py`](./src/sdk_client.py) | Claude Agent SDK 구조화 출력 호출 래퍼 |
| [`src/filters/rules.py`](./src/filters/rules.py) | `audience.yaml` 키워드로 1~2차 게이트 적용 |
| [`src/verify.py`](./src/verify.py) | 한국어 필드 검사 + 1회 재요청 |
| [`src/report.py`](./src/report.py) | HTML 리포트 조립 |
| [`store/metrics.jsonl`](./store/metrics.jsonl) | 실행마다 누적되는 단계별 지표(증빙 로그) |
