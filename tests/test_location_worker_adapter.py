"""Exercise the Python Worker service-binding contract without provider calls."""
import asyncio
import importlib.util
import json
from pathlib import Path


def test_private_geocoder_binding_uses_keyword_fetch_options():
    spec = importlib.util.spec_from_file_location(
        "location_adapter", Path(__file__).parents[1] / "cloudflare-classifier/runtime/location_adapter.py"
    )
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)

    class Response:
        ok = True

        async def text(self):
            return json.dumps([{"display_name": "Nipigon, Ontario, Canada", "lat": "49.015", "lon": "-88.265", "importance": .6, "class": "place"}])

    class Gateway:
        async def fetch(self, resource, *, method, headers, body):
            assert resource == "https://geocoder.internal/search"
            assert method == "POST"
            assert json.loads(body) == {"mention": "Nipigon", "country": "ca"}
            return Response()

    output = asyncio.run(adapter.locate([
        {"tweet_id": "north-1", "tweet": "flood warning: nipigon", "source_row": 1}
    ], "CA", Gateway()))
    assert output["results"][0]["tweet_id"] == "north-1"
    assert output["results"][0]["status"] == "resolved"
    assert output["results"][0]["canonical_name"] == "Nipigon, Ontario, Canada"
