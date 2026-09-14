from __future__ import annotations

import logging

from kafka_shared import Topic, run_consumer_loop
from logging_shared import configure_logging

from app.core.config import get_settings
from app.handlers import handle_event

configure_logging("notification-worker")
logger = logging.getLogger("notification.worker")

CONSUMED_TOPICS = [
    Topic.APPOINTMENT_BOOKED.value,
    Topic.APPOINTMENT_CANCELLED.value,
    Topic.APPOINTMENT_RESCHEDULED.value,
    Topic.REMINDER_SCHEDULED.value,
    Topic.BILLING_STATUS_UPDATED.value,
]


def main() -> None:
    settings = get_settings()
    logger.info(
        "notification worker started; bootstrap=%s topics=%s",
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
