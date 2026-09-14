from __future__ import annotations

import logging

from kafka_shared import Topic, run_consumer_loop
from logging_shared import configure_logging

from app.core.config import get_settings
from app.handlers import handle_event

configure_logging("analytics-worker")
logger = logging.getLogger("analytics.worker")

# The 4 topics the 5 published metrics are actually derived from —
# total_patients (PATIENT_REGISTERED), appointments_booked
# (APPOINTMENT_BOOKED), completed_visits + avg_wait_time (VISIT_COMPLETED,
# which carries checked_in_at/started_at), cancellation_rate (booked vs
# APPOINTMENT_CANCELLED).
CONSUMED_TOPICS = [
    Topic.PATIENT_REGISTERED.value,
    Topic.APPOINTMENT_BOOKED.value,
    Topic.APPOINTMENT_CANCELLED.value,
    Topic.VISIT_COMPLETED.value,
]


def main() -> None:
    settings = get_settings()
    logger.info(
        "analytics worker started; bootstrap=%s topics=%s",
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
