<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# ingestion

## Purpose
The **indexing pipeline** — turns a GitHub repo into searchable vectors. It clones/pulls the repo, walks code files, splits them into language-aware chunks, embeds them with `text-embedding-3-small`, and upserts them into the repo's ChromaDB collection. Supports both full and incremental (changed-files-only) indexing. Driven by `scheduler/`; queried by `agent/retriever.py`.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | Public API barrel — re-exports `clone_or_pull`, `changed_files`, `get_head_sha`, `file_exists_at`, `Chunk`, `chunk_repo`, `chunk_files`, `get_collection`, `full_index`, `incremental_index`, `delete_file_chunks`, `embed_texts` |
| `cloner.py` | Git operations via GitPython: `clone_or_pull` (fresh clone or pull, hard-resets on divergence), `changed_files` (diff `old..new`), `get_head_sha`, `file_exists_at` |
| `chunker.py` | `Chunk` dataclass + language-aware splitting (`RecursiveCharacterTextSplitter.from_language`). `iter_code_files` filters by extension/size/skip-dirs; `chunk_repo` (whole repo) and `chunk_files` (specific paths) produce chunks with stable ids and metadata |
| `embedder.py` | ChromaDB client cache + `get_collection` (cosine space), batched `embed_texts` (retry on rate-limit/connection errors), `index_chunks` (upsert), `delete_file_chunks`, `full_index`, `incremental_index` |

## For AI Agents

### Working In This Directory
- **Chunk id is the stable key**: `f"{repo_name}::{rel_path}::{chunk_index}"`. Metadata carries `repo`, `file_path`, `chunk_index`, `language`. The `file_path` metadata is what retrieval and the eval harness key on — don't change its meaning without updating `agent/retriever.py` and `eval/`.
- **Full vs incremental**: `full_index` deletes and recreates the collection. `incremental_index` deletes chunks for changed files (by `file_path` `$in`) then re-embeds the files that still exist (deletions handled by absence). The split between deletions and upserts is by filesystem existence.
- File selection rules live in `chunker.iter_code_files` and `config`: only `CODE_EXTENSIONS`, skip `SKIP_DIRS`, skip symlinks, skip files > 1 MB, skip non-UTF-8 and empty files.
- Language mapping (`_LANG_MAP` in `chunker.py`) covers common languages; unmapped extensions fall back to a plain character splitter.
- Embedding is batched (`_EMBED_BATCH = 100`) with exponential backoff (`_MAX_RETRIES = 5`); after exhausting retries it raises `RuntimeError` — callers (scheduler) treat that as a failed reindex.

### Testing Requirements
- No unit tests yet. `chunk_repo` and `iter_code_files` are good first targets (pure, filesystem-driven). Validate indexing end-to-end via `eval/run_eval.py` (which calls `initial_index_if_empty`).

### Common Patterns
- ChromaDB `PersistentClient`s are cached per directory in `_chroma_clients` to avoid re-opening.
- Collections always use `metadata={"hnsw:space": "cosine"}`; keep this consistent with the distance→similarity conversion in `agent/retriever.py`.

## Dependencies

### Internal
- `config` — `CHUNK_SIZE`, `CHUNK_OVERLAP`, `CODE_EXTENSIONS`, `SKIP_DIRS`, `EMBEDDING_MODEL`, `OPENAI_API_KEY`

### External
- `gitpython` — clone/pull/diff
- `langchain-text-splitters` — `RecursiveCharacterTextSplitter`, `Language`
- `chromadb` — persistent vector store
- `openai` — embeddings (with `RateLimitError` / `APIConnectionError` handling)

<!-- MANUAL: -->
