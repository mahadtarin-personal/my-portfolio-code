from __future__ import annotations

from prometheus_fastapi_instrumentator import Instrumentator

# design doc §10: "Prometheus collects metrics over time from every
# service — the pattern across many requests, not one" (the counterpart
# to Jaeger, which is "why was THIS ONE request slow"). request count,
# latency histograms, and in-progress requests, all broken down by
# method/path/status — the standard "four golden signals" starting point.
_DEFAULT_ENDPOINT = "/metrics"


def instrument_metrics(app, endpoint: str = _DEFAULT_ENDPOINT) -> None:
    """Call once, right after the FastAPI app is constructed. `endpoint`
    only needs overriding for analytics, whose own /metrics path is
    already taken by its business metrics (total_patients,
    appointments_booked, etc.) — everything else uses the Prometheus
    convention of plain /metrics, which is also what Prometheus's own
    scrape config (deploy/prometheus/prometheus.yml) expects by default."""
    Instrumentator().instrument(app).expose(app, endpoint=endpoint, include_in_schema=False)
