from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from tracing_shared import tag_span


def test_tag_span_sets_attributes_on_the_current_span() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("request"):
        tag_span(appointment_id="abc-123", patient_id="patient-1")

    (span,) = exporter.get_finished_spans()
    assert span.attributes["appointment_id"] == "abc-123"
    assert span.attributes["patient_id"] == "patient-1"


def test_tag_span_does_not_raise_with_no_active_span() -> None:
    tag_span(appointment_id="abc-123")  # no-op on the default INVALID_SPAN
