from fastapi import FastAPI
from logging_shared import configure_logging
from metrics_shared import instrument_metrics
from tracing_shared import configure_tracing, instrument_fastapi

configure_logging("billing")
configure_tracing("billing")

app = FastAPI(title="SmartHealth Billing Service")
instrument_fastapi(app)
instrument_metrics(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
