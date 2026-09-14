from __future__ import annotations

import logging

from kafka_shared import Topic, run_consumer_loop
from logging_shared import configure_logging

from app.core.config import get_settings
from app.handlers import handle_event

configure_logging("audit-worker")
logger = logging.getLogger("audit.worker")

# Every topic — audit's whole purpose is a complete tamper-evident record
# of everything, not a filtered subset like notification/analytics.
CONSUMED_TOPICS = [t.value for t in Topic]


def main() -> None:
    settings = get_settings()
    logger.info(
        "audit worker started; bootstrap=%s topics=%s",
        settings.kafka_bootstrap_servers,
        CONSUMED_TOPICS,
    )
    run_consumer_loop(
        settings.kafka_bootstrap_servers,
        settings.kafka_consumer_group,
        CONSUMED_TOPICS,
        handle_event,
    )


if __name__ == "__main__":
    main()
