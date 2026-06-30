# RAG 평가 프레임워크

repo Q&A 봇의 검색·생성 품질을 골드셋으로 측정한다. 봇 핸들러를 헤드리스로
재현(Slack만 제외)해 문항별로 검색·답변·채점을 돌리고, persona/난이도/intent/hop
축별로 점수를 분해한다.

## 구성

```
eval/
├── goldset/                  # 직무별 골드셋(현실 50문항) + 생성물 all.jsonl
│   ├── backend.jsonl … navigation.jsonl   # 12개 직무 파일 (각 레코드에 persona 태그)
│   └── all.jsonl             # build_goldset.py 생성물 — 평가는 이 파일 기준
├── goldset_synthetic/        # 합성 suite(코드사실 49) — all.jsonl 에서 제외, 옵션 보존
├── build_goldset.py          # 직무 파일 → all.jsonl 통합 + 분포 출력
├── verify_goldset.py         # gold_files 존재 + gold_symbols 정의(py=AST) 검증
├── run_eval.py               # 평가 러너 (검색→답변→judge→집계)
├── judge.py                  # gpt-4o LLM-as-judge (Correctness 0~5)
├── DESIGN.md / DECISIONS.md  # 설계·결정 기록
└── results/<tag>/            # 실행 산출물 (per_question.jsonl, summary.{json,md})
```

## 지표

| 지표 | 정의 |
|---|---|
| **Recall@5** | gold_files 가 상위 5개 chunk의 파일집합에 든 비율(부분점수) |
| **AllFound@5** | gold_files 전부가 검색됐는가 (multi-hop AND 충족) |
| **Hit@1** | 검색 1순위 파일이 gold_file 인가 |
| **Correctness** | gpt-4o judge 0~5 (must_include 충족 / must_not_include 위반 반영) |
| **IntentAcc** | classify_intent 예측이 gold intent 와 일치하는가 |

`hop="none"`(검색 불필요) 문항은 retrieval 지표를 N/A 처리한다.

## 실행

전제: `OPENAI_API_KEY` 설정, 의존성 설치(`requirements.txt`).

```bash
# 골드셋 빌드/검증
python eval/build_goldset.py
python eval/verify_goldset.py --goldset eval/goldset/all.jsonl --repo-root <Leadership 클론경로>

# 평가 (대상 레포는 처음 1회 자동 인덱싱됨)
python -m eval.run_eval --tag v0
python -m eval.run_eval --tag smoke --limit 5     # 빠른 점검
python -m eval.run_eval --tag v0 --no-index       # 이미 인덱싱된 경우
```

기본값: 대상 repo `REPO_A`(Leadership), `top_k=5`, judge `gpt-4o`.

## 개선 루프

`v0` 측정 → 약한 축 확인(예: navigation Recall 낮음) → 레버 하나 변경
(top_k/임베딩/청킹/프롬프트) → `v1` 재측정 → `summary.md` 축별 비교.
`per_question.jsonl`(검색파일·점수·답변·judge_reason)이 회귀 원인 추적의 근거다.
