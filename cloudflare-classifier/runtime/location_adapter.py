"""Mutasim's resolver with prefetched LocationIQ candidates; no tweet storage."""
import json
import math
import pandas as pd
from src.geocode import Geocoder
from src.locations import batch_extract_locations, canonicalize_mentions, _clean_mention


class PrefetchedGeocoder(Geocoder):
    def __init__(self, candidates):
        self.candidates = candidates

    def geocode_candidates(self, name, country_codes=None):
        return self.candidates.get((name, country_codes or ""), [])


async def locate(rows, country, gateway):
    from js import Object
    from pyodide.ffi import to_js
    mentions = batch_extract_locations(pd.DataFrame(rows))
    if mentions.empty:
        return {"results": [], "warnings": [], "model_version": "mutasim-locationiq-v1"}
    names = list(dict.fromkeys(_clean_mention(value) for value in mentions["mention"]))
    if len(names) > 40:
        raise ValueError("Too many place mentions; use smaller location batches.")
    candidates = {}
    for name in names:
        if len(name) > 240:
            candidates[(name, country or "")] = []
            continue
        for code in ([country.lower(), ""] if country else [""]):
            response = await gateway.fetch("https://geocoder.internal/search", to_js({"method": "POST",
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"mention": name, "country": code or None})}, dict_converter=Object.fromEntries))
            if not response.ok:
                raise RuntimeError("Geocoding provider unavailable or daily safety cap reached.")
            raw = json.loads(await response.text())
            converted = []
            for value in raw:
                lat, lon = float(value["lat"]), float(value["lon"])
                importance = float(value.get("importance", 0))
                if not math.isfinite(lat) or not math.isfinite(lon) or abs(lat) > 90 or abs(lon) > 180 or not math.isfinite(importance):
                    raise RuntimeError("Invalid provider coordinates.")
                converted.append({"display_name": value["display_name"], "lat": lat, "lon": lon,
                                  "importance": importance, "raw": value})
            candidates[(name, code)] = converted
            if converted:
                break
    result = canonicalize_mentions(mentions, geocoder=PrefetchedGeocoder(candidates), prefer_country=country)
    return {"results": json.loads(result.to_json(orient="records", double_precision=15)),
            "warnings": [], "model_version": "mutasim-locationiq-v1"}
