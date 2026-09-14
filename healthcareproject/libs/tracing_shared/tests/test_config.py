from fastapi import FastAPI
from opentelemetry import trace

from tracing_shared import configure_tracing, instrument_fastapi


def test_configure_tracing_sets_a_real_tracer_provider() -> None:
    configure_tracing("test-service")
    provider = trace.get_tracer_provider()
    # A no-op provider (the default before configure_tracing runs) has no
    # resource attribute — asserting a real one confirms configure_tracing
    # actually replaced it rather than silently doing nothing.
    assert provider.resource.attributes["service.name"] == "test-service"


def test_instrument_fastapi_does_not_raise() -> None:
    configure_tracing("test-service")
    app = FastAPI()
    instrument_fastapi(app)  # should not raise
