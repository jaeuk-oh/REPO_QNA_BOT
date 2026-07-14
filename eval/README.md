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

## v0 baseline 기록 (2026-07-14) — "자와 대상을 먼저 정렬하라"

첫 v0 실행은 **점수가 아니라 방법론의 허점**을 먼저 드러냈다. 그 인과를 남긴다.

### 무슨 일이 있었나
처음 `run_eval --tag v0`를 `verify_goldset` 없이 돌렸더니 OVERALL Recall@5 0.26 / Correctness
1.52로 처참했다. 그런데 analytics·cs·qa·refactoring persona의 Recall이 **통째로 0.00** —
"임베딩이 약함"으로는 설명 안 되는 패턴이라 측정 자체를 의심했다.

### 근본 원인 (검색으로 확인)
1. **골드셋 ↔ 인덱스 버전 불일치**: 인덱싱된 클론이 초기 커밋 `5f74019`(4/19)에 고정돼 있었다.
   골드셋이 참조하는 `api/services/auth.py`, `api/services/limits.py`,
   `web/src/app/auth/callback/route.ts` 등이 **이 커밋엔 존재하지 않았다**(원격 최신 `127171e1`(6/24)엔 존재).
   정답 파일이 인덱스에 없으면 검색이 아무리 좋아도 **Recall은 구조적으로 0** — 저 0.00들의 정체.
2. **인덱스 오염**: 대상 레포에 커밋돼 있던 `.omc/`(autopilot spec 등)가 `SKIP_DIRS`에 없고 `.md`가
   `CODE_EXTENSIONS`라 그대로 임베딩됐다. 정답 파일이 존재하는 문항조차 검색 상위를
   `README.md`·`.omc/autopilot/spec.md`·`docs/SETUP.md`가 차지해 실제 코드 파일을 밀어냈다.

→ 즉 저 점수는 "봇 성능"이 아니라 **(a) 봇 약점 + (b) 도달 불가능한 정답(측정 오류) + (c) 오염**이
뒤섞인 값. 프레임워크 원칙 "자(尺)는 고정"의 전제는 **자가 대상과 정렬돼 있을 것**인데 그게 깨져 있었다.

### 조치
- `config.SKIP_DIRS`에 `.omc`(+`.vscode`/`.idea`/`.pytest_cache`) 추가 → 오염원 제외
- REPO_A를 원격 최신 `127171e1`로 pull + **전체 재인덱싱**(337 chunks)
- `verify_goldset` 재실행 → 파일 72 · 심볼 66 **전부 통과**(정렬 확인) → 그 다음에 v0 재측정
- 무효 실행은 `results/v0_stale/`에 보존(인과 증거)

### 정렬 전후 (동일 골드셋·동일 채점, 인덱스만 정렬)
| 지표 | v0_stale(무효) | **v0(유효)** | Δ |
|---|---|---|---|
| Recall@5 | 0.26 | **0.50** | +0.24 |
| AllFound@5 | 0.20 | **0.41** | +0.21 |
| Hit@1 | 0.16 | **0.31** | +0.15 |
| Correctness(0-5) | 1.52 | **1.96** | +0.44 |
| IntentAcc | 0.44 | **0.44** | 0 |

**읽는 법**: 검색계 지표가 거의 2배 → 원래 저점의 상당 부분이 봇이 아니라 **정렬 오류**였다는 증거.
IntentAcc가 불변인 것도 인과적으로 맞다 — intent 분류는 인덱스와 무관하므로, 이건 이제 **진짜 약점**으로 확정된다.

### 유효 baseline이 가리키는 실약점 (다음 실험 우선순위)
- **IntentAcc 0.44** (라우팅이 절반 이상 오분류; hard 0.21, incident/performance/analytics 0.00) — 인덱스 무관, 순수 분류/프롬프트 문제.
- **hop=multi AllFound@5 0.22** (멀티파일 검색 취약) — DECISIONS #1·#5의 구조적 한계 실측.
- 유효값도 Correctness 1.96/5, Hit@1 0.31 — 봇 자체 개선 여지 실재(이제 깨끗하게 측정 가능).

### 교훈 (프로세스에 반영)
**`run_eval` 전에 `verify_goldset`을 반드시 통과시킨다.** 자와 대상이 정렬되지 않은 baseline은
개선 실험의 신호를 정렬 오류와 뒤섞어 판단 불능으로 만든다. 정렬은 실험의 전제조건이다.
