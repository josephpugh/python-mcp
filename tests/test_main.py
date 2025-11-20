import importlib
import sys

import pytest


@pytest.fixture
def main_module(monkeypatch):
    from app import logging_utils

    monkeypatch.setattr(logging_utils, "setup_logging", lambda: None)
    monkeypatch.setattr(logging_utils, "setup_tracing_basic", lambda: None)

    sys.modules.pop("app.main", None)
    module = importlib.import_module("app.main")
    return module


@pytest.mark.asyncio
async def test_get_weather_impl_returns_response(monkeypatch, main_module):
    payload = {
        "current": {
            "condition": {"text": "Sunny"},
            "temp_f": 72.5,
            "wind_mph": 5.0,
        }
    }
    captured = {}

    class DummyResponse:
        def json(self):
            return payload

    class DummyAsyncClient:
        async def __aenter__(self):
            captured["entered"] = True
            return self

        async def __aexit__(self, exc_type, exc, tb):
            captured["exited"] = True

        async def get(self, url, params=None):
            captured["request"] = {"url": url, "params": params}
            return DummyResponse()

    monkeypatch.setattr(main_module.httpx, "AsyncClient", lambda *args, **kwargs: DummyAsyncClient())

    result = await main_module._get_weather_impl("Boston")

    assert captured["request"]["url"] == "https://api.weatherapi.com/v1/current.json"
    assert captured["request"]["params"] == {
        "q": "Boston",
        "key": "149ccae2d2e04db39f7232644251911",
    }
    assert result.condition == "Sunny"
    assert result.temp_f == 72.5
    assert result.wind_mph == 5.0


@pytest.mark.asyncio
async def test_get_weather_rest_delegates_to_impl(monkeypatch, main_module):
    expected = main_module.WeatherResponse(condition="Clear", temp_f=55.0, wind_mph=10.0)
    called = {}

    async def fake_impl(city):
        called["city"] = city
        return expected

    monkeypatch.setattr(main_module, "_get_weather_impl", fake_impl)

    request = main_module.WeatherRequest(city="Madrid")
    result = await main_module.get_weather_rest(request)

    assert result is expected
    assert called["city"] == "Madrid"


@pytest.mark.asyncio
async def test_get_weather_tool_sets_span_attributes(monkeypatch, main_module):
    expected = main_module.WeatherResponse(condition="Rain", temp_f=60.0, wind_mph=3.0)

    async def fake_impl(city):
        return expected

    monkeypatch.setattr(main_module, "_get_weather_impl", fake_impl)

    class DummySpan:
        def __init__(self):
            self.attributes = {}
            self.status = None
            self.exceptions = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def set_attribute(self, key, value):
            self.attributes[key] = value

        def record_exception(self, exc):
            self.exceptions.append(exc)

        def set_status(self, status):
            self.status = status

    spans = []

    class DummyTracer:
        def start_as_current_span(self, name):
            span = DummySpan()
            spans.append((name, span))
            return span

    monkeypatch.setattr(main_module, "tracer", DummyTracer())

    result = await main_module.get_weather(None, "Lisbon")

    assert result is expected
    assert spans[0][0] == "mcp.tool.get_weather"
    span = spans[0][1]
    assert span.attributes["weather.city"] == "Lisbon"
    assert span.attributes["mcp.tool.success"] is True
    assert span.exceptions == []


@pytest.mark.asyncio
async def test_get_weather_tool_records_failures(monkeypatch, main_module):
    async def fake_impl(city):
        raise RuntimeError("external api failed")

    monkeypatch.setattr(main_module, "_get_weather_impl", fake_impl)

    class DummySpan:
        def __init__(self):
            self.attributes = {}
            self.set_status_calls = []
            self.exceptions = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def set_attribute(self, key, value):
            self.attributes[key] = value

        def record_exception(self, exc):
            self.exceptions.append(exc)

        def set_status(self, status):
            self.set_status_calls.append(status)

    spans = []

    class DummyTracer:
        def start_as_current_span(self, name):
            span = DummySpan()
            spans.append(span)
            return span

    monkeypatch.setattr(main_module, "tracer", DummyTracer())

    with pytest.raises(RuntimeError):
        await main_module.get_weather(None, "Oslo")

    span = spans[0]
    assert span.attributes["weather.city"] == "Oslo"
    assert span.attributes["mcp.tool.success"] is False
    assert isinstance(span.exceptions[0], RuntimeError)
    assert span.set_status_calls  # error status recorded


def test_greeting_prompt_formats_name(main_module):
    message = main_module.greeting_prompt("Cassie")
    assert "Cassie" in message
    assert "friendly" in message.lower()


def test_health_check_response(main_module):
    response = main_module.healthz()
    assert response.status_code == 200
    assert response.body == b'{"status":"OK"}'


@pytest.mark.asyncio
async def test_weather_resource_tracing(monkeypatch, main_module):
    expected = main_module.WeatherResponse(condition="Cloudy", temp_f=40.0, wind_mph=12.0)

    async def fake_impl(city):
        return expected

    monkeypatch.setattr(main_module, "_get_weather_impl", fake_impl)

    class DummySpan:
        def __init__(self):
            self.attributes = {}
            self.set_status_calls = []
            self.exceptions = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def set_attribute(self, key, value):
            self.attributes[key] = value

        def record_exception(self, exc):
            self.exceptions.append(exc)

        def set_status(self, status):
            self.set_status_calls.append(status)

    class DummyTracer:
        def __init__(self):
            self.spans = []

        def start_as_current_span(self, name):
            span = DummySpan()
            self.spans.append((name, span))
            return span

    tracer = DummyTracer()
    monkeypatch.setattr(main_module, "tracer", tracer)

    result = await main_module.weather_forecast("Rome")

    assert result is expected
    assert tracer.spans[0][0] == "mcp.resource.weather_forecast"
    span = tracer.spans[0][1]
    assert span.attributes["weather.city"] == "Rome"
    assert span.attributes["mcp.resource.success"] is True


def test_greeting_prompt_tracing(monkeypatch, main_module):
    class DummySpan:
        def __init__(self):
            self.attributes = {}
            self.set_status_calls = []
            self.exceptions = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def set_attribute(self, key, value):
            self.attributes[key] = value

        def record_exception(self, exc):
            self.exceptions.append(exc)

        def set_status(self, status):
            self.set_status_calls.append(status)

    class DummyTracer:
        def __init__(self):
            self.spans = []

        def start_as_current_span(self, name):
            span = DummySpan()
            self.spans.append((name, span))
            return span

    tracer = DummyTracer()
    monkeypatch.setattr(main_module, "tracer", tracer)

    message = main_module.greeting_prompt("Sky")

    assert "Sky" in message
    assert tracer.spans[0][0] == "mcp.prompt.greeting"
    span = tracer.spans[0][1]
    assert span.attributes["prompt.name"] == "Sky"
    assert span.attributes["mcp.prompt.success"] is True
