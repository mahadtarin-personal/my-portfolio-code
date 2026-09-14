from fastapi import Depends, FastAPI
from logging_shared import configure_logging
from metrics_shared import instrument_metrics, register_gauge_collector
from sqlalchemy.orm import Session
from tracing_shared import configure_tracing, instrument_fastapi

from app.core.domain_metrics import compute_chain_status_metrics
from app.crud import audit_log as audit_log_crud
from app.db.session import get_db
from app.schemas.audit_log import AuditLogRead, VerifyResult

configure_logging("audit")
configure_tracing("audit")

app = FastAPI(title="SmartHealth Audit Service")
instrument_fastapi(app)
instrument_metrics(app)
register_gauge_collector(compute_chain_status_metrics)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/audit", response_model=list[AuditLogRead])
def list_audit_log(db: Session = Depends(get_db)) -> list[AuditLogRead]:
    """No auth — a real deployment would gate this behind admin/compliance
    roles; kept open here for the same reason notification's read endpoint
    is, this is a verification surface for this stage of the project."""
    return [AuditLogRead.model_validate(r) for r in audit_log_crud.list_recent(db)]


@app.get("/audit/verify", response_model=VerifyResult)
def verify_audit_chain(db: Session = Depends(get_db)) -> VerifyResult:
    """The code-level second layer from design §13. Called nightly by
    booking's celery-beat (app/tasks/audit_verify.py::verify_audit_chain_task,
    schedule "verify-audit-chain-nightly"), which pages on a mismatch —
    also exposed here directly so it can be checked on demand."""
    valid, broken_at_id, rows_checked = audit_log_crud.verify_chain(db)
    return VerifyResult(valid=valid, broken_at_id=broken_at_id, rows_checked=rows_checked)
