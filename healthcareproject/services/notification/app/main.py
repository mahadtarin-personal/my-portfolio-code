from fastapi import Depends, FastAPI
from logging_shared import configure_logging
from metrics_shared import instrument_metrics
from sqlalchemy.orm import Session
from tracing_shared import configure_tracing, instrument_fastapi

from app.crud import notification as notification_crud
from app.db.session import get_db
from app.schemas.notification import NotificationRead

configure_logging("notification")
configure_tracing("notification")

app = FastAPI(title="SmartHealth Notification Service")
instrument_fastapi(app)
instrument_metrics(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/notifications", response_model=list[NotificationRead])
def list_notifications(db: Session = Depends(get_db)) -> list[NotificationRead]:
    """No auth — this is a verification/debugging read endpoint (see real
    stubs it's meant to eventually be replaced by if this service ever
    needs a user-facing surface), matching how billing/analytics'
    endpoints have no auth either at this stage."""
    return [NotificationRead.model_validate(n) for n in notification_crud.list_recent(db)]
