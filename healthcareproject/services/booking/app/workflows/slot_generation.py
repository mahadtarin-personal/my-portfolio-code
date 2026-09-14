from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.activities.slot_generation import (
        GenerateForProviderInput,
        generate_slots_for_one_provider,
        list_provider_ids,
    )

DEFAULT_DAYS_AHEAD = 14

STEP_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
)


@dataclass
class GenerateSlotsScheduledResult:
    providers_processed: int
    slots_created: int


@dataclass
class ReconcileProviderSlotsInput:
    provider_id: str
    days_ahead: int = DEFAULT_DAYS_AHEAD


@workflow.defn
class GenerateSlotsScheduledWorkflow:
    """Recurring counterpart to POST /slots/generate — run on a Temporal
    Schedule (see app/worker.py) instead of Celery, since it reuses
    infrastructure that already exists for the booking saga rather than
    requiring a new broker + worker + beat process. One activity call per
    provider, so a single provider's failure doesn't block the rest."""

    @workflow.run
    async def run(self, days_ahead: int = DEFAULT_DAYS_AHEAD) -> GenerateSlotsScheduledResult:
        provider_ids = await workflow.execute_activity(
            list_provider_ids,
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=STEP_RETRY,
        )

        total_created = 0
        for provider_id in provider_ids:
            created = await workflow.execute_activity(
                generate_slots_for_one_provider,
                GenerateForProviderInput(provider_id=provider_id, days_ahead=days_ahead),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=STEP_RETRY,
            )
            total_created += created

        return GenerateSlotsScheduledResult(
            providers_processed=len(provider_ids), slots_created=total_created
        )


@workflow.defn
class ReconcileProviderSlotsWorkflow:
    """Event-triggered counterpart to GenerateSlotsScheduledWorkflow —
    started by profiles right after a provider's schedule or time-off
    changes, instead of waiting for the next 24h scheduled tick. Same
    activity, same reconciliation logic (see
    generate_slots_for_provider) — just scoped to the one provider that
    actually changed, run right now."""

    @workflow.run
    async def run(self, inp: ReconcileProviderSlotsInput) -> int:
        return await workflow.execute_activity(
            generate_slots_for_one_provider,
            GenerateForProviderInput(provider_id=inp.provider_id, days_ahead=inp.days_ahead),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=STEP_RETRY,
        )
