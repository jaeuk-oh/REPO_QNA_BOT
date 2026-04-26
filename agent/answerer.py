import logging
from openai import OpenAI
from pydantic import BaseModel, Field

import config
from .retriever import RetrievedChunk

logger = logging.getLogger(__name__)

_openai = OpenAI(api_key=config.OPENAI_API_KEY)

_INTENT_SYSTEM = (
    "Classify the user's message into exactly one of: 'code', 'project', 'chat'.\n"
    "'code'    = questions about a specific function, bug, implementation, file, or class.\n"
    "'project' = questions about what the project does, its purpose, architecture, tech stack, or overall structure.\n"
    "'chat'    = greetings, small talk, or anything completely unrelated to the repository.\n"
    "Reply with exactly one word: code, project, or chat."
)

_CHAT_SYSTEM_TEMPLATE = (
    "You are a helpful assistant for the `{repo_name}` repository ({repo_url}), "
    "embedded in a Slack workspace. "
    "Respond naturally and concisely in Korean."
)

_PROJECT_SYSTEM_TEMPLATE = (
    "You are an expert on the `{repo_name}` repository ({repo_url}). "
    "Answer the user's question using the provided code context. "
    "Respond naturally in Korean — no need for bullet-point structure, just a clear explanation."
)


def classify_intent(question: str) -> str:
    """Returns 'code', 'project', or 'chat'."""
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
        if label in ("code", "project", "chat"):
            return label
        return "code"
    except Exception:
        logger.exception("Intent classification failed; defaulting to 'code'")
        return "code"


def answer_general(question: str, repo_name: str = "", repo_url: str = "") -> str:
    """Natural-language reply for chat messages, no RAG."""
    system = _CHAT_SYSTEM_TEMPLATE.format(repo_name=repo_name, repo_url=repo_url)
    try:
        resp = _openai.chat.completions.create(
            model=config.CHAT_MODEL,
            temperature=0.7,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        logger.exception("General answer failed")
        return "죄송해요, 잠시 문제가 생겼어요. 다시 시도해 주세요."


_MAX_CONTEXT_CHARS = 12_000


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


def answer_project(
    question: str,
    chunks: list[RetrievedChunk],
    repo_name: str,
    repo_url: str,
) -> str:
    """Natural-language reply for project-level questions, with RAG context."""
    if not chunks:
        return f"`{repo_name}` 레포에 대한 정보를 찾지 못했어요. 인덱싱이 완료됐는지 확인해 주세요."

    context = build_context(chunks)
    system_msg = _PROJECT_SYSTEM_TEMPLATE.format(repo_name=repo_name, repo_url=repo_url)
    user_msg = f"Code context:\n\n{context}\n\nQuestion: {question}"

    try:
        resp = _openai.chat.completions.create(
            model=config.CHAT_MODEL,
            temperature=0.3,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        logger.exception("Project answer failed")
        return "죄송해요, 프로젝트 정보를 가져오는 중 문제가 생겼어요."


class StructuredAnswer(BaseModel):
    pattern: str = Field(description="What pattern / approach is used in the code")
    rationale: str = Field(description="Why this pattern was likely chosen")
    pros: list[str]
    cons: list[str]
    best_for: str = Field(description="When/where this pattern is most appropriate")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0.0–1.0")
    code_refs: list[str] = Field(description="Relative file paths referenced")


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
)


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
            max_tokens=2048,
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
        )
