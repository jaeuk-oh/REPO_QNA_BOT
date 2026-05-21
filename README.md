# QnA Bot Inhouse

> 사내 코드베이스에 질문하면 GPT가 답해주는 Slack 봇

---

## 문제 정의

새로운 프로젝트 코드를 파악할 때마다 파일을 하나씩 열어보거나, 담당자에게 직접 물어봐야 했습니다.
"이 기능은 어디서 처리하지?", "대화 내역은 어떻게 저장되지?" 같은 질문에 답을 찾으려면 수십 개의 파일을 뒤져야 했고, 그 시간이 아깝게 느껴졌습니다.

**코드베이스에 직접 질문할 수 있다면 어떨까?** 라는 생각에서 출발했습니다.

---

## 주요 기능

### 3단계 의도 분류
질문의 성격을 자동으로 분류해 최적의 방식으로 답변합니다.

| 분류 | 예시 질문 | 응답 방식 |
|------|-----------|-----------|
| `[코드]` | "로그인 함수 어떻게 구현돼 있어?" | RAG + 구조화 답변 (패턴, 이유, 장단점, 참조 파일) |
| `[프로젝트]` | "이 서비스가 뭐 하는 건가요?" | RAG + 자연어 답변 |
| `[일반]` | "안녕" | 자연어 답변 |

### RAG 기반 코드 검색
- 레포지토리를 청크 단위로 분할 후 벡터 DB에 저장
- 질문과 의미적으로 유사한 코드 조각을 검색해 GPT 컨텍스트로 전달
- 전체 코드를 읽히지 않고 관련 부분만 전달해 정확도와 비용을 동시에 최적화

### 멀티 레포 독립 운영
- 레포마다 별도 Slack 봇, 별도 벡터 DB로 운영
- 레포 추가는 `config.py`에 한 줄 + 환경변수 3개로 완료

### 자동 재인덱싱
- 봇 시작 시 최초 인덱싱 (이미 인덱싱된 경우 스킵)
- 이후 2일마다 변경된 파일만 증분 재인덱싱

---

## 아키텍처

```
Slack 멘션
    ↓
의도 분류 (gpt-4o-mini)
    ↓
[코드/프로젝트] → 질문 임베딩 → ChromaDB 유사 청크 검색
    ↓
GPT-4o-mini에 청크 + 질문 전달 → 답변
    ↓
Slack 채널 응답
```

```
인덱싱 파이프라인
GitHub URL → git clone/pull → 코드 파일 순회
    → 청크 분할 (1000자 단위) → 임베딩 → ChromaDB 저장
```

---

## 적용 기술

| 분류 | 기술 |
|------|------|
| LLM | OpenAI GPT-4o-mini (답변, 의도 분류) |
| 임베딩 | OpenAI text-embedding-3-small |
| 벡터 DB | ChromaDB (로컬 PersistentClient) |
| Slack | slack-bolt (Socket Mode) |
| 텍스트 분할 | LangChain RecursiveCharacterTextSplitter |
| Git 자동화 | GitPython |
| 스케줄러 | APScheduler |
| 데이터 검증 | Pydantic |

---

## 설치 및 실행

### 환경 설정

```bash
git clone <this-repo>
cd QnA_BOT_INHOUSE
python -m venv .qna_venv
source .qna_venv/bin/activate
pip install -r requirements.txt
```

### 환경변수 설정

```env
OPENAI_API_KEY=...

SLACK_BOT_TOKEN_REPO_A=xoxb-...
SLACK_APP_TOKEN_REPO_A=xapp-...
```

### 레포 등록

`config.py`의 `_REPO_DEFINITIONS`에 추가:

```python
("REPO_A", "https://github.com/your-org/your-repo"),
```

### 실행

```bash
python main.py
```

---

## 알려진 한계

### 청크 단위 분할로 인한 맥락 단절
코드를 1000자 단위 청크로 잘라 저장하기 때문에, 함수 간 호출 관계나 모듈 간 의존성이 다른 청크에 분산되면 GPT가 그 연결을 파악하지 못합니다.

### 전체 파일 구조 및 흐름 파악 불가
질문과 유사도 높은 청크 5개만 GPT에 전달하는 구조상, 여러 파일에 걸친 전체 흐름(인증 흐름, 데이터 처리 파이프라인 등)을 묻는 질문에는 부정확한 답변이 나올 수 있습니다.

**→ 국소적 질문** ("이 함수 뭐 해?", "이 변수 어디서 쓰여?")엔 강하지만, **전체 아키텍처/흐름 질문**엔 한계가 있습니다.

---

## 디렉토리 구조

```
├── main.py              # 진입점
├── config.py            # 설정 및 레포 등록
├── agent/
│   ├── answerer.py      # 의도 분류 및 GPT 답변 생성
│   ├── retriever.py     # ChromaDB 검색
│   └── formatter.py     # Slack 블록 포맷
├── ingestion/
│   ├── cloner.py        # git clone/pull
│   ├── chunker.py       # 코드 청크 분할
│   └── embedder.py      # 임베딩 및 ChromaDB 저장
├── slackbot/
│   └── handler.py       # Slack 이벤트 핸들링
└── scheduler/
    └── reindexer.py     # 자동 재인덱싱
```
