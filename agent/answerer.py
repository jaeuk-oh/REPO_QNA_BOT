import logging
from openai import OpenAI
from pydantic import BaseModel, Field

import config
from .retriever import RetrievedChunk

logger = logging.getLogger(__name__)

_openai = OpenAI(api_key=config.OPENAI_API_KEY)

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
    "Never fabricate file paths; only cite paths that appear in the context."
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
