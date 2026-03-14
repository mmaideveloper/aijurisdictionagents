from __future__ import annotations

import logging
import time

from app.logging_config import configure_logging
from app.services.email_scheduler import EmailScheduler, scheduler_enabled, scheduler_interval_seconds

logger = logging.getLogger("aijuristiction-api.email.scheduler-main")


def main() -> None:
    configure_logging()
    if not scheduler_enabled():
        logger.info("Email scheduler is disabled by EMAIL_SCHEDULER_ENABLED")
        return

    scheduler = EmailScheduler.from_env()
    interval = scheduler_interval_seconds()
    logger.info("Email scheduler started | interval_seconds=%s", interval)
    while True:
        processed = scheduler.run_once(limit=50)
        if processed:
            logger.info("Email scheduler processed %s queued messages", processed)
        time.sleep(interval)


if __name__ == "__main__":
    main()
