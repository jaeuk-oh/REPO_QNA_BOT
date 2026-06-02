# QnA Bot Inhouse

**사내 코드베이스에 Slack으로 질문하면, RAG로 관련 코드를 찾아 GPT가 답해주는 봇.**

> "이 함수 어디서 호출돼?" → 파일 수십 개 뒤질 필요 없이 멘션 한 번으로 해결

---

## 데모

`@봇 로그인 처리는 어떻게 구현돼 있어?` 라고 멘션하면:

```
[코드] 패턴: JWT 기반 토큰 인증
이유: 세션 상태를 서버에 저장하지 않기 위해 stateless 방식 채택
장점: 수평 확장 용이, 서버 재시작 시 세션 유지
단점: 토큰 즉시 무효화 불가
신뢰도: 0.87
참조 파일: auth/middleware.py, auth/tokens.py
```

<!-- 데모 GIF 추가 예정: Slack 멘션 → "생각 중 🔍" → 구조화 답변 흐름 -->
<!-- ![demo](docs/demo.gif) -->

---

## 아키텍처

```
사용자 Slack 멘션
        │
        ▼  WebSocket (Socket Mode — 공개 URL 불필요)
┌─────────────────────────────────────────────┐
│  Render 서버 (상시 실행)                     │
│                                              │
│  1. 의도 분류  (gpt-4o-mini, max_tokens=5)  │
│     chat / project / code                   │
│          │                                  │
│          ├─ chat    → RAG 없이 자연어 답변   │
│          ├─ project → RAG + 자연어 답변      │
│          └─ code    → RAG + 구조화 답변      │
│                                              │
│  2. 질문 임베딩 (text-embedding-3-small)     │
│  3. ChromaDB 유사 청크 검색 (로컬, top_k=5) │
│  4. 청크 + 질문 → GPT 답변 생성             │
│     code → StructuredAnswer (Pydantic 스키마)│
└─────────────────────────────────────────────┘
        │
        ▼  HTTPS
  Slack 채널에 답변 표시

인덱싱 파이프라인 (첫 실행 1회 + 2일마다 증분)
  GitHub URL
    → git clone/pull
    → 언어별 청크 분할 (RecursiveCharacterTextSplitter.from_language)
    → text-embedding-3-small
    → ChromaDB PersistentClient 저장
```

---

## 기술 스택 & 선택 이유

| 기술 | 역할 | 왜 골랐나 |
|------|------|-----------|
| GPT-4o-mini | 의도 분류 / 답변 생성 | RAG 컨텍스트가 있으면 mini로 충분. gpt-4o 대비 비용 ~15배 절감 |
| text-embedding-3-small | 벡터 임베딩 | large 대비 비용 5배 저렴, 코드 검색 품질 차이 미미 |
| ChromaDB (로컬) | 벡터 저장/검색 | 비용 0, 네트워크 레이턴시 없음, 코드가 외부로 나가지 않음 |
| Slack Socket Mode | 이벤트 수신 | HTTP Webhook과 달리 공개 URL 불필요 — 방화벽 뒤 사내 환경에 최적 |
| Pydantic Structured Output | 코드 답변 포맷 강제 | 환각 파일 경로 차단, 패턴/이유/장단점/신뢰도 일관 포맷 보장 |
| RecursiveCharacterTextSplitter | 코드 청킹 | 언어별 구분자(함수·클래스 경계) 사용 → 단순 문자 분할 대비 의미 단위 보존 |
| APScheduler | 재인덱싱 스케줄 | git diff로 변경 파일만 증분 재임베딩 — 전체 재인덱싱 비용 회피 |
| Docker | 배포 환경 | chromadb가 C++ 빌드 도구(gcc, g++) 필요 — Render 기본 Python 환경에 없어서 Dockerfile로 직접 설치 |

상세 트레이드오프 → [DECISIONS.md](DECISIONS.md)

---

## 설치 및 실행

```bash
git clone <this-repo>
cd QnA_BOT_INHOUSE
python -m venv .qna_venv && source .qna_venv/bin/activate
pip install -r requirements.txt
```

`.env`:

```env
OPENAI_API_KEY=sk-...

SLACK_BOT_TOKEN_REPO_A=xoxb-...
SLACK_APP_TOKEN_REPO_A=xapp-...
SLACK_SIGNING_SECRET_REPO_A=...
# 레포 추가 시 REPO_B, REPO_C ... 동일 패턴
```

`config.py`에 레포 등록:

```python
_REPO_DEFINITIONS = [
    ("REPO_A", "https://github.com/your-org/your-repo"),
]
```

```bash
python main.py
# 첫 실행: 자동 clone + 인덱싱 (수 분 소요)
# "All bots running." 출력 후 Slack 멘션 가능
```

---

## 디렉토리 구조

```
├── main.py              # 진입점 (헬스체크 서버 + 봇 스레드 + 스케줄러)
├── config.py            # 설정 및 레포 등록
├── agent/
│   ├── answerer.py      # 의도 분류, GPT 답변 (StructuredAnswer 포함)
│   ├── retriever.py     # ChromaDB 유사도 검색
│   └── formatter.py     # Slack Block Kit 포맷
├── ingestion/
│   ├── cloner.py        # git clone/pull, 변경 파일 diff
│   ├── chunker.py       # 언어별 코드 청킹
│   └── embedder.py      # 임베딩 + ChromaDB upsert/delete
├── slackbot/
│   └── handler.py       # Slack 이벤트 핸들링, 백그라운드 스레드
└── scheduler/
    └── reindexer.py     # 증분 재인덱싱 + APScheduler
```

---

## 현재 상태

| 기능 | 상태 | 비고 |
|------|------|------|
| 코드 질문 — RAG + 구조화 답변 | ✅ 완료 | 패턴 / 이유 / 장단점 / 신뢰도 / 참조 파일 |
| 프로젝트 질문 — 자연어 답변 | ✅ 완료 | |
| 일반 대화 | ✅ 완료 | RAG 없이 처리 |
| 멀티 레포 독립 운영 | ✅ 완료 | 레포별 봇 + 컬렉션 분리 |
| 증분 재인덱싱 (2일 주기) | ✅ 완료 | git diff 기반, 변경 파일만 재임베딩 |
| Render 상시 배포 | ✅ 완료 | Docker + Persistent Disk |
| 멀티턴 대화 (스레드 맥락 유지) | 🔧 미구현 | 현재 매 멘션이 독립 처리됨 |
| Private 레포 지원 | 🔧 미구현 | GitHub PAT 인증 추가 필요 |
| 재인덱싱 실패 알림 | 🔧 미구현 | 현재 로그에만 기록 |
| 단위 테스트 | 🔧 미구현 | classify_intent / retrieve / chunk_repo 우선 |
| 전체 아키텍처 흐름 질문 | ⚠️ 구조적 한계 | 청크 분할 특성상 함수 간 호출 관계 파악 어려움 |

> **설계 의도**: "이 함수 뭐 해?", "이 변수 어디서 쓰여?" 같은 **국소적 질문**에 최적화되어 있습니다.
> 여러 파일에 걸친 전체 흐름 질문은 top_k 청크만 보는 구조적 한계로 정확도가 낮을 수 있습니다.
