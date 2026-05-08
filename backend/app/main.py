"""Entry point: init DB, run one sync immediately, then start scheduler."""
from __future__ import annotations

import asyncio
import logging
import os
import signal

from .db.init_db import init_db
from .scheduler.jobs import full_sync, start_scheduler


def _configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _main_async() -> None:
    interval = int(os.environ.get("SYNC_INTERVAL_MINUTES", "30"))

    # 1. Initial run (no manual fallback under scheduler)
    await full_sync(allow_manual_login=False)

    # 2. Start the recurring scheduler
    start_scheduler(interval_minutes=interval)

    # 3. Block forever until SIGINT/SIGTERM
    stop = asyncio.Event()

    def _shutdown() -> None:
        stop.set()

    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGINT, _shutdown)
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, _shutdown)
    except NotImplementedError:
        # Windows: signal handlers in asyncio aren't fully supported
        pass

    try:
        await stop.wait()
    except KeyboardInterrupt:
        pass


def main() -> None:
    _configure_logging()
    init_db()
    try:
        asyncio.run(_main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
