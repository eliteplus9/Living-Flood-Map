import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("locationiq_adapter", Path(__file__).parents[1] / "cloudflare-classifier/runtime/location_adapter.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

@pytest.fixture(autouse=True)
def ffi(monkeypatch):
    monkeypatch.setitem(sys.modules, "js", types.SimpleNamespace(Object=types.SimpleNamespace(fromEntries=None)))
    monkeypatch.setitem(sys.modules, "pyodide.ffi", types.SimpleNamespace(to_js=lambda value, **kwargs: value))

class Gateway:
    def __init__(self, ok=True, latitude="51.04"):
        self.calls, self.ok, self.latitude = [], ok, latitude

    async def fetch(self, url, options):
        payload = json.loads(options["body"])
        self.calls.append(payload)
        values = [] if payload["country"] else [{"lat": self.latitude, "lon": "-114.07", "importance": 0.8, "display_name": "Calgary, Alberta, Canada", "class": "place"}]
        async def text():
            return json.dumps(values)
        return types.SimpleNamespace(ok=self.ok, text=text)

ROWS = [{"tweet_id": "one", "tweet": "Flood in Calgary", "source_row": 1}]

def test_country_fallback_and_duplicate_text_ids():
    gateway = Gateway()
    output = asyncio.run(adapter.locate(ROWS + [{**ROWS[0], "tweet_id": "two", "source_row": 2}], "CA", gateway))
    assert gateway.calls == [{"mention": "Calgary", "country": "ca"}, {"mention": "Calgary", "country": None}]
    assert {row["tweet_id"] for row in output["results"]} == {"one", "two"}
    assert all(row["status"] == "resolved" for row in output["results"])

def test_outage_is_not_empty_results():
    with pytest.raises(RuntimeError, match="unavailable"):
        asyncio.run(adapter.locate(ROWS, None, Gateway(ok=False)))

def test_invalid_provider_coordinates_rejected():
    with pytest.raises(RuntimeError, match="coordinates"):
        asyncio.run(adapter.locate(ROWS, None, Gateway(latitude="999")))
