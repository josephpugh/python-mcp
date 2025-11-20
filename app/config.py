import os
from functools import lru_cache
from pydantic import BaseModel, Field


def _default_otel_endpoint() -> str | None:
    return os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")


def _default_service_name() -> str:
    return os.getenv("OTEL_SERVICE_NAME", "python-mcp")


class Settings(BaseModel):
    # Telemetry
    otel_endpoint: str | None = Field(default_factory=_default_otel_endpoint)
    otel_service_name: str = Field(default_factory=_default_service_name)


@lru_cache
def get_settings() -> Settings:
    return Settings()
