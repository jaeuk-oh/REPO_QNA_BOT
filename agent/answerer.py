import logging
from openai import OpenAI
from pydantic import BaseModel, Field

import config
from .retriever import RetrievedChunk

logger = logging.getLogger(__name__)

_openai = OpenAI(api_key=config.OPENAI_API_KEY)

_INTENT_SYSTEM = (
    "Classify the user's message as 'code' or 'general'.\n"
    "'code' = questions about a specific codebase, feature, function, bug, or technical detail.\n"
    "'general' = greetings, small talk, bot usage questions, or anything unrelated to code.\n"
    "Reply with exactly one word: code or general."
)

_GENERAL_SYSTEM = (
    "You are a helpful assistant embedded in a Slack workspace. "
    "Respond naturally and concisely in Korean."
)


def classify_intent(question: str) -> str:
    """Returns 'code' or 'general'."""
    try:
        resp = _openai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=5,
            messages=[
                {"role": "system", "content": _INTENT_SYSTEM},
                {"role": "user", "content": question},
            ],
        )
        label = resp.choices[0].message.content.strip().lower()
        return "code" if label == "code" else "general"
    except Exception:
        logger.exception("Intent classification failed; defaulting to 'code'")
        return "code"


def answer_general(question: str) -> str:
    """Natural-language reply for non-code messages, no RAG."""
    try:
        resp = _openai.chat.completions.create(
            model=config.CHAT_MODEL,
            temperature=0.7,
            messages=[
                {"role": "system", "content": _GENERAL_SYSTEM},
                {"role": "user", "content": question},
            ],
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        logger.exception("General answer failed")
        return "죄송해요, 잠시 문제가 생겼어요. 다시 시도해 주세요."

_MAX_CONTEXT_CHARS = 12_000


class StructuredAnswer(BaseModel):
    pattern: str = Field(description="What pattern / approach is used in the code")
    rationale: str = Field(description="Why this pattern was likely chosen")
    pros: list[str]
    cons: list[str]
    best_for: str = Field(description="When/where this pattern is most appropriate")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0.0–1.0")
    code_refs: list[str] = Field(description="Relative file paths referenced")
    snippets: list[str] = Field(description="Short code snippets, ≤20 lines each")


_SYSTEM_TEMPLATE = (
    "You are an expert on the `{repo_name}` codebase. "
    "Answer only using the provided code context. "
    "If the context is insufficient, explain why in `rationale` and set `confidence` below 0.4. "
    "Never fabricate file paths; only cite paths that appear in the context. "
    "Always respond in Korean."
)

_NO_RESULT_ANSWER = StructuredAnswer(
    pattern="No relevant code found",
    rationale="The search returned no matching code chunks for this question.",
    pros=[],
    cons=[],
    best_for="N/A",
    confidence=0.0,
    code_refs=[],
    snippets=[],
)


def build_context(chunks: list[RetrievedChunk]) -> str:
    parts: list[str] = []
    total = 0
    for chunk in chunks:
        block = f"### file: {chunk.file_path} (score={chunk.score:.2f})\n```\n{chunk.content}\n```"
        if total + len(block) > _MAX_CONTEXT_CHARS:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


def answer(
    question: str,
    chunks: list[RetrievedChunk],
    repo_name: str,
) -> StructuredAnswer:
    if not chunks:
        return _NO_RESULT_ANSWER

    context = build_context(chunks)
    system_msg = _SYSTEM_TEMPLATE.format(repo_name=repo_name)
    user_msg = f"Code context:\n\n{context}\n\nQuestion: {question}"

    try:
        completion = _openai.beta.chat.completions.parse(
            model=config.CHAT_MODEL,
            temperature=0.2,
            response_format=StructuredAnswer,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
        )
        result = completion.choices[0].message.parsed
        if result is None:
            raise ValueError("Structured output parsing returned None")
        return result
    except Exception as e:
        logger.exception("GPT-4o structured output failed: %s", type(e).__name__)
        return StructuredAnswer(
            pattern="Error generating answer",
            rationale=f"LLM call failed: {type(e).__name__}. Check server logs.",
            pros=[],
            cons=[],
            best_for="N/A",
            confidence=0.0,
            code_refs=[c.file_path for c in chunks],
            snippets=[],
        )
