from contextlib import asynccontextmanager

from fastapi import FastAPI
from logging_shared import configure_logging
from metrics_shared import instrument_metrics, register_gauge_collector, register_labeled_gauge_collector
from rate_limit_shared import install_rate_limiting
from tracing_shared import configure_tracing, instrument_fastapi

from app.core.config import get_settings
from app.core.domain_metrics import compute_appointment_funnel_rows, compute_outbox_metrics
from app.core.temporal import connect_with_retry
from app.deps import limiter
from app.routers import appointments, ops, slots, waitlist

configure_logging("booking")
configure_tracing("booking")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.temporal_enabled:
        app.state.temporal_client = await connect_with_retry(
            settings.temporal_address, settings.temporal_namespace
        )
    else:
        app.state.temporal_client = None
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="SmartHealth Booking Service", lifespan=lifespan)
    instrument_fastapi(app)
    instrument_metrics(app)
    install_rate_limiting(app, limiter)
    register_gauge_collector(compute_outbox_metrics)
    register_labeled_gauge_collector(
        "smarthealth_appointments_by_status",
        "Current appointment count by status",
        ["status"],
        compute_appointment_funnel_rows,
    )
    app.include_router(slots.router)
    app.include_router(appointments.router)
    app.include_router(waitlist.router)
    app.include_router(ops.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
