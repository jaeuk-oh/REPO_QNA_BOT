<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# data

## Purpose
Runtime data store — **generated at runtime, not source**. Holds cloned repos, the ChromaDB vector indexes, and the indexing metadata. In production this path is a Render Persistent Disk mounted at `/app/data` (see `render.yaml`). All contents except `.gitkeep` are gitignored.

## Key Files & Subdirectories
| Path | Description |
|------|-------------|
| `.gitkeep` | Keeps the otherwise-empty directory in version control |
| `repos/<REPO_NAME>/` | Per-repo git clones, created by `ingestion.cloner.clone_or_pull` (each repo's `clone_dir`) |
| `chroma/<REPO_NAME>/` | Per-repo ChromaDB `PersistentClient` storage (each repo's `chroma_dir`); cosine-space collections |
| `meta.json` | Maps `repo_name → last-indexed commit SHA`; written atomically by `scheduler.reindexer` |

## For AI Agents

### Working In This Directory
- **Do not edit anything here by hand** and do not commit its contents — it's reproducible from the repo registry in `config.py`. Paths are defined by `config.DATA_DIR` / `REPOS_DIR` / `CHROMA_DIR` / `META_PATH` and the `RepoConfig.clone_dir` / `chroma_dir` properties.
- To force a full re-index, delete the relevant `chroma/<REPO>/` directory (or remove the repo's entry from `meta.json`); the next run will rebuild it.
- The `repos/` subtree contains *external cloned repositories* (the bot's index targets), not part of this project — they are deliberately excluded from this AGENTS.md hierarchy.

### Testing Requirements
- Not applicable (runtime artifacts). Eval and local runs create a populated `data/` automatically.

## Dependencies

### Internal
- Written by `ingestion/` (clones, embeddings) and `scheduler/` (`meta.json`); read by `agent/retriever.py`.

<!-- MANUAL: -->
