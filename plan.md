# QnA Bot Inhouse — 개발 플랜

> 목표: 레포별 독립 Slack 봇 + RAG 기반 코드 질의응답 시스템 (v1 MVP)
> 스택: Python · OpenAI GPT-4o · ChromaDB · slack_bolt · APScheduler

---

## 폴더 구조

```
QnA_BOT_INHOUSE/
├── main.py                   # 진입점: Slack 봇 + 스케줄러 실행
├── config.py                 # 환경변수 로드, 레포 목록 정의
├── requirements.txt
├── .env                      # API 키 (절대 커밋 금지)
├── .gitignore
│
├── ingestion/
│   ├── __init__.py
│   ├── cloner.py             # GitHub URL → 로컬 clone / git pull
│   ├── chunker.py            # 소스파일 → 텍스트 청크
│   └── embedder.py           # 청크 → OpenAI 임베딩 → ChromaDB 저장
│
├── agent/
│   ├── __init__.py
│   ├── retriever.py          # 질문 → ChromaDB 유사도 검색
│   ├── answerer.py           # 검색 결과 + GPT-4o → 구조화 답변
│   └── formatter.py          # Slack 메시지 포맷 변환
│
├── slack/
│   ├── __init__.py
│   └── handler.py            # slack_bolt @mention 이벤트 처리
│
├── scheduler/
│   ├── __init__.py
│   └── reindexer.py          # APScheduler 2일 재인덱싱 로직
│
└── data/
    ├── repos/                # git clone 저장 위치 (gitignore)
    │   ├── repo-a/
    │   └── repo-b/
    ├── chroma/               # ChromaDB 로컬 파일 (gitignore)
    │   ├── repo-a/
    │   └── repo-b/
    └── meta.json             # 레포별 마지막 커밋 해시 저장
```

---

## 개발 순서

### Phase 1. 환경 설정

- [ ] Python 가상환경 생성
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  ```

- [ ] `requirements.txt` 작성 및 설치
  ```
  openai
  chromadb
  slack_bolt
  slack_sdk
  apscheduler
  gitpython
  langchain-text-splitters
  python-dotenv
  pydantic
  ```

- [ ] `.env` 파일 생성
  ```
  OPENAI_API_KEY=sk-...

  # 레포 A 봇
  SLACK_BOT_TOKEN_REPO_A=xoxb-...
  SLACK_SIGNING_SECRET_REPO_A=...

  # 레포 B 봇
  SLACK_BOT_TOKEN_REPO_B=xoxb-...
  SLACK_SIGNING_SECRET_REPO_B=...
  ```

- [ ] `.gitignore` 작성 (`.env`, `data/`, `__pycache__/` 포함)

- [ ] `config.py` 작성
  ```python
  # 레포 목록 정의 예시
  REPOS = [
      {
          "name": "repo-a",
          "github_url": "https://github.com/yourname/repo-a",
          "slack_bot_token": os.getenv("SLACK_BOT_TOKEN_REPO_A"),
          "slack_signing_secret": os.getenv("SLACK_SIGNING_SECRET_REPO_A"),
          "chroma_dir": "data/chroma/repo-a",
          "clone_dir": "data/repos/repo-a",
      },
      ...
  ]
  ```

---

### Phase 2. Ingestion 파이프라인

> 목표: GitHub 레포를 clone해서 ChromaDB에 코드 임베딩 저장

#### 2-1. `ingestion/cloner.py`
- [ ] `clone_repo(github_url, clone_dir)`: 없으면 clone, 있으면 git pull
- [ ] 반환값: 변경 여부 (True/False)
- [ ] `GitPython` 라이브러리 사용

#### 2-2. `ingestion/chunker.py`
- [ ] 대상 파일 필터링: `.py`, `.js`, `.ts`, `.java`, `.go`, `.md` 등 코드 파일만
- [ ] `langchain_text_splitters.RecursiveCharacterTextSplitter` 사용
  - `chunk_size=1000`, `chunk_overlap=200` 권장
- [ ] 각 청크에 메타데이터 붙이기: `{"file_path": "...", "repo": "repo-a", "language": "python"}`
- [ ] 반환: `List[Document]`

#### 2-3. `ingestion/embedder.py`
- [ ] `OpenAIEmbeddings(model="text-embedding-3-small")` 사용
- [ ] ChromaDB 컬렉션 생성: 레포별 독립 (`chroma_dir` 분리)
- [ ] `embed_documents(docs)`: 전체 초기 인덱싱
- [ ] `embed_diff(changed_files, chroma_dir)`: 변경 파일만 재임베딩
  - 기존 해당 파일 청크 삭제 후 재삽입 (metadata.file_path 기준)

#### 2-4. 테스트
- [ ] 실제 GitHub 레포 1개로 `clone → chunk → embed` 전 과정 수동 실행
- [ ] ChromaDB에 데이터 들어갔는지 확인:
  ```python
  collection = chroma_client.get_collection("repo-a")
  print(collection.count())  # 청크 수 출력
  ```

---

### Phase 3. RAG Agent

> 목표: 질문 → ChromaDB 검색 → GPT-4o → 구조화 답변

#### 3-1. `agent/retriever.py`
- [ ] `retrieve(query, repo_name, chroma_dir, top_k=5)` 함수
- [ ] OpenAI 임베딩으로 query 벡터화 → ChromaDB similarity search
- [ ] 반환: `List[{"content": ..., "file_path": ..., "score": ...}]`

#### 3-2. `agent/answerer.py`
- [ ] Pydantic 모델 정의:
  ```python
  class StructuredAnswer(BaseModel):
      pattern: str        # 어떤 패턴인지
      rationale: str      # 왜 사용했는지 (추론)
      pros: list[str]     # 장점
      cons: list[str]     # 단점
      best_for: str       # 적합한 상황
      confidence: float   # 신뢰도 0.0~1.0
      code_refs: list[str]  # 관련 파일 경로
      snippets: list[str]   # 핵심 코드 스니펫
  ```
- [ ] OpenAI `response_format` structured output 사용:
  ```python
  client.beta.chat.completions.parse(
      model="gpt-4o",
      response_format=StructuredAnswer,
      messages=[...]
  )
  ```
- [ ] 시스템 프롬프트 작성: "당신은 {repo_name} 코드베이스 전문가입니다. 다음 코드 컨텍스트를 바탕으로..."
- [ ] `answer(question, retrieved_docs, repo_name)` → `StructuredAnswer`

#### 3-3. `agent/formatter.py`
- [ ] `StructuredAnswer` → Slack 메시지 블록 변환
- [ ] Slack Block Kit 형식으로 보기 좋게 포맷팅
  ```
  *패턴*: JWT + Refresh Token
  *이유*: Stateless 서버를 위해 선택...
  *장점*: • 서버 확장 용이 • 세션 저장 불필요
  *단점*: • 토큰 탈취 시 즉시 무효화 불가
  *적합한 상황*: REST API 서버, MSA 환경
  *신뢰도*: 87%
  *관련 파일*: `src/auth/jwt.py`, `src/middleware/auth.py`
  ```

#### 3-4. 테스트
- [ ] 실제 질문으로 검색 → 답변 생성 수동 테스트
- [ ] 프롬프트 품질 검토 및 조정

---

### Phase 4. Slack 봇 연동

> 목표: @mention 시 해당 레포 agent 호출

#### 4-1. Slack 앱 생성 (레포마다 반복)
- [ ] [api.slack.com/apps](https://api.slack.com/apps) → Create New App
- [ ] **Socket Mode** 활성화 (ngrok 없이 로컬 개발 가능)
- [ ] OAuth Scopes 설정:
  - `app_mentions:read`
  - `chat:write`
  - `channels:history`
- [ ] Event Subscriptions → `app_mention` 구독
- [ ] 앱 설치 → Bot Token (`xoxb-...`) 및 App-Level Token (`xapp-...`) 저장

#### 4-2. `slack/handler.py`
- [ ] `slack_bolt` App 초기화 (Socket Mode)
- [ ] `@app.event("app_mention")` 핸들러 작성:
  ```python
  @app.event("app_mention")
  def handle_mention(event, say, client):
      question = event["text"]  # 멘션 텍스트에서 질문 추출
      repo_name = ...           # 어떤 봇인지 config에서 확인
      # retrieve → answer → format → say()
  ```
- [ ] 멘션 텍스트에서 봇 ID 제거 후 순수 질문만 추출
- [ ] 답변 생성 중 "생각 중..." 임시 메시지 처리 (UX)

#### 4-3. `main.py`
- [ ] 레포마다 별도 App 인스턴스 생성
- [ ] 각 App을 별도 쓰레드로 실행 (Socket Mode는 쓰레드 기반)
- [ ] APScheduler도 함께 시작

#### 4-4. 테스트
- [ ] 로컬에서 봇 실행 후 Slack에서 `@repoabot 로그인 방식은?` 테스트
- [ ] 답변 포맷 확인 및 개선

---

### Phase 5. 자동 재인덱싱 스케줄러

#### 5-1. `scheduler/reindexer.py`
- [ ] `data/meta.json`에 레포별 마지막 커밋 해시 저장
  ```json
  {
    "repo-a": "abc123...",
    "repo-b": "def456..."
  }
  ```
- [ ] `reindex_repo(repo_config)` 함수:
  1. `git pull` 실행
  2. 새 HEAD 해시 읽기
  3. 해시 동일하면 스킵
  4. `git diff --name-only <old_hash> <new_hash>` 로 변경 파일 목록
  5. 변경 파일만 재청크 → 재임베딩
  6. `meta.json` 업데이트
- [ ] APScheduler 설정:
  ```python
  scheduler = BackgroundScheduler()
  scheduler.add_job(reindex_all, 'interval', days=2)
  scheduler.start()
  ```

#### 5-2. 테스트
- [ ] interval을 `seconds=30`으로 줄여서 스케줄러 동작 확인
- [ ] 레포에 파일 변경 후 재인덱싱 확인
- [ ] 변경 없을 때 스킵되는지 확인

---

### Phase 6. 통합 테스트 & 마무리

- [ ] 전체 흐름 E2E 테스트:
  1. 새 레포 등록 (`config.py`에 추가)
  2. 초기 인덱싱 실행
  3. Slack에서 `@repobot 질문` 전송
  4. 구조화 답변 수신 확인
- [ ] 에러 처리: ChromaDB 없을 때, OpenAI 타임아웃, Slack 전송 실패
- [ ] `README.md` 작성: 설치 방법, 레포 추가 방법, 실행 방법

---

## 개발 팁

**개발 순서 추천**: Phase 2 → 3 → 4 → 5 순서로 진행. 각 Phase 끝에 단독 테스트 후 다음 단계.

**비용 절약**: 개발 중 임베딩 비용 아끼려면 `text-embedding-3-small` 사용 (가장 저렴). 테스트용 레포는 파일 수 적은 것 먼저.

**Socket Mode**: 로컬 개발 시 ngrok 없이도 Slack 이벤트 수신 가능. 프로덕션 전환 시 HTTP 모드로 변경.

**ChromaDB persist**: `chromadb.PersistentClient(path="data/chroma/repo-a")` 사용해야 재시작 후에도 데이터 유지.

**멀티봇 실행**: 봇마다 포트가 다를 필요 없음 (Socket Mode는 포트 불필요). 쓰레드로 동시 실행.
