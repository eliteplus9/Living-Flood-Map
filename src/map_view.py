"""Map rendering helpers using folium.

Accepts rows (or DataFrames) containing `tweet`, `location_name`,
`latitude`, and `longitude` and returns a Folium map with clustered
clickable markers whose popup contains the location name and source tweet.
"""
from typing import Iterable, List, Optional
import folium
import math
import html
import os
from dotenv import load_dotenv


# Load environment variables from a .env file if present. We do this at
# module import time so callers get a clear error early if the key is
# missing. The key itself is never printed or logged.
load_dotenv()
_CARTO_KEY = os.getenv("CARTO_BASEMAP_KEY")
# Do not raise at import time if CARTO key is missing; only require it when
# rendering a CARTO-backed TileLayer. This prevents import-time failures in
# environments where the key is intentionally not set (e.g. CI, tests).

try:
    from folium.plugins import MarkerCluster
    _HAS_CLUSTER = True
except Exception:
    MarkerCluster = None
    _HAS_CLUSTER = False


def _compute_center(points: List[tuple]) -> List[float]:
    # compute mean latitude/longitude of valid points
    if not points:
        return [45.0, -82.0]
    lat_sum = 0.0
    lon_sum = 0.0
    count = 0
    for lat, lon in points:
        if lat is None or lon is None or math.isnan(lat) or math.isnan(lon):
            continue
        lat_sum += lat
        lon_sum += lon
        count += 1
    if count == 0:
        return [45.0, -82.0]
    return [lat_sum / count, lon_sum / count]


def create_map_from_rows(rows: Iterable[dict], start_location: Optional[List[float]] = None, zoom_start: int = 6) -> folium.Map:
    """Create an interactive Folium map from rows with lat/lon.

    Args:
        rows: Iterable of dict-like objects containing keys:
            `tweet`, `location_name`, `latitude`, `longitude`.
        start_location: Optional explicit center [lat, lon]. If not
            provided the mean of valid coordinates is used.
        zoom_start: Initial folium zoom level.

    Returns:
        folium.Map instance.
    """
    points = []
    entries = []
    for r in rows:
        try:
            lat = float(r.get("latitude"))
            lon = float(r.get("longitude"))
        except Exception:
            continue
        points.append((lat, lon))
        entries.append({
            "lat": lat,
            "lon": lon,
            "location_name": str(r.get("location_name", "")),
            "tweet": str(r.get("tweet", "")),
        })

    center = start_location or _compute_center(points)
    # Create the map without a default tile layer to avoid Folium adding
    # the OpenStreetMap layer automatically (which can produce 403s).
    m = folium.Map(location=center, zoom_start=zoom_start, tiles=None)

    # Add a basemap. Prefer CARTO Positron when a key is available, otherwise
    # fall back to standard OpenStreetMap tiles so importing the module does
    # not fail when no CARTO key is present.
    if _CARTO_KEY:
        tile_url = f"https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png?key={_CARTO_KEY}"
        folium.TileLayer(tiles=tile_url, attr="© OpenStreetMap contributors © CARTO", name="CartoDB Positron").add_to(m)
    else:
        folium.TileLayer(tiles="OpenStreetMap", name="OpenStreetMap").add_to(m)

    if _HAS_CLUSTER:
        cluster = MarkerCluster()
        m.add_child(cluster)
        add_target = cluster
    else:
        add_target = m

    for e in entries:
        name = html.escape(e["location_name"])
        tweet = html.escape(e["tweet"]) or "(no text)"
        popup_html = f"<b>{name}</b><br/><small>{tweet}</small>"
        popup = folium.Popup(popup_html, max_width=400)
        marker = folium.Marker(location=[e["lat"], e["lon"]], popup=popup)
        try:
            marker.add_to(add_target)
        except Exception:
            # ignore faulty marker additions
            continue

    return m


def create_map(rows: Iterable[dict], start_location: Optional[List[float]] = None, zoom_start: int = 6) -> folium.Map:
    """Compatibility wrapper expected by older `app.py`.

    Accepts an iterable of geocoded rows (dictionaries) and returns a folium.Map.
    This mirrors the earlier `create_map` signature so `from src.map_view import create_map`
    continues to work for existing UI code.
    """
    return create_map_from_rows(rows, start_location=start_location, zoom_start=zoom_start)


__all__ = ["create_map_from_rows", "create_map"]
