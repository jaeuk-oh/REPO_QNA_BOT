import re
import logging
import threading

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import config
from config import RepoConfig
from agent import retrieve, answer, answer_project, to_blocks, to_fallback_text, classify_intent, answer_general

logger = logging.getLogger(__name__)

_MENTION_RE = re.compile(r"<@[A-Z0-9]+>\s*")


def _strip_mention(text: str) -> str:
    return _MENTION_RE.sub("", text).strip()


def _process_mention(question: str, channel: str, thread_ts: str, client, repo: RepoConfig) -> None:
    # Post placeholder first so users get immediate feedback while we call OpenAI
    try:
        placeholder = client.chat_postMessage(
            channel=channel,
            # thread_ts=thread_ts,
            text="생각 중... 🔍",
        )
        placeholder_ts = placeholder["ts"]
    except Exception:
        logger.exception("Failed to post placeholder for %s", repo.name)
        return

    try:
        intent = classify_intent(question)
        _LABEL = {"chat": "[일반]", "project": "[프로젝트]", "code": "[코드]"}
        label = _LABEL.get(intent, "[코드]")

        if intent == "chat":
            reply = answer_general(question, repo_name=repo.display_name, repo_url=repo.github_url)
            client.chat_update(channel=channel, ts=placeholder_ts, text=f"{label} {reply}")
            return

        chunks = retrieve(question, repo.chroma_dir, repo.collection_name, config.TOP_K)

        if intent == "project":
            reply = answer_project(question, chunks, repo.display_name, repo.github_url)
            client.chat_update(channel=channel, ts=placeholder_ts, text=f"{label} {reply}")
            return

        ans = answer(question, chunks, repo.display_name)
        blocks = [{"type": "context", "elements": [{"type": "mrkdwn", "text": label}]}] + to_blocks(ans)
        client.chat_update(
            channel=channel,
            ts=placeholder_ts,
            text=f"{label} {to_fallback_text(ans)}",
            blocks=blocks,
        )
    except Exception as e:
        logger.exception("Processing failed for %s: %s", repo.name, type(e).__name__)
        try:
            client.chat_update(
                channel=channel,
                ts=placeholder_ts,
                text=f"답변 생성 실패: {type(e).__name__}",
            )
        except Exception:
            pass


def build_app(repo: RepoConfig) -> App:
    app = App(token=repo.slack_bot_token)

    @app.event("app_mention")
    def on_mention(event, client):
        question = _strip_mention(event.get("text", ""))
        thread_ts = event.get("thread_ts") or event["ts"]
        channel = event["channel"]

        if not question:
            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="질문을 함께 적어주세요.",
            )
            return

        # Return immediately so Bolt's thread is free — OpenAI calls run in background
        threading.Thread(
            target=_process_mention,
            args=(question, channel, thread_ts, client, repo),
            daemon=True,
        ).start()

    return app


def run_socket_mode(repo: RepoConfig) -> None:
    """Blocking. Intended to run in a dedicated thread."""
    app = build_app(repo)
    handler = SocketModeHandler(app, repo.slack_app_token)
    logger.info("Starting Socket Mode bot for repo: %s", repo.name)
    handler.start()
