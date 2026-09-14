from app.celery_app import celery_app
from app.tasks.debug import debug_task


def test_debug_task_round_trips_through_the_celery_app() -> None:
    # conftest sets task_always_eager, so .delay() runs synchronously here
    # without needing a real broker.
    result = debug_task.delay("hello")
    assert result.get(timeout=5) == "pong: hello"


def test_debug_task_is_registered_on_the_celery_app() -> None:
    assert "booking.debug_task" in celery_app.tasks


def test_audit_chain_verification_is_scheduled_nightly() -> None:
    entry = celery_app.conf.beat_schedule["verify-audit-chain-nightly"]
    assert entry["task"] == "booking.verify_audit_chain_task"
