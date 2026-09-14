from fastapi import Depends, FastAPI
from logging_shared import configure_logging
from metrics_shared import instrument_metrics, register_gauge_collector
from sqlalchemy.orm import Session
from tracing_shared import configure_tracing, instrument_fastapi

from app.core.domain_metrics import compute_business_metrics
from app.crud import analytics_event as analytics_crud
from app.db.session import get_db
from app.schemas.analytics_event import AnalyticsEventRead
from app.schemas.metrics import MetricsRead

configure_logging("analytics")
configure_tracing("analytics")

app = FastAPI(title="SmartHealth Analytics Service")
instrument_fastapi(app)
# /metrics is already this service's own business-metrics endpoint
# (total_patients, appointments_booked, ...) — Prometheus's operational
# metrics (request rate/latency/errors) go on /prom-metrics instead, and
# deploy/prometheus/prometheus.yml scrapes this service at that path.
instrument_metrics(app, endpoint="/prom-metrics")
register_gauge_collector(compute_business_metrics)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", response_model=MetricsRead)
def metrics(db: Session = Depends(get_db)) -> MetricsRead:
    """No auth — same debugging/verification-surface precedent as
    notification's /notifications and audit's /audit at this stage."""
    return analytics_crud.compute_metrics(db)


@app.get("/events", response_model=list[AnalyticsEventRead])
def list_events(db: Session = Depends(get_db)) -> list[AnalyticsEventRead]:
    return [AnalyticsEventRead.model_validate(e) for e in analytics_crud.list_recent(db)]
