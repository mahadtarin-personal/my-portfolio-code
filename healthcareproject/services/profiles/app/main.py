from fastapi import FastAPI
from logging_shared import configure_logging
from metrics_shared import instrument_metrics, register_gauge_collector
from rate_limit_shared import install_rate_limiting
from tracing_shared import configure_tracing, instrument_fastapi

from app.core.domain_metrics import compute_outbox_metrics
from app.deps import limiter
from app.routers import auth, clinics, patients, providers, staff

configure_logging("profiles")
configure_tracing("profiles")


def create_app() -> FastAPI:
    app = FastAPI(title="SmartHealth Profiles Service")
    instrument_fastapi(app)
    instrument_metrics(app)
    install_rate_limiting(app, limiter)
    register_gauge_collector(compute_outbox_metrics)
    app.include_router(auth.router)
    app.include_router(patients.router)
    app.include_router(providers.router)
    app.include_router(clinics.router)
    app.include_router(staff.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
