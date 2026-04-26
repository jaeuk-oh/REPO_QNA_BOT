import logging
import signal
import sys
import threading

import config
import scheduler
import slackbot as slack

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


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
