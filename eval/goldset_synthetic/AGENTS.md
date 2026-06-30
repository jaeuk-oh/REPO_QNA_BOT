<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# goldset_synthetic

## Purpose
The **synthetic** evaluation suite — a precise grid of code-fact questions that systematically cover code units in the target repo's backend. Kept separate from the realistic `goldset/` and **excluded from `all.jsonl`**; preserved as an option for fine-grained coverage testing (tracked separately per eval design decision D13).

## Key Files
| File | Description |
|------|-------------|
| `api_backend.jsonl` | Synthetic backend goldset (~49 code-fact questions) covering the target repo's `api/` units |

## For AI Agents

### Working In This Directory
- Same record schema as `eval/goldset/` (`id`, `intent`, `question`, `gold_files`, `gold_symbols`, `hop`, `difficulty`, `must_include`, `must_not_include`) but **without** a `persona` field — so it is not merged by `build_goldset.py` into `all.jsonl`.
- To evaluate against this suite explicitly, pass it directly: `python -m eval.run_eval --goldset eval/goldset_synthetic/api_backend.jsonl --tag synthetic`.
- Validate with `verify_goldset.py` the same way as the realistic goldset (it tolerates the missing `persona` field — persona is only checked when present).
- Synthetic = exhaustive precision grid; realistic (`goldset/`) = real user phrasing/distribution. Track the two suites separately; don't merge their scores.

### Testing Requirements
- Run `verify_goldset.py` against this file + the target repo before using it for an eval.

## Dependencies

### Internal
- Optionally consumed by `eval/run_eval.py` via `--goldset`; validated by `eval/verify_goldset.py`.

<!-- MANUAL: -->
