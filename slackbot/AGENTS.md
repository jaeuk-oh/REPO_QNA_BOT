<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# slackbot

## Purpose
The **Slack interface** — receives `app_mention` events over Socket Mode (no public URL required) and drives the `agent` pipeline to answer them. One `App` + `SocketModeHandler` runs per repo in its own thread (launched from `main.py`). Each mention is processed in a background thread so Bolt's event loop stays responsive.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | Public API barrel — re-exports `build_app`, `run_socket_mode` |
| `handler.py` | `build_app(repo)` registers the `app_mention` handler; `_process_mention` runs the full pipeline (placeholder post → classify → retrieve → answer → update); `run_socket_mode(repo)` blocks on the Socket Mode connection (run in a dedicated thread) |

## For AI Agents

### Working In This Directory
- **Immediate-ack pattern**: `on_mention` strips the bot mention, then immediately spawns a daemon thread running `_process_mention` and returns, so Bolt's handler thread is freed before the (slow) OpenAI calls. Preserve this — blocking in the handler risks Slack retries/duplicate processing.
- **Placeholder-then-update**: `_process_mention` posts "생각 중... 🔍" first, captures its `ts`, then `chat_update`s that same message with the final answer. Errors also update the placeholder (never leave it dangling).
- **Intent dispatch** mirrors `agent`: `chat` → `answer_general`, `project` → `answer_project`, `code` → `answer` + `to_blocks`/`to_fallback_text` (Block Kit + plaintext fallback). Each answer is prefixed with a label (`[일반]` / `[프로젝트]` / `[코드]`).
- Empty questions (mention with no text) get a prompt to include a question and short-circuit.
- Note: `thread_ts` is computed but the placeholder post currently does **not** thread replies (`thread_ts=` is commented out) — multi-turn / threaded context is intentionally unimplemented (see README status).

### Testing Requirements
- No unit tests; Slack I/O is the hard-to-mock part. The pure logic (`_strip_mention`, intent dispatch) is reachable for unit testing; the answer functions themselves are covered headlessly by `eval/`.
- Manual test: run `main.py` with valid tokens and `@`-mention the bot in a channel it's in.

### Common Patterns
- `_MENTION_RE` strips leading `<@USERID>` tokens from the message text.
- All Slack API calls are wrapped in try/except with logging; a failed placeholder post aborts processing, a failed final update degrades to an error message.
- Per-repo isolation: each bot is built from its own `RepoConfig` (separate token, collection, clone dir).

## Dependencies

### Internal
- `config` / `RepoConfig` — per-repo tokens, `chroma_dir`, `collection_name`, `display_name`, `github_url`, `TOP_K`
- `agent` — `retrieve`, `answer`, `answer_project`, `answer_general`, `classify_intent`, `to_blocks`, `to_fallback_text`

### External
- `slack_bolt` — `App`, `SocketModeHandler`

<!-- MANUAL: -->
