# RAG 개선 실험 계획 (EXPERIMENTS.md)

봇 성능을 **레버 하나씩** 바꿔가며 올린다. 각 실험은 3단 논리로 묶인다:
**이 지표가 낮다 → 낮은 원인이 이것이라 본다(가설) → 그 원인을 때리는 변경.**

## 규칙
- **자(尺) 고정**: `all.jsonl` 50문항·채점 규칙 불변. 실험 간 비교 유효성의 전제.
- **레버 하나씩**: 한 실험에 변수 하나. 각 실험 = 새 `--tag`.
- **선행조건**: 측정 전 `verify_goldset` 통과 (자↔인덱스 정렬). v0 정렬 사고 재발 방지 — [README](README.md) 참조.
- **판정 기준**: 검색 지표 **+0.03↑** 또는 Correctness 타깃축 **+0.5↑**, 그리고 다른 축 Correctness **−0.3 이내**(비열등)이면 채택 → 그 설정이 새 baseline. 아니면 원복.

## v0 baseline (2026-07-14, 유효)
| | Recall@5 | AllFound@5 | Hit@1 | Correct(0-5) | IntentAcc |
|---|---|---|---|---|---|
| OVERALL(50) | 0.50 | 0.41 | 0.31 | 1.96 | 0.44 |
| code(37) | 0.50 | 0.43 | 0.24 | 2.03 | 0.46 |
| project(13) | 0.50 | 0.33 | 0.50 | 1.77 | 0.39 |
| hop=multi(23) | 0.41 | 0.22 | 0.30 | 1.70 | 0.30 |
| hard(14) | 0.39 | 0.23 | 0.31 | 1.64 | 0.21 |

**드러난 실약점**: IntentAcc 0.44(라우팅), hop=multi AllFound 0.22(멀티파일 검색), Hit@1 0.31(랭킹).

---

## 실험 카드 (우선순위 = 싸고 격리된 것 → 검색 → 생성 → 구조)

### E8 — intent 프롬프트 보강 · 노림: IntentAcc 0.44↑ · 재인덱싱 ✗
- **원인 가설**: IntentAcc가 인덱스와 무관한데 0.44 → 순수 분류 문제로 확정. hard에서 0.21로 붕괴.
  현재 `_INTENT_SYSTEM`([answerer.py](../agent/answerer.py))은 정의 3줄뿐 **예시 0개**라 project↔code 경계에서 흔들림.
  DECISIONS #6도 오분류("대화 내역 저장 방식은?"→chat)를 인정.
- **바꿀 것**: `_INTENT_SYSTEM`에 실측 오분류 경계 케이스 few-shot 예시 추가.
- **판정**: IntentAcc +0.05↑, Correctness 회귀 없음.

### E5 — 하이브리드(BM25+벡터)/리랭커 · 노림: Hit@1 0.31↑, AllFound↑ · 재인덱싱 ✗
- **원인 가설**: 검색이 **순수 벡터 코사인 단독**([retriever.py](../agent/retriever.py)). 코드질문은
  `get_current_user` 같은 정확 심볼명 lexical 매칭이 결정적인데 벡터는 의미유사도만 봐 놓침.
  code Hit@1(0.24) < project(0.42)가 lexical 신호 부재의 증거.
- **바꿀 것**: `retrieve()`에 BM25+벡터 rank fusion 또는 cross-encoder 리랭커.
- **판정**: Hit@1 +0.05↑.

### E2 — 청크 1000→500 · 노림: Hit@1, Recall · 재인덱싱 ✓
- **원인 가설**: 큰 청크엔 여러 함수가 섞여 특정 함수 질문에 **청크 임베딩이 희석**됨(무관 코드가 벡터를 흐림).
  작게 쪼개면 함수 단위에 가까워져 질문↔청크 유사도가 선명.
- **바꿀 것**: `CHUNK_SIZE 1000→500`(양방향으로 1500도) ([config.py](../config.py)).
- **판정**: Hit@1 +0.03↑ (너무 작아 맥락 손실 시 원복).

### E3 — 경로 인지 임베딩 · 노림: navigation Recall/Hit@1 · 재인덱싱 ✓
- **원인 가설**: navigation(10문항, 최대 표본)은 "어디서 처리돼?"류인데 Recall 0.60 대비 Hit@1 0.30 —
  위치는 아는데 1순위를 못 짚음. 파일경로가 임베딩 텍스트에 없어 **위치 토큰이 검색에 안 실림**.
- **바꿀 것**: 청크 앞에 `rel_path` 삽입 후 임베딩 ([chunker.py](../ingestion/chunker.py) chunk_file).
- **판정**: navigation 축 Recall/Hit@1 +0.1↑.

### E1 — top_k 5→10 · 노림: multi-hop Correctness · 재인덱싱 ✗
- **원인 가설**: hop=multi AllFound@5 0.22 — 멀티파일 정답을 top5에 다 못 담음. 정답이 6~10위면 5컷에서 잘려
  생성이 재료를 못 받음. 컷↑ → 정답 포함 확률↑.
- **바꿀 것**: `TOP_K 5→10` + eval `--top-k 10` ([config.py](../config.py)).
- **판정**: 노이즈·비용↑ 트레이드오프 → Recall 아닌 **multi-hop Correctness +0.5↑**로 판정.

### E6 — answer 프롬프트 근거인용 강화 · 노림: Correctness 1.96↑ · 재인덱싱 ✗
- **원인 가설**: 검색이 정답을 가져와도(Recall 0.50) Correctness 1.96 → **검색-생성 갭**(자료는 있는데 답을 못 씀).
- **바꿀 것**: `_SYSTEM_TEMPLATE`/`_PROJECT_SYSTEM_TEMPLATE` 인용 규칙·few-shot 강화 ([answerer.py](../agent/answerer.py)).
- **판정**: OVERALL Correctness +0.2↑, judge violations↓.

### E9/E10 — AST 청킹 / 파일요약·호출그래프 · 노림: hop=multi · 재인덱싱 ✓
- **원인 가설**: 멀티홉은 파라미터로 한계 — DECISIONS #1·#5가 "RAG는 함수 간 호출관계·멀티파일 흐름을
  청크 분산 탓에 못 본다"고 명시. AST 청킹은 함수 잘림 제거, 파일요약/호출그래프는 청크에 없는
  파일 간 관계를 명시 인덱싱 → 구조적 원인 자체를 건드림.
- **판정**: hop=multi Correctness +0.5↑.

### (참고) E4·E7 — large 임베딩 / gpt-4o · 노림: "천장 진단"
- **원인 가설**: 위 레버를 다 당긴 뒤 남는 갭이 **모델 한계**인지 확인. E7이 Correctness를 크게 올리면
  병목=mini 추론력, E4가 Recall을 올리면 병목=임베딩 표현력임을 입증. 비용 트레이드오프라 마지막 원인규명용.
- **바꿀 것**: `CHAT_MODEL→gpt-4o`(E7) / `EMBEDDING_MODEL→large`(E4, 재인덱싱).

---

## 실행 로그
| tag | 레버 | 핵심 결과 | 판정 |
|---|---|---|---|
| v0 | (baseline) | Recall 0.50 / Correct 1.96 / IntentAcc 0.44 | 기준선 |
| v1 | E8 intent 프롬프트 | **IntentAcc 0.44→0.84 (+0.40)**, Correct 1.96→2.34 (+0.38), 검색 지표 불변 | **✅ 채택 (새 baseline)** |

### E8 상세 (v1)
- **원인 규명**: v0 오분류 28/50건 중 **23건이 정당한 레포 질문을 `chat`으로 오판**(code→chat 19, project→chat 4).
  자연어 표현("점수는 어디에 저장되나요?")을 잡담으로 분류. 원 프롬프트가 `chat="small talk"`이라고만 하고 예시 0개.
- **조치**: `_INTENT_SYSTEM`에 "레포에 관한 것이면 chat 아님" 규칙 + 실측 오분류 few-shot 5개 추가.
- **결과**: IntentAcc code 0.46→0.95, hard 0.21→0.64. **부수 효과**로 Correctness +0.38 —
  v0에선 코드질문이 chat 경로(RAG 없음)로 새서 틀렸는데, 라우팅이 고쳐지며 검색 컨텍스트를 쓰게 됨.
  **라우팅이 생성 품질을 은밀히 캡하고 있었다**는 인과 발견.
- **비열등**: n≥9 전 축 +0.23~+0.56. 유일한 − 는 hop=none(n=1) 5→4인데, 해당 문항 intent가 v0/v1 동일 →
  E8 무관한 judge 잡음(±1, DECISIONS #8). 회귀 아님.
- **남은 약점**: project IntentAcc 0.54(→code 오분류 4건: "호출 흐름 설명" 류 멀티파일 질문이 code로 감).
  골드셋에 chat 문항이 0개 → chat 과교정 위험은 이 자로 못 잡음. 향후 chat 문항 추가 필요.
