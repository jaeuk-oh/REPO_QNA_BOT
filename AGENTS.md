<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# QnA_BOT_INHOUSE

## Purpose
A Slack bot that answers questions about in-house codebases using RAG. A user mentions a per-repo bot in Slack; the bot classifies intent (`chat` / `project` / `code`), retrieves similar code chunks from a local ChromaDB vector store, and asks GPT-4o-mini to generate an answer — structured (pattern / rationale / pros / cons / confidence / file refs) for `code` questions, natural language for `project` and `chat`. One independent bot runs per registered repo, each over its own Slack app and ChromaDB collection. Repos are cloned and embedded on first run, then incrementally re-indexed every 2 days via `git diff`.

## Key Files
| File | Description |
|------|-------------|
| `main.py` | Entry point. Starts a health-check HTTP server (for Render port scan), runs initial indexing, launches one Socket Mode thread per repo, and starts the reindex scheduler |
| `config.py` | Central config: paths, model names, chunking params, `RepoConfig` dataclass, the `_REPO_DEFINITIONS` repo registry, and env-var loading/validation |
| `requirements.txt` | Python dependencies (openai, chromadb, slack_bolt, apscheduler, gitpython, langchain-text-splitters, pydantic, tiktoken) |
| `Dockerfile` | Python 3.11-slim image; installs gcc/g++/git (needed by chromadb/hnswlib + gitpython) then runs `python main.py` |
| `render.yaml` | Render deploy config: background worker + 5GB persistent disk mounted at `/app/data`; all secrets injected via dashboard (`sync: false`) |
| `README.md` | Project rationale, architecture diagram, tech-stack tradeoffs, setup, and current status |
| `DECISIONS.md` | Detailed design decisions and tradeoffs |
| `plan.md` | Working plan / notes |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `agent/` | RAG query side: intent classification, retrieval, answer generation, Slack formatting (see `agent/AGENTS.md`) |
| `ingestion/` | Indexing pipeline: git clone/pull, code chunking, embedding + ChromaDB upsert (see `ingestion/AGENTS.md`) |
| `slackbot/` | Slack Socket Mode event handling and per-mention background processing (see `slackbot/AGENTS.md`) |
| `scheduler/` | Initial + incremental re-indexing orchestration on an APScheduler interval (see `scheduler/AGENTS.md`) |
| `eval/` | Offline RAG evaluation framework: goldsets, runner, LLM-as-judge (see `eval/AGENTS.md`) |
| `data/` | Runtime data store: cloned repos, ChromaDB indexes, indexing metadata (gitignored; see `data/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- **Registering a new repo/bot**: add a `(name, github_url)` tuple to `_REPO_DEFINITIONS` in `config.py` and provide three env vars per repo — `SLACK_BOT_TOKEN_<name>`, `SLACK_APP_TOKEN_<name>`, `SLACK_SIGNING_SECRET_<name>` (signing secret is optional under Socket Mode). For Render, also add the keys to `render.yaml` with `sync: false`.
- Each module exposes its public API via its `__init__.py` — import from the package (`from agent import retrieve, answer`), not deep paths.
- The data flow is one-directional: `ingestion` writes to ChromaDB; `agent.retriever` reads from it; `scheduler` drives `ingestion`; `slackbot` drives `agent`.
- All user-facing bot answers are in Korean (enforced via system prompts in `agent/answerer.py`); code, identifiers, and logs are in English.
- Secrets live only in `.env` / Render env vars — never commit tokens or `OPENAI_API_KEY`.

### Testing Requirements
- No unit test suite yet (see README "현재 상태"). The `eval/` framework is the closest thing to integration testing — it exercises `classify_intent → retrieve → answer*` headlessly (Slack excluded) against a goldset.
- Manual smoke test: set env vars, `python main.py`, wait for `All bots running.`, then mention a bot in Slack.

### Common Patterns
- `RepoConfig` (frozen dataclass) is the unit of identity: `clone_dir`, `chroma_dir`, `collection_name`, `display_name` are all derived properties.
- LLM calls are wrapped in try/except with logging and a safe fallback (never raise into the Slack handler).
- ChromaDB uses cosine space; cosine distance `[0,2]` is converted to similarity `[0,1]` in `agent/retriever.py`.

## Dependencies

### External
- **OpenAI** — `gpt-4o-mini` (intent + answers), `text-embedding-3-small` (embeddings), `gpt-4o` (eval judge)
- **chromadb** — local persistent vector store
- **slack_bolt / slack_sdk** — Slack Socket Mode (no public URL required)
- **apscheduler** — background reindex scheduling
- **gitpython** — clone/pull + diff for incremental indexing
- **langchain-text-splitters** — language-aware code chunking
- **pydantic** — structured LLM output schemas

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
