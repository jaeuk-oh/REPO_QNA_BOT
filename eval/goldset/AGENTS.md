<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# goldset

## Purpose
The **realistic** evaluation goldset — questions phrased the way real users (across job functions / personas) would ask, used to measure perceived bot performance. Stored split by persona (one `*.jsonl` per persona); the runner consumes the merged `all.jsonl`.

## Key Files
| File | Description |
|------|-------------|
| `all.jsonl` | **The eval input.** Built by `eval/build_goldset.py` from all persona files; do not hand-edit (regenerate instead) |
| `backend.jsonl`, `frontend.jsonl`, `qa.jsonl`, `onboarding.jsonl`, `pm.jsonl`, `cs.jsonl`, `analytics.jsonl`, `devops.jsonl`, `incident.jsonl`, `performance.jsonl`, `refactoring.jsonl`, `navigation.jsonl` | Per-persona source goldsets (12 personas). Each record's `persona` field must equal the filename stem |

## For AI Agents

### Working In This Directory
- **Edit the per-persona files, never `all.jsonl`.** After editing, run `python eval/build_goldset.py` to regenerate `all.jsonl`, then `python eval/verify_goldset.py --goldset all.jsonl --repo-root <target-repo-clone>` to confirm every `gold_files`/`gold_symbols` still resolves.
- One JSON object per line. Required fields: `id` (unique), `intent` (code/project/chat), `question`, `gold_files`, `gold_symbols`, `hop` (single/multi/none), `difficulty` (easy/medium/hard), `persona`, `must_include`, `must_not_include`.
- `persona` must be one of the 12 valid values (= the filenames) and must match the file it lives in — `build_goldset.py` aborts on a mismatch.
- `hop` must be consistent with the `gold_files` count: 0 → `none`, 1 → `single`, ≥2 → `multi` (`verify_goldset.py` enforces this).
- These are **data files, not code** — they encode the "right answers." Keep them stable across eval runs so scores stay comparable; treat changes like changing the measuring stick.

### Testing Requirements
- Validate with `verify_goldset.py` (file/symbol existence + schema) and `build_goldset.py --check` (persona/id consistency) before running an eval.

## Dependencies

### Internal
- Consumed by `eval/run_eval.py` (via `all.jsonl`); built by `eval/build_goldset.py`; validated by `eval/verify_goldset.py`.

<!-- MANUAL: -->
