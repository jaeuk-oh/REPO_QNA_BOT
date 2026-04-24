import re
import logging

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import config
from config import RepoConfig
from agent import retrieve, answer, to_blocks, to_fallback_text, classify_intent, answer_general

logger = logging.getLogger(__name__)

_MENTION_RE = re.compile(r"<@[A-Z0-9]+>\s*")


def _strip_mention(text: str) -> str:
    return _MENTION_RE.sub("", text).strip()


def build_app(repo: RepoConfig) -> App:
    # signing_secret is not used in Socket Mode (auth is via slack_app_token).
    # Omitting it prevents spurious validation errors if the env var is unset.
    app = App(token=repo.slack_bot_token)

    # Drop Slack retry events to avoid duplicate answers on slow OpenAI calls
    @app.middleware
    def ignore_retries(req, next):
        if req.headers.get("x-slack-retry-num"):
            return {"statusCode": 200, "body": "retry ignored"}
        return next()

    @app.event("app_mention")
    def on_mention(event, say, client):
        question = _strip_mention(event.get("text", ""))
        thread_ts = event.get("thread_ts") or event["ts"]
        channel = event["channel"]

        if not question:
            say(text="질문을 함께 적어주세요.", thread_ts=thread_ts)
            return

        intent = classify_intent(question)

        if intent == "general":
            try:
                reply = answer_general(question)
                say(text=reply, thread_ts=thread_ts)
            except Exception:
                logger.exception("General answer failed for %s", repo.name)
                say(text="죄송해요, 잠시 문제가 생겼어요.", thread_ts=thread_ts)
            return

        # Post placeholder immediately so Bolt ack is fast
        try:
            placeholder = client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="생각 중... 🔍",
            )
        except Exception:
            logger.exception("Failed to post placeholder for %s", repo.name)
            return

        try:
            chunks = retrieve(
                question,
                repo.chroma_dir,
                repo.collection_name,
                config.TOP_K,
            )
            ans = answer(question, chunks, repo.name)
            client.chat_update(
                channel=channel,
                ts=placeholder["ts"],
                text=to_fallback_text(ans),
                blocks=to_blocks(ans),
            )
        except Exception as e:
            logger.exception("Answer generation failed for %s", repo.name)
            try:
                client.chat_update(
                    channel=channel,
                    ts=placeholder["ts"],
                    text=f"답변 생성 실패: {type(e).__name__}",
                )
            except Exception:
                pass

    return app


def run_socket_mode(repo: RepoConfig) -> None:
    """Blocking. Intended to run in a dedicated thread."""
    app = build_app(repo)
    handler = SocketModeHandler(app, repo.slack_app_token)
    logger.info("Starting Socket Mode bot for repo: %s", repo.name)
    handler.start()
