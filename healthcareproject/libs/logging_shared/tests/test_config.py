import io
import json
import logging

from opentelemetry.sdk.trace import TracerProvider

from logging_shared import JSONFormatter, configure_logging


def _make_record(msg: str = "hello") -> logging.LogRecord:
    return logging.LogRecord(
        name="my.module", level=logging.INFO, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )


def test_json_formatter_emits_expected_fields() -> None:
    formatter = JSONFormatter("test-service")
    record = logging.LogRecord(
        name="my.module", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello %s", args=("world",), exc_info=None,
    )

    line = json.loads(formatter.format(record))

    assert line["service"] == "test-service"
    assert line["level"] == "INFO"
    assert line["logger"] == "my.module"
    assert line["message"] == "hello world"
    assert "timestamp" in line
    assert "exception" not in line


def test_json_formatter_includes_exception_when_present() -> None:
    formatter = JSONFormatter("test-service")
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="my.module", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="failed", args=(), exc_info=sys.exc_info(),
        )

    line = json.loads(formatter.format(record))
    assert "ValueError: boom" in line["exception"]


def test_configure_logging_makes_root_logger_emit_json() -> None:
    stream = io.StringIO()
    configure_logging("test-service")
    root = logging.getLogger()
    root.handlers[0].stream = stream  # redirect from stdout for the test

    logging.getLogger("some.module").info("hello")

    line = json.loads(stream.getvalue().strip())
    assert line["service"] == "test-service"
    assert line["message"] == "hello"


def test_json_formatter_omits_trace_id_with_no_active_span() -> None:
    formatter = JSONFormatter("test-service")
    line = json.loads(formatter.format(_make_record()))
    assert "trace_id" not in line
    assert "span_id" not in line


def test_json_formatter_includes_trace_id_inside_an_active_span() -> None:
    formatter = JSONFormatter("test-service")
    tracer = TracerProvider().get_tracer("test")

    with tracer.start_as_current_span("request") as span:
        line = json.loads(formatter.format(_make_record()))
        expected_trace_id = format(span.get_span_context().trace_id, "032x")
        expected_span_id = format(span.get_span_context().span_id, "016x")

    assert line["trace_id"] == expected_trace_id
    assert len(line["trace_id"]) == 32
    assert line["span_id"] == expected_span_id
    assert len(line["span_id"]) == 16
