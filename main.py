import logging
import os
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import config
import scheduler
import slackbot as slack

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

class _HealthHandler(BaseHTTPRequestHandler):
    """Render의 포트 스캔을 통과하기 위한 최소 헬스체크 엔드포인트."""

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, fmt, *args):  # 액세스 로그 억제
        pass


def _start_health_server() -> None:
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    logger.info("Health check server listening on port %d", port)
    server.serve_forever()

def main() -> int:
    config.validate()
    config.ensure_dirs()

    repos = config.load_repos()
    if not repos:
        logger.error("No repos configured. Add entries to _REPO_DEFINITIONS in config.py")
        return 1

    logger.info("Loaded %d repo(s): %s", len(repos), [r.name for r in repos])

    # Initial index (synchronous — bots wait until data is ready)
    for repo in repos:
        scheduler.initial_index_if_empty(repo)

    # Launch one Socket Mode thread per repo (daemon so Ctrl+C exits cleanly)
    threads: list[threading.Thread] = []
    for repo in repos:
        t = threading.Thread(
            target=slack.run_socket_mode,
            args=(repo,),
            name=f"slackbot-{repo.name}",
            daemon=True,
        )
        t.start()
        threads.append(t)
        logger.info("Started Slack bot thread for %s", repo.name)

    # Start background reindex scheduler
    sched = scheduler.start_scheduler(repos)

    # Render Web Service용 헬스체크 서버 (포트 스캔 통과)
    threading.Thread(target=_start_health_server, daemon=True, name="health-server").start()

    stop = threading.Event()

    def _shutdown(signum, frame):
        logger.info("Shutting down...")
        sched.shutdown(wait=False)
        stop.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("All bots running. Press Ctrl+C to stop.")
    stop.wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
