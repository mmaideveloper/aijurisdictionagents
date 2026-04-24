from __future__ import annotations

import logging

from app.logging_config import configure_logging
from app.services.email_scheduler import EmailScheduler, scheduler_enabled

logger = logging.getLogger("aijuristiction-api.email.scheduler-job")


def main() -> int:
    configure_logging()
    if not scheduler_enabled():
        logger.info("Email scheduler job is disabled by EMAIL_SCHEDULER_ENABLED")
        return 0

    scheduler = EmailScheduler.from_env()
    processed = scheduler.run_once(limit=50)
    logger.info("Email scheduler job finished | processed=%s", processed)
    return processed


if __name__ == "__main__":
    main()
