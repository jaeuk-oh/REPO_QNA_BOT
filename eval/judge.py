"""LLM-as-judge: 봇 답변의 정확성을 gpt-4o로 0~5점 채점한다.

채점 대상(봇)은 gpt-4o-mini이므로, judge는 한 단계 위인 gpt-4o를 쓴다
(동일 모델로 채점하면 self-preference 편향). temperature=0 + structured
output으로 결정성과 파싱 안정성을 확보한다.

judge에는 정답 코드 전문을 넣지 않고, 골드셋에 큐레이션된 '레퍼런스 사실'
(must_include / gold_symbols / gold_files / notes)과 환각 트랩
(must_not_include)을 준다. 이 사실들과의 일치 여부로 채점한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from openai import OpenAI

import config

_client = OpenAI(api_key=config.OPENAI_API_KEY)

JUDGE_MODEL = "gpt-4o"

_SYSTEM = """\
You are a strict grader for a code-repository Q&A bot. You are given a QUESTION,
a set of REFERENCE FACTS curated by a human (the ground truth), optional FORBIDDEN
CLAIMS (things that are factually wrong / hallucination traps), and the BOT ANSWER.

Score the BOT ANSWER from 0 to 5 on factual correctness relative to the REFERENCE FACTS:
  5 = fully correct; conveys all key reference facts; well grounded; no errors.
  4 = correct, but misses a minor point or is slightly vague.
  3 = partially correct; gets the main idea but omits or muddles a key fact.
  2 = mostly wrong or misses most key facts, with some correct fragments.
  1 = wrong, irrelevant, or unsupported.
  0 = wrong AND asserts a FORBIDDEN CLAIM (hallucination), or fabricates file paths / symbols.

HARD RULE: if the BOT ANSWER asserts any FORBIDDEN CLAIM, the score must be at most 1.
Judge only factual correctness against the reference — not writing style or language.
List which reference facts were satisfied and which forbidden claims (if any) were violated.
Give a one-sentence reason in Korean.
"""


class JudgeResult(BaseModel):
    score: int = Field(ge=0, le=5, description="0-5 correctness score")
    reason: str = Field(description="One-sentence justification, Korean")
    satisfied: list[str] = Field(default_factory=list, description="reference facts the answer got right")
    violations: list[str] = Field(default_factory=list, description="forbidden claims the answer asserted")


def _reference_block(record: dict) -> str:
    lines: list[str] = []
    if record.get("gold_files"):
        lines.append("Relevant files: " + ", ".join(record["gold_files"]))
    if record.get("gold_symbols"):
        lines.append("Relevant symbols: " + ", ".join(record["gold_symbols"]))
    if record.get("must_include"):
        lines.append("Facts the answer SHOULD convey:")
        lines += [f"  - {x}" for x in record["must_include"]]
    if record.get("notes"):
        lines.append("Grader notes: " + record["notes"])
    return "\n".join(lines) if lines else "(no structured reference; judge on general correctness)"


def judge_answer(record: dict, bot_answer: str) -> JudgeResult:
    forbidden = record.get("must_not_include") or []
    user = (
        f"QUESTION:\n{record['question']}\n\n"
        f"REFERENCE FACTS:\n{_reference_block(record)}\n\n"
        f"FORBIDDEN CLAIMS (must not be asserted):\n"
        + ("\n".join(f"  - {x}" for x in forbidden) if forbidden else "  (none)")
        + f"\n\nBOT ANSWER:\n{bot_answer}\n"
    )
    completion = _client.beta.chat.completions.parse(
        model=JUDGE_MODEL,
        temperature=0,
        response_format=JudgeResult,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    result = completion.choices[0].message.parsed
    if result is None:
        return JudgeResult(score=0, reason="judge 파싱 실패", satisfied=[], violations=[])
    # 안전망: 금지 주장 위반이 보고됐는데 점수가 높으면 캡
    if result.violations and result.score > 1:
        result.score = 1
    return result
