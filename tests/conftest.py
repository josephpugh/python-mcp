import asyncio
import inspect
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _ensure_fastmcp_stub():
    if "fastmcp" in sys.modules:
        return

    module = ModuleType("fastmcp")

    class DummyHTTPApp:
        def __init__(self):
            self.lifespan = None

        async def __call__(self, scope, receive, send):  # pragma: no cover - helper stub
            raise RuntimeError("fastmcp stub app cannot handle requests")

    class DummyFastMCP:
        def __init__(self, name):
            self.name = name

        def http_app(self, **kwargs):
            return DummyHTTPApp()

        def tool(self, **kwargs):
            return lambda fn: fn

        def resource(self, *args, **kwargs):
            return lambda fn: fn

        def prompt(self, *args, **kwargs):
            return lambda fn: fn

    module.FastMCP = DummyFastMCP
    module.Context = SimpleNamespace

    sys.modules["fastmcp"] = module


_ensure_fastmcp_stub()


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test as asynchronous for manual runner")


def pytest_pyfunc_call(pyfuncitem):
    test_fn = pyfuncitem.obj
    if inspect.iscoroutinefunction(test_fn):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(test_fn(**pyfuncitem.funcargs))
        finally:
            loop.close()
        return True
    return None
