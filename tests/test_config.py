import pytest

from app import config


@pytest.fixture(autouse=True)
def clear_settings_cache():
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_get_settings_uses_environment(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "custom-service")

    settings = config.get_settings()

    assert settings.otel_endpoint == "http://collector:4318"
    assert settings.otel_service_name == "custom-service"


def test_get_settings_is_cached(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)

    first = config.get_settings()
    second = config.get_settings()

    assert first is second
    assert first.otel_service_name == "python-mcp"
