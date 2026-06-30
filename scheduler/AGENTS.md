<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# scheduler

## Purpose
**Indexing orchestration** — decides *when* and *how much* to (re)index, then calls `ingestion`. Handles first-run full indexing, periodic incremental re-indexing (every `REINDEX_INTERVAL_DAYS`, default 2) via APScheduler, and tracks each repo's last-indexed commit SHA in `data/meta.json`.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | Public API barrel — re-exports `reindex_all`, `reindex_repo`, `start_scheduler`, `initial_index_if_empty` |
| `reindexer.py` | `meta.json` load/save (atomic, lock-guarded), `initial_index_if_empty` (full index on first run), `reindex_repo` (incremental with full-reindex fallbacks), `reindex_all` (per-repo error isolation), `start_scheduler` (APScheduler interval job) |

## For AI Agents

### Working In This Directory
- **SHA-driven incremental logic** (`reindex_repo`): pull → if collection empty or no recorded SHA → full index; if SHA unchanged → skip; otherwise `git diff` the changed files, filter to `CODE_EXTENSIONS`, and incrementally index. If the diff can't be computed (shallow clone / unreachable SHA) it falls back to a full reindex.
- **`meta.json` is the source of truth** for "what's indexed." Writes go through `_update_meta`, which is `threading.Lock`-guarded and atomic (write to `.tmp` then `os.replace`). Keep updates atomic — concurrent reindex + initial-index can race otherwise.
- `reindex_all` wraps each repo in try/except so one repo's failure doesn't abort the batch; failures are logged and returned as `{"status": "error", ...}` (note: no external alerting yet — see README status).
- The scheduler uses `coalesce=True, max_instances=1` so overlapping/backed-up runs collapse into one — don't remove this without considering concurrent indexing.
- `initial_index_if_empty` is called synchronously from `main.py` *before* bots start (and also by `eval/run_eval.py`), so bots never serve an empty index.

### Testing Requirements
- No unit tests. The branching in `reindex_repo` (full / skip / incremental / fallback) is the highest-value test target — can be tested with a small local git repo and a temp ChromaDB dir.

### Common Patterns
- Return values are status dicts (`{"repo", "status", ...}`) used for logging and could feed future alerting.
- All heavy lifting is delegated to `ingestion`; this module only orchestrates and persists state.

## Dependencies

### Internal
- `config` / `RepoConfig` / `META_PATH` — repo identity, `REINDEX_INTERVAL_DAYS`, `CODE_EXTENSIONS`
- `ingestion` — `clone_or_pull`, `changed_files`, `file_exists_at`, `full_index`, `incremental_index`, `get_collection`

### External
- `apscheduler` — `BackgroundScheduler` (interval trigger)

<!-- MANUAL: -->
