from pydantic import BaseModel, Field
from typing import Annotated
import logging
import httpx
from fastmcp import FastMCP, Context
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .logging_utils import setup_logging, setup_tracing_basic
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

setup_logging()

tracer = trace.get_tracer("weather-service.mcp")
logger = logging.getLogger("weather-service")

mcp = FastMCP("weather-service")

mcp_app = mcp.http_app(
    path="/mcp",
    stateless_http=True
)

app = FastAPI(
    title="Weather MCP Server",
    description="An MCP Example Server",
    lifespan=mcp_app.lifespan
)
app.mount("/mcp-server", mcp_app)
setup_tracing_basic()

class WeatherRequest(BaseModel):
    city: str = Field(..., description="City to get weather for")

class WeatherResponse(BaseModel):
    condition: str = Field(..., description="Current weather conditions")
    temp_f: float = Field(..., description="Temperature in Farenheit")
    wind_mph: float = Field(..., description="Wind speed in mph")

async def _get_weather_impl(city: str) -> WeatherResponse:
    """Fetch current weather for a city"""
    logger.info("Fetching weather", extra={"city": city})
    async with httpx.AsyncClient() as client:
        response = await client.get(
             f"https://api.weatherapi.com/v1/current.json",
            params={"q": city, "key": '149ccae2d2e04db39f7232644251911'}
        )
        response_json = response.json()
        return WeatherResponse(
            condition=response_json['current']['condition']['text'],
            temp_f=response_json['current']['temp_f'],
            wind_mph=response_json['current']['wind_mph']
        )

@app.post("/get_weather", tags=["weather"])
async def get_weather_rest(req: WeatherRequest) -> WeatherResponse:
    return await _get_weather_impl(req.city) 

@mcp.tool(tags=["weather"])
async def get_weather(ctx:Context, city: Annotated[str, "City to get weather for"]) -> WeatherResponse:
    """Fetch current weather for a city"""
    with tracer.start_as_current_span("mcp.tool.get_weather") as span:
        span.set_attribute("weather.city", city)
        try:
            weather = await _get_weather_impl(city)
            span.set_attribute("mcp.tool.success", True)
            return weather
        except Exception as e:
            span.set_attribute("mcp.tool.success", False)
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR))
            raise
       
@mcp.resource("weather://forecast/{city}")
async def weather_forecast(city: str) -> WeatherResponse:
    """Get 7-day forecast as a resource"""
    return await _get_weather_impl(city)

@mcp.prompt("greeting_prompt")
def greeting_prompt(name: str):
    """A reusable MCP prompt that returns a formatted prompt."""
    return f"Write a warm, friendly greeting for {name}."

@app.get("/healthz", include_in_schema=False)
def healthz():
    """Health Check"""
    return JSONResponse({"status": "OK"})
