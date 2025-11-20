import logging
import sys

from pythonjsonlogger import json
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

try:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    HTTPXClientInstrumentor = None

from .config import get_settings


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    formatter = json.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={
            "asctime": "timestamp",
            "levelname": "level",
            "name": "logger",
        },
    )
    handler.setFormatter(formatter)
    root.handlers.clear()
    root.addHandler(handler)


def setup_tracing(app) -> None:
    settings = get_settings()

    resource = Resource.create(
        {
            "service.name": "weather-service",
            "service.namespace": "mcp",
        }
    )

    span_exporters = []
    if settings.otel_endpoint:
        span_exporters.append(
            OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
        )
    else:
        span_exporters.append(ConsoleSpanExporter())

    provider = TracerProvider(resource=resource)
    for exporter in span_exporters:
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)

    if HTTPXClientInstrumentor:
        HTTPXClientInstrumentor().instrument()
