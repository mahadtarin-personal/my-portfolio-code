from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from opentelemetry import trace


class JSONFormatter(logging.Formatter):
    """One JSON object per line — every service emits the exact same
    shape (timestamp, level, service, logger, message, plus exception if
    present) instead of each one's own ad-hoc string format. Doesn't
    require a log aggregator to be useful today (grep/jq against
    `docker logs` works immediately); it's also the shape a real
    aggregator (Loki, ELK, CloudWatch) expects, so adding one later is a
    deployment change, not a re-instrumentation.

    trace_id/span_id are pulled from whatever span is currently active
    (the same one FastAPIInstrumentor started for this request, see
    libs/tracing_shared) and formatted as lowercase hex — the exact
    string Jaeger's UI shows and its Tags search box accepts, so a log
    line can be pasted straight into a Jaeger search with no conversion.
    Omitted entirely outside a traced request (background/startup code,
    or a process — a worker — that never calls configure_tracing() at
    all) rather than logging a meaningless all-zero id."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "logger": record.name,
            "message": record.getMessage(),
        }
        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            payload["trace_id"] = format(span_context.trace_id, "032x")
            payload["span_id"] = format(span_context.span_id, "016x")
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(service_name: str, level: int = logging.INFO) -> None:
    """Replaces the root logger's handlers wholesale — called once, at
    process startup, before anything else logs. Every service's own
    `logging.getLogger(__name__)` calls flow through this same root
    handler, so nothing per-module needs to change."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter(service_name))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
