<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# agent

## Purpose
The RAG **query side** of the bot — everything that happens after a user asks a question. It classifies intent, retrieves similar code chunks from ChromaDB, generates an answer with GPT-4o-mini, and formats `code`-intent answers into Slack Block Kit. This package only *reads* from the vector store; writing/indexing lives in `ingestion/`.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | Public API barrel — re-exports `retrieve`, `RetrievedChunk`, `answer`, `answer_project`, `answer_general`, `classify_intent`, `StructuredAnswer`, `to_blocks`, `to_fallback_text` |
| `answerer.py` | Intent classification (`classify_intent`) + three answer paths: `answer_general` (chat, no RAG), `answer_project` (RAG + natural language), `answer` (RAG + `StructuredAnswer` Pydantic schema). Also `build_context` (chunk → prompt context, capped at ~12k chars) |
| `retriever.py` | `retrieve()` — embeds the query, queries the repo's ChromaDB collection (top_k), and returns `RetrievedChunk` objects with a cosine-distance→similarity score |
| `formatter.py` | Converts a `StructuredAnswer` into Slack Block Kit blocks (`to_blocks`) and a plaintext fallback (`to_fallback_text`); HTML-escapes user-facing text |

## For AI Agents

### Working In This Directory
- **Three intents, three answer shapes**: `chat` → `answer_general` (no retrieval), `project` → `answer_project` (natural language over RAG context), `code` → `answer` (returns a `StructuredAnswer`). The Slack handler dispatches on `classify_intent`'s label.
- `classify_intent` defaults to `"code"` on any ambiguity or API failure — keep that fail-safe behavior.
- `StructuredAnswer` is produced via `openai.beta.chat.completions.parse` with `response_format=StructuredAnswer`. The system prompt forbids fabricating file paths and requires `confidence < 0.4` when context is insufficient — preserve these guardrails when editing prompts.
- Every answer function catches exceptions and returns a safe fallback (string or a degraded `StructuredAnswer`); never let an LLM error propagate to the Slack thread.
- All answers must be in Korean (enforced in system prompts).

### Testing Requirements
- No unit tests yet. Exercise these functions through `eval/run_eval.py`, which calls `classify_intent`, `retrieve`, and the `answer*` functions directly (headless, no Slack).
- When changing prompts or retrieval, re-run the eval (`python -m eval.run_eval --tag <new>`) and compare against the prior tag's `summary.md` — separately watch Recall (retrieval) vs Correctness (generation).

### Common Patterns
- `build_context` formats each chunk as a `### file: <path> (score=…)` block and stops before exceeding `_MAX_CONTEXT_CHARS` (12,000).
- Scores are similarities in `[0,1]` (higher = closer), already converted from ChromaDB cosine distance in `retriever.py`.
- A single shared `OpenAI` client is instantiated at module load from `config.OPENAI_API_KEY`.

## Dependencies

### Internal
- `config` — model names (`CHAT_MODEL`), `OPENAI_API_KEY`, `TOP_K`
- `ingestion.embedder` — `embed_texts`, `get_collection` (used by `retriever`)

### External
- `openai` — chat completions, structured-output parse, embeddings
- `pydantic` — `StructuredAnswer` schema
- `html` (stdlib) — escaping in `formatter`

<!-- MANUAL: -->
