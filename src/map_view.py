"""Map rendering helpers using folium.

This module returns folium.Map objects which can be embedded by different
frontends (Streamlit via streamlit-folium, or a FastAPI endpoint).
"""
from typing import List, Dict, Optional
import folium


def create_map(points: List[Dict[str, float]], start_location: Optional[List[float]] = None, zoom_start: int = 6) -> folium.Map:
    """Create a folium map with markers for the provided geocoded points.

    Args:
        points: List of dicts with `name`, `lat`, `lon` keys.
        start_location: Optional [lat, lon] to center the map. If not provided,
            the first point is used.
        zoom_start: Integer zoom level.

    Returns:
        A folium.Map instance.
    """
    if not points:
        center = start_location or [45.0, -82.0]
    else:
        center = start_location or [points[0]["lat"], points[0]["lon"]]

    m = folium.Map(location=center, zoom_start=zoom_start)
    for p in points:
        try:
            folium.Marker([p["lat"], p["lon"]], popup=p.get("name")).add_to(m)
        except Exception:
            continue
    return m
