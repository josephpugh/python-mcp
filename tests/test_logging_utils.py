import io
import json as py_json
import logging
from types import SimpleNamespace

import pytest

from app import logging_utils


@pytest.fixture(autouse=True)
def reset_root_logger():
    root = logging.getLogger()
    root.handlers.clear()
    yield
    root.handlers.clear()


def test_setup_logging_configures_json_formatter(monkeypatch):
    stream = io.StringIO()
    dummy_sys = SimpleNamespace(stdout=stream)
    monkeypatch.setattr(logging_utils, "sys", dummy_sys)

    logging_utils.setup_logging()

    root = logging.getLogger()
    assert root.level == logging.INFO
    assert len(root.handlers) == 1

    handler = root.handlers[0]
    assert handler.stream is stream
    assert isinstance(handler.formatter, logging_utils.json.JsonFormatter)

    logging.getLogger().info("structured log", extra={"city": "Boston"})
    log_line = stream.getvalue().strip().splitlines()[-1]
    payload = py_json.loads(log_line)
    assert payload["message"] == "structured log"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "root"
    assert payload["city"] == "Boston"


def test_setup_tracing_basic_uses_otlp_exporter(monkeypatch):
    monkeypatch.setattr(
        logging_utils,
        "get_settings",
        lambda: SimpleNamespace(otel_endpoint="http://collector:4318", otel_service_name="svc"),
    )

    otlp_exporters = []

    class DummyOTLPExporter:
        def __init__(self, endpoint, insecure):
            self.endpoint = endpoint
            self.insecure = insecure
            otlp_exporters.append(self)

    monkeypatch.setattr(logging_utils, "OTLPSpanExporter", DummyOTLPExporter)

    batch_processors = []

    class DummyBatchSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter
            batch_processors.append(self)

    monkeypatch.setattr(logging_utils, "BatchSpanProcessor", DummyBatchSpanProcessor)

    tracer_providers = []

    class DummyProvider:
        def __init__(self, resource):
            self.resource = resource
            self.processors = []
            tracer_providers.append(self)

        def add_span_processor(self, processor):
            self.processors.append(processor)

    monkeypatch.setattr(logging_utils, "TracerProvider", DummyProvider)

    tracer_set = []
    monkeypatch.setattr(
        logging_utils.trace,
        "set_tracer_provider",
        lambda provider: tracer_set.append(provider),
    )

    instrument_called = []

    class DummyInstrumentor:
        def instrument(self):
            instrument_called.append(True)

    monkeypatch.setattr(logging_utils, "HTTPXClientInstrumentor", lambda: DummyInstrumentor())

    logging_utils.setup_tracing_basic()

    assert len(otlp_exporters) == 1
    assert otlp_exporters[0].endpoint == "http://collector:4318"
    assert otlp_exporters[0].insecure is True

    assert len(batch_processors) == 1
    assert batch_processors[0].exporter is otlp_exporters[0]

    assert tracer_providers[0].processors == batch_processors
    resource_attrs = tracer_providers[0].resource.attributes
    assert resource_attrs["service.name"] == "weather-service"
    assert resource_attrs["service.namespace"] == "mcp"

    assert tracer_set == tracer_providers
    assert instrument_called == [True]


def test_setup_tracing_basic_falls_back_to_console_exporter(monkeypatch):
    monkeypatch.setattr(
        logging_utils,
        "get_settings",
        lambda: SimpleNamespace(otel_endpoint=None, otel_service_name="svc"),
    )

    console_exporters = []

    class DummyConsoleExporter:
        def __init__(self):
            console_exporters.append(self)

    monkeypatch.setattr(logging_utils, "ConsoleSpanExporter", DummyConsoleExporter)

    processors = []

    class DummyBatchSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter
            processors.append(self)

    monkeypatch.setattr(logging_utils, "BatchSpanProcessor", DummyBatchSpanProcessor)

    class DummyProvider:
        def __init__(self, resource):
            self.resource = resource
            self.processors = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    monkeypatch.setattr(logging_utils, "TracerProvider", DummyProvider)

    monkeypatch.setattr(logging_utils.trace, "set_tracer_provider", lambda provider: None)
    monkeypatch.setattr(logging_utils, "HTTPXClientInstrumentor", lambda: SimpleNamespace(instrument=lambda: None))

    logging_utils.setup_tracing_basic()

    assert len(console_exporters) == 1
    assert len(processors) == 1
    assert processors[0].exporter is console_exporters[0]
