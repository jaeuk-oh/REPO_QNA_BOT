<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# eval

## Purpose
Offline **RAG evaluation framework** — measures the bot's retrieval and generation quality against a curated goldset, so changes (chunking / top_k / embedding / prompts) can be compared causally. It replays the bot pipeline headlessly (everything except Slack): `classify_intent → retrieve(top_k=5) → answer*/answer_project/answer_general → judge(gpt-4o)`. Retrieval and generation are scored **separately** and broken down by persona / intent / difficulty / hop. Default target repo is `REPO_A`.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | Package marker (docstring only) |
| `run_eval.py` | The runner. Indexes (once) → runs each goldset record → computes Recall@5 / AllFound@5 / Hit@1 / IntentAcc + judge Correctness → aggregates overall + per-axis → writes `results/<tag>/` (`per_question.jsonl`, `summary.json`, `summary.md`). CLI: `--tag`, `--goldset`, `--repo`, `--top-k`, `--limit`, `--no-index` |
| `judge.py` | LLM-as-judge. `judge_answer` scores an answer 0–5 with `gpt-4o` (one tier above the bot's `gpt-4o-mini` to avoid self-preference), `temperature=0`, structured output (`JudgeResult`). Uses curated reference facts + forbidden-claim traps; caps score at 1 on any violation |
| `build_goldset.py` | Merges per-persona `goldset/*.jsonl` into `goldset/all.jsonl` (the eval input), validates persona/filename consistency and id uniqueness, and prints axis distributions. `--check` validates without writing |
| `verify_goldset.py` | Integrity checker: every `gold_files` exists in the target repo and every `gold_symbols` is actually defined (Python via AST; other languages via text substring). Also validates schema/enums and hop↔gold_files-count consistency |
| `README.md` | How to build/verify/run the eval and read the metrics |
| `DESIGN.md` | Fixed design doc — principles, metric definitions, goldset schema, scope |
| `DECISIONS.md` | Evaluation design decisions log |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `goldset/` | Per-persona realistic goldsets (`*.jsonl`) + the built `all.jsonl` (eval input) (see `goldset/AGENTS.md`) |
| `goldset_synthetic/` | Synthetic code-fact suite (`api_backend.jsonl`), kept optional and excluded from `all.jsonl` (see `goldset_synthetic/AGENTS.md`) |
| `results/<tag>/` | Per-run outputs (`per_question.jsonl`, `summary.json`, `summary.md`); created at runtime, not tracked here |

## For AI Agents

### Working In This Directory
- **The ruler is fixed**: goldsets and scoring rules must not change between runs, or cross-run score comparisons become meaningless. To improve the bot, change *one* lever in the bot (not the eval), re-run with a new `--tag`, and diff `summary.md`.
- **Metrics are deliberately separated**: Recall/AllFound/Hit@1 measure *retrieval* (deterministic); Correctness measures *generation* (LLM judge). Never collapse them into one number — the split is what localizes a regression to retrieval vs generation.
- `hop="none"` (no retrieval needed) records report retrieval metrics as `None` (N/A) and are excluded from those averages.
- Goldset record schema (one JSON object per line): `id`, `intent` (code/project/chat), `question`, `gold_files`, `gold_symbols`, `hop` (single/multi/none), `difficulty` (easy/medium/hard), `must_include`, `must_not_include`, and (in `all.jsonl`) `persona`. `hop` must match the `gold_files` count.
- Run order: `build_goldset.py` → `verify_goldset.py` → `run_eval.py`. The runner auto-indexes the target repo on first run unless `--no-index`.
- Requires `OPENAI_API_KEY` (retrieval, answers, and judge all hit OpenAI). Runner exits non-zero if it's unset.

### Testing Requirements
- This *is* the integration-test harness for the RAG pipeline. Validate the goldset itself with `verify_goldset.py` before trusting eval numbers. Use `--limit 5` for a fast smoke run.

### Common Patterns
- The runner imports the real bot functions from `agent` (and `scheduler.reindexer.initial_index_if_empty`) — it tests the production code path, not a copy.
- `sys.path` is prepended with the repo root so both `python -m eval.run_eval` and `python eval/run_eval.py` work.
- Judge has a safety net: if `violations` are reported but score > 1, it's forced down to 1.

## Dependencies

### Internal
- `config` — `OPENAI_API_KEY`, repo registry, `ensure_dirs`
- `agent` — `retrieve`, `classify_intent`, `answer`, `answer_project`, `answer_general`, `StructuredAnswer`
- `scheduler.reindexer` — `initial_index_if_empty`

### External
- `openai` — judge (`gpt-4o`) via structured-output parse
- `pydantic` — `JudgeResult` schema
- `ast` (stdlib) — symbol verification in `verify_goldset.py`

<!-- MANUAL: -->
