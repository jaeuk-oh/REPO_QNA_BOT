# RAG 평가 프레임워크 — 설계 (고정 문서)

대상 봇: repo QnA Slack 봇 / 대상 레포: Leadership-Training-Service `api/` 백엔드

## 목적
현재 봇이 레포 질문에 얼마나 잘 답하는지 숫자로 재고, 그 숫자를 올리며 봇을 개선한다.
봇이 틀리는 원인을 **검색(Retrieval) / 생성(Generation)** 으로 분리 측정해, "무엇을 바꿨더니
무엇이 좋아졌나"를 인과적으로 말할 수 있게 한다.

## 원칙
1. **Slack 우회** — 평가는 전송 직전 답변을 직접 채점. `agent.retrieve` + `agent.answer*`만
   호출하고 Slack 토큰/소켓은 쓰지 않는다. 실험 반복 속도 확보.
2. **자(尺)는 고정** — 골드셋·채점 규칙은 안 바꾼다. 그래야 실험 간 점수 비교가 유효.
3. **지표 분리** — 단일 점수 금지. 검색과 생성을 따로 본다.

## 지표

| | 지표 | 정의 | 채점 |
|---|---|---|---|
| Metric 1   | **Recall@K**     | 검색 결과가 `gold_files`를 포함했나 (hop=multi는 전부 AND) | 결정론 |
| Metric 1.5 | **Hit@1**        | 정답 파일이 검색 1순위로 왔나 (랭킹 품질)              | 결정론 |
| Metric 2   | **Correctness 0~5** | 답변이 맞고 충분한가                                | LLM judge |
| Metric 2 meta | **judge_reason** | judge가 그 점수를 준 이유 (반드시 함께 저장)         | LLM judge |

- judge는 `temperature=0`. `질문 + gold_files 실제 소스 + 봇답변`을 입력으로 받고,
  `must_include`/`must_not_include`를 힌트로 사용(환각 시 감점). 모범답안은 쓰지 않는다(소스가 ground truth).
- **project 질문**은 답이 여러 파일에 흩어져 `gold_files` 기반 Recall이 흔들리므로,
  Correctness 채점에서 `must_include` 커버리지 비중을 높인다. Recall은 참고 지표로만 본다.
- MRR / Hit@3 / Hit@5 는 나중에 랭킹 비교가 필요해지면 추가 (지금은 보류).

## 케이스 커버 (지표 분리의 이유)
- 검색 실패 + 운 좋은 정답 → Recall=0, Correct=5 → "검색이 망함"이 드러남
- 검색 성공 + 헛소리       → Recall=1, Correct=0 → "생성이 망함"이 드러남

## 로그 (분석 필수)
매 질문마다 retrieval 로그를 남긴다. 없으면 "왜 점수가 떨어졌지?" 분석이 불가능.
```json
{ "id": "...", "question": "...",
  "retrieved_files": ["...", "..."], "scores": [0.89, 0.84],
  "recall_at_k": 1.0, "hit_at_1": 0,
  "answer": "...", "correctness": 4, "judge_reason": "..." }
```

## 골드셋 (`eval/goldset/api_backend.jsonl`)
49문항. 한 줄 구조:
```json
{ "id": "auth-jwt-01", "intent": "code", "question": "...",
  "gold_files": ["api/services/auth.py"],   // Metric 1/1.5 채점 기준
  "gold_symbols": ["get_current_user"],       // 무결성 검증용 (코드에 존재 확인)
  "hop": "single",                            // single|multi|none → Recall AND/OR
  "difficulty": "medium",                     // easy|medium|hard → 개선효과는 hard에서 크게 보임
  "must_include": ["Authorization","Bearer"], // Metric 2 judge 힌트
  "must_not_include": ["자체 서명검증"] }       // Metric 2 환각트랩
```
분포: intent code 31 / project 14 / chat 4 · hop single 30 / multi 15 / none 4 ·
difficulty easy 12 / medium 26 / hard 11

`difficulty`로 난이도별 점수를 쪼개 본다 — path-embedding 같은 개선은 easy에선 변화 없고
hard에서만 크게 오를 수 있으므로, 평균만 보면 효과를 놓친다.

## 무결성 검증 (`eval/verify_goldset.py`)
배포 전 골드셋 자체를 검증:
- 모든 `gold_files`가 대상 레포에 실재 / 모든 `gold_symbols`가 해당 파일에 AST상 정의됨
- 스키마: intent/hop/difficulty enum, hop과 gold_files 개수 일관성, id 중복, 빈 question
현재: 49 레코드 · 파일 63 · 심볼 84 전부 통과.

## 컴포넌트
| 파일 | 역할 | 상태 |
|---|---|---|
| `eval/goldset/api_backend.jsonl` | 골드셋 (자) | ✅ |
| `eval/verify_goldset.py` | 골드셋 무결성/스키마 검증 | ✅ |
| `eval/run_eval.py` | 러너: 봇 호출 → Recall@K/Hit@1 산출 → 로그 저장 | ⬜ |
| `eval/judge.py` | Correctness judge (temp=0, score+reason) | ⬜ |
| `eval/results/` | 실험별 점수·로그 (v0, v1, …) | ⬜ |

## 개선 루프
```
v0 측정 → 약점 분석(난이도/intent/hop별 분해) → 레버 하나 변경 → 재측정 → 비교
   레버: embedding 모델 / chunking / top_k / 검색방식 / answer 프롬프트
```

## 로드맵
0. 환경 확보 ✅ · 1. 골드셋+검증 ✅ · 2. 채점 설계 확정 ✅
3. 러너+judge ⬜ · 4. Leadership 인덱싱 ⬜ · 5. v0 baseline ⬜ · 6. 개선 루프 ⬜
