"""Dedicated production/development worker process."""

import logging
import signal
import sys

from backend.app.main import initialize_database, worker_loop, WORKER_ID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - [Worker:%(threadName)s] %(message)s"
)
logger = logging.getLogger("worker")


def main() -> None:
    logger.info(f"Starting standalone worker process (ID: {WORKER_ID})")
    initialize_database()

    def handle_shutdown(signum, frame):
        logger.info("Shutdown signal received. Stopping worker loop gracefully...")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        worker_loop()
    except KeyboardInterrupt:
        logger.info("Worker interrupted. Exiting.")


if __name__ == "__main__":
    main()
