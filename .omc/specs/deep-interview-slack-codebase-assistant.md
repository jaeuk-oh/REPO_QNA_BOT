# Deep Interview Spec: Slack 멀티레포 코드베이스 어시스턴트

## Metadata
- Interview ID: slack-codebase-assistant-2026-04-22
- Rounds: 9 (+ 대화 기반 스펙 보완)
- Final Ambiguity Score: 17%
- Type: greenfield
- Generated: 2026-04-22
- Last Updated: 2026-04-22
- Threshold: 20%
- Status: PASSED
- MVP Phase: v1 (레포별 단독 봇) | v2 (크로스레포 협업) 별도

---

## Clarity Breakdown

| 차원 | 점수 | 가중치 | 가중 점수 |
|------|------|--------|----------|
| 목표 명확도 | 0.88 | 0.40 | 0.352 |
| 제약 조건 | 0.78 | 0.30 | 0.234 |
| 성공 기준 | 0.82 | 0.30 | 0.246 |
| **총 명확도** | | | **0.832** |
| **모호도** | | | **17%** |

---

## Goal

여러 개의 GitHub 저장소를 각각 독립된 Slack 봇으로 인덱싱하고,
사용자가 `@repo1bot`, `@repo2bot` 으로 특정 봇을 멘션해 해당 레포에 대해 질문하면
**그 봇만의 ChromaDB를 검색하여 구조화된 패턴 분석 답변을 제공**하는 시스템.

취업 포트폴리오 목적: 개인 프로젝트 저장소들을 질의응답 가능한 지식 베이스로 만들고,
나중에는 실제 사내 엔지니어링 지식 어시스턴트로 확장 가능한 구조.

**v1 (현재 MVP)**: 레포별 단독 봇, `@mention` 질문만
**v2 (이후)**: 봇 간 협업, 일반 질문 라우팅

---

## Constraints

- **LLM**: OpenAI GPT-4o (API 키 기반, Anthropic API 미사용)
- **임베딩**: OpenAI `text-embedding-3-small`
- **벡터 DB**: ChromaDB (로컬 파일 기반 영속성, 레포별 독립 컬렉션)
- **Slack 연동**: 레포별 독립 Slack 앱/봇 (각 봇마다 별도 토큰)
- **저장소 수집**: GitHub URL 입력 → 로컬 clone → RAG 인덱싱
- **자동 재인덱싱**: APScheduler로 2일 간격, 변경된 파일만 재임베딩 (git 커밋 해시 비교)
- **언어/런타임**: Python
- **v1에서 LangGraph 불필요**: 단일 레포 봇에는 StateGraph 오케스트레이션 불필요

### Non-constraints (범위 외)
- GitHub API 연동 없이 clone만 사용 (퍼블릭 레포 기준)
- 사용자 인증/권한 관리 없음 (MVP 범위 외)

---

## Non-Goals

- 코드 자동 수정 또는 PR 생성
- 실시간 커밋 감지 (2일 주기 폴링으로 충분)
- 웹 UI (Slack만 사용)
- 여러 사용자 계정 지원 (단일 개인 사용자)
- Private GitHub 레포 지원 (MVP 기준 퍼블릭 레포)
- **봇 간 협업 및 일반 질문 라우팅 → v2**
- **크로스레포 비교 질문 → v2**

---

## Acceptance Criteria (v1 MVP)

- [ ] GitHub URL을 입력하면 레포가 clone되고 ChromaDB에 인덱싱된다
- [ ] 각 레포에 대응하는 Slack 봇이 `@repobot` 멘션에 응답한다
- [ ] `@repobot` 은 자신의 레포 ChromaDB만 검색한다 (다른 레포 접근 없음)
- [ ] 단일 레포 질문 (`@proj1bot 로그인 코드는 어디?`)에 다음 6가지 형식으로 답변한다:
  - 어떤 패턴인지
  - 왜 사용했는지 (추론)
  - 장점
  - 단점
  - 적합한 상황
  - 신뢰도 (0~100%)
- [ ] 답변에 관련 파일 경로 및 코드 스니펫이 포함된다
- [ ] APScheduler가 2일마다 각 레포를 `git pull`하고 변경 파일만 재임베딩한다
- [ ] 변경 없으면 재임베딩 스킵 (git HEAD 해시 비교)

---

## Assumptions Exposed & Resolved

| 가정 | 질문 | 해결 |
|------|------|------|
| 봇 하나로 전체 관리 | "별도 Slack 앱이 필요한가?" (Contrarian) | 레포별 독립 봇 (`@repo1bot`, `@repo2bot`) 방식 선택 |
| 코드 전체를 컨텍스트로 전달 | "어떻게 코드를 이해할 것인가?" | RAG + 벡터 임베딩 방식 |
| 단순 코드 위치 답변 | "어떤 질문까지 답해야 MVP?" | 패턴/이유/장단점/상황/신뢰도 6가지 구조화 답변 |
| 복잡한 봇 간 API 통신 | "가장 단순한 버전은?" (Simplifier) | Slack 메시지 방식으로 협업 |

---

## Technical Context

**프로젝트 디렉토리**: `/Users/jae6/AI-AGENT/QnA_BOT_INHOUSE/`
**현재 상태**: `main.py` 빈 파일 (완전 신규 구현)

### 권장 아키텍처 (v1 MVP)

```
사용자 → @repo1bot 멘션
              │
              ▼
      [slack_handler.py]
      slack_bolt Event API
              │
              ▼
      [repo_agent.py]
      ChromaDB-1 검색 (repo1 전용)
              │
              ▼
      [answer_formatter.py]
      GPT-4o → StructuredAnswer
              │
              ▼
      Slack 답변 (패턴/이유/장단점/상황/신뢰도)

백그라운드:
[scheduler.py] ──2일마다──▶ git pull → 해시 비교 → 변경파일만 재임베딩
```

### 핵심 컴포넌트 (v1)

| 컴포넌트 | 역할 | 기술 |
|---------|------|------|
| `ingestion.py` | GitHub clone → 파일 파싱 → 청크 분할 → ChromaDB 저장 | LangChain splitter, ChromaDB |
| `scheduler.py` | 2일 주기 자동 재인덱싱, git HEAD 해시 비교로 변경 파일만 처리 | APScheduler |
| `repo_agent.py` | 질문 수신 → ChromaDB 검색 → GPT-4o → 구조화 답변 | OpenAI, ChromaDB |
| `slack_handler.py` | Slack Event API 수신 → repo_agent 호출 | slack_bolt |
| `answer_formatter.py` | 6가지 구조화 답변 포맷팅 | OpenAI structured output (Pydantic) |

### 구조화 답변 스키마

```python
class StructuredAnswer(BaseModel):
    pattern: str          # 어떤 패턴인지
    rationale: str        # 왜 사용했는지
    pros: list[str]       # 장점
    cons: list[str]       # 단점
    best_for: str         # 적합한 상황
    confidence: float     # 신뢰도 (0.0~1.0)
    code_refs: list[str]  # 관련 파일 경로
    snippets: list[str]   # 코드 스니펫
```

---

## Ontology (Key Entities)

| 엔티티 | 타입 | 주요 필드 | 관계 |
|--------|------|----------|------|
| Repository | core domain | url, local_path, name, language | RepoBot owns 1 Repository |
| RepoBot | core domain | slack_token, bot_id, chroma_collection | RepoBot has 1 VectorDB, belongs to OrchestratorGraph |
| VectorDB (Chroma) | supporting | collection_name, persist_dir | VectorDB stores EmbeddingIndex for 1 RepoBot |
| EmbeddingIndex | supporting | chunks, embeddings, metadata | EmbeddingIndex contains CodeChunks |
| OrchestratorGraph | core domain | bots[], routing_logic | OrchestratorGraph routes to many RepoBots |
| SlackMessage | external system | channel_id, user_id, text, thread_ts | SlackMessage triggers RepoBot or OrchestratorGraph |
| SlackUser | external system | user_id, workspace | SlackUser sends SlackMessage |
| StructuredAnswer | core domain | pattern, rationale, pros, cons, confidence, code_refs | StructuredAnswer is returned by RepoBot |

---

## Ontology Convergence

| 라운드 | 엔티티 수 | 신규 | 변경 | 안정 | 안정도 |
|--------|---------|------|------|------|--------|
| 1 | 4 | 4 | - | - | N/A |
| 2 | 5 | 1 | 0 | 4 | 80% |
| 4 | 6 | 1 | 1 | 4 | 83% |
| 7 | 7 | 1 | 0 | 6 | 86% |
| 9 | 7 | 0 | 1 | 6 | **100%** |

---

## Interview Transcript

<details>
<summary>전체 Q&A (9 라운드)</summary>

### Round 1
**Q:** LLM API를 어떻게 사용할 계획인가요?
**A:** OpenAI API (GPT-4o)
**Ambiguity:** 60% (Goal: 0.55, Constraints: 0.30, Criteria: 0.30)

### Round 2
**Q:** 저장소를 어떻게 제공할 예정인가요?
**A:** GitHub URL 입력
**Ambiguity:** 55% (Goal: 0.60, Constraints: 0.40, Criteria: 0.30)

### Round 3
**Q:** 첫 버전을 "쓸 만하다"고 판단할 기준은?
**A:** 각 레포별 봇 + 봇끼리 Slack으로 소통해서 가장 적절한 봇이 답변
**Ambiguity:** 45% (Goal: 0.70, Constraints: 0.45, Criteria: 0.45)

### Round 4 (Contrarian)
**Q:** "봇마다 별도 Slack 앱"이 실제로 필요한가? 하나로 내부 라우팅 안 될까?
**A:** 각 레포마다 봇 하나씩, 유저는 @repo1bot @repo2bot 식으로 호출
**Ambiguity:** 42% (Goal: 0.75, Constraints: 0.45, Criteria: 0.50)

### Round 5
**Q:** 일반 질문이 들어오면 봇들이 어떻게 협업해야 할까?
**A:** Slack 메시지 방식
**Ambiguity:** 37% (Goal: 0.78, Constraints: 0.55, Criteria: 0.50)

### Round 6 (Simplifier)
**Q:** 여러 봇이 답한 후 유저가 Slack에서 보는 형태는?
**A:** 가장 연관성 높은 한 봇이 통합 답변 제공
**Ambiguity:** 32% (Goal: 0.80, Constraints: 0.55, Criteria: 0.65)

### Round 7
**Q:** 각 레포봇이 코드를 어떻게 이해하고 답변 생성할까?
**A:** RAG (Vector DB + 임베딩)
**Ambiguity:** 28% (Goal: 0.82, Constraints: 0.65, Criteria: 0.65)

### Round 8
**Q:** RAG 파이프라인 기술 스택은?
**A:** LangGraph + ChromaDB
**Ambiguity:** 23% (Goal: 0.85, Constraints: 0.78, Criteria: 0.65)

### Round 9
**Q:** 어떤 질문 유형까지 답할 수 있어야 MVP인가?
**A:** 패턴, 이유, 장점, 단점, 적합한 상황, 신뢰도
**Ambiguity:** 17% ✅ (Goal: 0.88, Constraints: 0.78, Criteria: 0.82)

</details>
