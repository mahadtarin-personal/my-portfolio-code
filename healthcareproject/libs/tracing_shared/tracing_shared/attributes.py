from __future__ import annotations

from opentelemetry import trace


def tag_span(**attributes: str) -> None:
    """Attaches business identifiers (appointment_id, patient_id, ...) to
    the CURRENT span — the one FastAPIInstrumentor already started for
    this request — rather than opening a new one. Auto-instrumentation
    only ever captures transport-level facts (URL, method, status, DB
    statement); without this, there's no way to jump from "the patient
    with appointment X says it failed" to the matching trace except
    guessing at a time window. No-ops harmlessly if tracing isn't
    configured (get_current_span() returns Trace.INVALID_SPAN, whose
    set_attribute is a no-op) — safe to call from code paths that also
    run under pytest with OTEL_SDK_DISABLED=true."""
    span = trace.get_current_span()
    for key, value in attributes.items():
        span.set_attribute(key, value)
