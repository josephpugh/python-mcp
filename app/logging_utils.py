import logging
import sys
import inspect
from functools import wraps

from pythonjsonlogger import json
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
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

tracer = trace.get_tracer("weather-service.mcp")

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

def traced_span(span_name: str, *, success_attribute: str, attribute_fn=None):
    attribute_fn = attribute_fn or (lambda *a, **kw: {})

    def decorator(func):
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                with tracer.start_as_current_span(span_name) as span:
                    for key, value in (attribute_fn(*args, **kwargs) or {}).items():
                        span.set_attribute(key, value)
                    try:
                        result = await func(*args, **kwargs)
                        span.set_attribute(success_attribute, True)
                        return result
                    except Exception as exc:
                        span.set_attribute(success_attribute, False)
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR))
                        raise

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                for key, value in (attribute_fn(*args, **kwargs) or {}).items():
                    span.set_attribute(key, value)
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute(success_attribute, True)
                    return result
                except Exception as exc:
                    span.set_attribute(success_attribute, False)
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR))
                    raise

        return sync_wrapper

    return decorator