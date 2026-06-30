# 평가 프레임워크 결정 기록 (왜 그렇게 골랐는가)

각 항목: **결정 / 이유 / 기각한 대안**. 나중에 "왜 이렇게 했지?"를 다시 묻지 않기 위해 남긴다.

---

### D1. Slack을 우회하고 함수를 직접 호출한다
- **결정**: 평가는 `retrieve()` + `answer*()`를 직접 호출하고 Slack 토큰/소켓을 쓰지 않는다.
- **이유**: 평가 대상은 "전송 직전 답변"이고 Slack 전송은 부수효과일 뿐이다. 우회하면
  토큰·워크스페이스 없이 실험을 빠르게 반복할 수 있고, 측정 경로가 운영과 동일해 신뢰성도 유지된다.
- **기각**: 실제 Slack 통합 테스트 → 느리고 비결정적, 외부 의존성 추가. 평가 가치 없음.

### D2. 검색과 생성을 분리해 측정한다
- **결정**: 단일 점수 대신 Retrieval 지표와 Generation 지표를 따로 낸다.
- **이유**: 봇이 틀릴 때 원인은 "검색이 못 찾음" 또는 "찾았는데 못 씀" 둘 중 하나다. 단일 점수는
  어느 쪽인지 못 알려줘서 개선 레버를 못 고른다. 분리해야 "top_k를 올렸더니 Recall만 올랐다" 같은
  인과 결론이 가능하다.
- **기각**: end-to-end accuracy 하나만 → 원인 추적 불가. 개선 실험의 의미가 사라짐.

### D3. 핵심 지표는 2개로 고정한다 (Recall@K + Correctness 0~5)
- **결정**: faithfulness/quality 등을 따로 만들지 않고 2개로 간다. Correctness는 0~5 단계점수.
- **이유**: 개인 프로젝트 규모에서 지표가 많으면 유지비용만 늘고 해석이 흐려진다. "완전성/명확성"은
  0~5 단계점수가 흡수한다(불완전=3, 완벽=5). 환각은 Correctness 감점으로 반영.
- **기각**: 다축 지표(별도 Quality/Hallucination 점수) → 과설계. 단, Hit@1만은 랭킹 품질용으로 추가(D8).

### D4. gold_files는 코드 사실이며 AST로 검증한다
- **결정**: 정답 파일/심볼을 코드에서 뽑고, `verify_goldset.py`가 실재를 기계 검증한다.
- **이유**: LLM이나 사람이 골드셋을 쓰면 없는 파일/함수를 적는 환각이 난다. 검증 없이 쓰면 평가의
  기준 자체가 틀린다. 덤으로 코드 리팩터링으로 심볼이 바뀌면 골드셋이 깨졌다고 알려주는 회귀 감지기가 된다.
- **기각**: LLM이 생성한 골드를 그대로 신뢰 → 검증 안 된 기준은 못 쓴다.

### D5. 모범답안(gold answer)을 쓰지 않는다 (reference-free judge)
- **결정**: judge에게 `질문 + 정답파일 실제 소스 + 봇답변`을 주고 채점. 미리 쓴 정답 텍스트 없음.
- **이유**: 손으로 쓴 모범답안은 그 자체가 틀릴 수 있고, 코드가 바뀌면 낡는다. 소스 코드가
  변하지 않는 ground truth다.
- **기각**: 문항마다 gold_answer 작성 → 작성비용 + 오류/노후 위험.

### D6. must_include는 정확매칭이 아니라 judge 힌트로 쓴다
- **결정**: `must_include`/`must_not_include`를 judge에게 주는 참고 신호로만 사용.
- **이유**: 정확 문자열 매칭이면 "10" 대신 "열 번"이라 답해도 오답 처리돼 억울하다. 의미 채점이 맞다.
  `must_not_include`는 환각트랩으로 judge가 감점 근거로 쓴다.
- **기각**: exact string match → 표현 다양성에 취약, 거짓 감점.

### D7. hop 라벨로 Recall의 AND/OR를 레코드별로 정한다
- **결정**: `hop: single|multi|none`. multi는 모든 gold_files가 검색돼야 정답(AND).
- **이유**: 진짜 멀티홉 질문(로직+상수가 다른 파일)은 일부만 찾으면 답할 수 없으므로 AND가 공정하다.
  통짜 규칙은 단일홉을 과하게 깎거나 멀티홉을 과하게 봐준다.
- **기각**: 전체 AND 또는 전체 OR 고정 → 문항 성격을 무시.

### D8. 리뷰 피드백 4개를 추가한다 (Hit@1 / judge_reason+temp0 / retrieval log / difficulty)
- **Hit@1**: Recall@K는 정답이 꼴찌로 와도 1점이라 랭킹 품질을 못 본다 → 1순위 여부를 따로 본다.
- **judge_reason + temperature=0**: LLM judge는 같은 답에 4→3→5로 흔들린다 → 온도 0으로 고정하고
  점수와 함께 이유를 저장해 사후 검증/디버깅을 가능하게 한다.
- **retrieval log**: 검색파일+유사도점수를 매 질문 저장 → "왜 점수가 떨어졌지?" 분석의 전제. 없으면 분석 불가.
- **difficulty(easy/medium/hard)**: path-embedding 같은 개선은 easy에선 변화 없고 hard에서만 크게
  오를 수 있다 → 난이도별로 쪼개 봐야 효과를 안 놓친다.

### D9. 골드셋 범위는 api/ 백엔드, 규모는 49문항
- **결정**: 대상은 Python `api/` 18파일. 31→49로 확대, project 문항 6→14.
- **이유**: 백엔드는 AST 심볼 검증이 정밀해 골드 신뢰도가 높다(사용자 선택). project가 6개뿐이면
  summary index 같은 변경 시 평가가 통계적으로 흔들리므로 보강.
- **기각**: 프론트(TSX)까지 포함 → grep 기반이라 검증 정밀도↓, 수작업↑. 31문항 유지 → project 표본 부족.

### D10. project 질문은 Recall보다 must_include 비중을 높인다
- **결정**: project 채점은 Correctness의 must_include 커버리지를 주신호로, Recall은 참고로 본다.
- **이유**: "인증 구조 설명"류는 답이 여러 파일에 흩어져, 정답파일을 다 못 찾아도 옳은 답이 나올 수 있다
  (Recall=0, Correct=5 가능). gold_files만으로 평가하면 공정하지 않다.
- **기각**: 모든 intent에 동일한 Recall 가중 → project에서 거짓 감점.

### D11. 범위를 전체 레포로 확장한다 (D9를 대체)
- **결정**: 골드셋 범위를 api/ 백엔드 → frontend(web/src) + docs + backend 전체로 확장.
- **이유**: 실제 Slack에 올라올 질문의 절반이 프론트(스트리밍 표시·인사 중복·로그인)·배포·인시던트
  영역이다. 백엔드만 보면 실사용 분포를 대표하지 못한다. 사용자가 큐레이션한 50문항이 그 분포를 반영.
- **기각**: D9(백엔드만) 유지 → 큐레이션된 현실 질문의 절반을 버리게 됨. AST 정밀도는 D12로 보완.

### D12. 검증은 언어별로 다른 방식을 쓴다 (py=AST, 그 외=텍스트)
- **결정**: `verify_goldset.py`가 .py는 AST로 심볼을 정밀 검증, TS/TSX/md/sql은 원문 substring 존재로 검증.
- **이유**: 비-Python 파일은 Python AST로 못 판다. 그래도 "파일 존재 + 핵심 토큰 존재"는 확인해야
  환각 골드를 막는다. 단, 이 보증은 AST보다 약하다는 점을 명시(텍스트 일치는 정의 여부를 보장 못 함).
- **한계 메모**: AST는 함수 **파라미터**를 심볼로 잡지 않는다(예: conversation_summary). gold_symbols는
  def/class/모듈상수에 앵커하고, 파라미터·세부 토큰은 must_include(judge 힌트)로 둔다.

### D13. 합성 suite와 현실 suite를 분리 운영한다
- **결정**: `api_backend.jsonl`(합성, 코드사실 49) + `realistic_{backend,frontend,docs}.jsonl`(현실, 50)로 공존.
- **이유**: 둘의 목적이 다르다. 합성은 코드 단위 기능을 빠짐없이 덮는 정밀 격자, 현실은 실제 사용자
  표현·분포로 체감 성능을 측정. 분리하면 "코드커버리지 점수"와 "실사용 점수"를 따로 추적할 수 있다.
- **기각**: 하나로 병합 → 개념 중복·목적 혼재로 두 신호가 섞임.

### D14. 골드셋을 직무(persona)별 파일로 저장하고 all.jsonl로 합쳐 평가한다 (D13 갱신)
- **결정**: 현실 50문항을 12개 직무 파일(backend/frontend/qa/onboarding/pm/cs/analytics/devops/
  incident/performance/refactoring/navigation)로 분리, 각 레코드에 `persona` 태그. `build_goldset.py`가
  이들을 `goldset/all.jsonl`로 합치고 평가는 통합본 기준으로 돈다. 합성 suite는 `goldset_synthetic/`로
  옮겨 all.jsonl에서 제외(옵션 보존).
- **이유**: 직무 태그가 있으면 평가 후 persona/난이도/intent/hop 어느 축으로든 점수를 쪼개 약점을 짚을 수
  있다("incident 41% vs navigation 91%"). 직무별 추가/관리도 파일 단위라 쉽다.
- **기각**: 영역(backend/frontend/docs) 3분할 → 직무 분해 불가. 단일 파일 → 추가·리뷰 단위가 거칠다.

### D15. K=5, judge=gpt-4o, intent는 예측값으로 디스패치한다
- **결정**: Recall@K·Hit@1의 K=5(=상위 5 chunk를 파일집합으로 환원, 봇 실제 컨텍스트와 동일).
  Correctness judge는 `gpt-4o`(temp=0, structured output). 핸들러는 `classify_intent` **예측값**으로
  디스패치하고, gold intent와 비교해 **IntentAcc**를 별도 지표로 기록.
- **이유**: judge가 채점 대상(gpt-4o-mini)보다 강해야 self-preference 편향을 피한다. 예측 intent로 돌려야
  라우팅 오류까지 포함한 진짜 엔드투엔드를 측정하고, intent 정확도도 공짜로 얻는다.
- **기각**: gold intent로 디스패치 → 라우팅 버그를 못 본다. judge=gpt-4o-mini → 자기 답 후하게 봄.

### D16. 검색 경로 정규화는 불필요하다 (코드로 확인)
- **결정**: 별도 경로 매핑 레이어를 두지 않는다.
- **이유**: `chunker.py:80`이 `relative_to(clone_dir).as_posix()`로 레포루트 기준 POSIX 경로를 저장하고
  `retriever.py:43`이 그대로 노출한다 → gold_files 형식(`api/…`, `web/src/…`, `docs/…`)과 글자 그대로 일치.
  러너는 `chunk.file_path`를 모아 중복제거만 하면 된다.
- **한계 메모**: 평가용 클론이 동일한 최상위 레이아웃(api/·web/·docs/)을 유지한다는 전제. cloner가 레포
  루트를 그대로 클론하므로 충족.
