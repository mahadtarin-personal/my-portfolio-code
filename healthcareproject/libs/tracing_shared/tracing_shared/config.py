from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# design doc §10: "Attaches a shared trace ID to each request at the front
# door, carried through every service it touches." There's no Envoy/API
# gateway in this local setup to be the literal front door — FastAPI's own
# instrumentation is what starts the trace here, the moment a request
# actually arrives at whichever service is hit first.
_DEFAULT_OTLP_ENDPOINT = "http://jaeger:4318/v1/traces"


def configure_tracing(service_name: str, otlp_endpoint: str | None = None) -> None:
    """Sets up ONE shared TracerProvider exporting to Jaeger over OTLP/HTTP,
    plus auto-instrumentation for:
    - outgoing httpx calls — this is what makes a trace continue ACROSS a
      service boundary (booking calling profiles during slot reconciliation
      shows up as one connected trace, not two separate ones), by injecting
      a `traceparent` header the receiving service's own FastAPI
      instrumentation picks back up automatically.
    - SQLAlchemy queries, IF this service actually has SQLAlchemy installed
      (billing doesn't — it's a Week 1 stub with no database at all) — so a
      slow query shows up as its own span inside whichever request
      triggered it, not just a black box.

    Call once, at import time, before create_app() actually builds the
    FastAPI app — ordering matters less than it looks like it should here:
    SQLAlchemyInstrumentor().instrument() with no engine argument hooks
    SQLAlchemy's Engine class itself, which applies to every engine
    instance regardless of whether it was created before or after this
    call, as long as it runs before any query actually executes (which
    only happens per-request, well after app startup)."""
    endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", _DEFAULT_OTLP_ENDPOINT)
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)

    HTTPXClientInstrumentor().instrument()

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    except ImportError:
        pass
    else:
        SQLAlchemyInstrumentor().instrument()


def instrument_fastapi(app) -> None:
    """Wraps the FastAPI app so every incoming request starts (or
    continues) a trace — call right after `FastAPI(...)` is constructed,
    inside create_app()."""
    FastAPIInstrumentor.instrument_app(app)
