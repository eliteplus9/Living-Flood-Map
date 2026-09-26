"""Geocoding utilities using geopy.

Functions here perform geocoding given textual location mentions and return
latitude/longitude pairs. These are synchronous wrappers around geopy and
are intentionally independent of any UI framework.
"""
from typing import List, Dict, Optional
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter


def geocode_locations(names: List[str], user_agent: Optional[str] = "living-flood-map") -> List[Dict[str, float]]:
    """Geocode a list of location names using Nominatim (OpenStreetMap).

    Args:
        names: Iterable of location strings.
        user_agent: User agent string for Nominatim.

    Returns:
        List of dicts with keys: `name`, `lat`, `lon` for successfully geocoded names.
    """
    geolocator = Nominatim(user_agent=user_agent)
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
    results = []
    seen = set()
    for name in names:
        if not name or name in seen:
            continue
        try:
            loc = geocode(name)
            if loc:
                results.append({"name": name, "lat": loc.latitude, "lon": loc.longitude})
                seen.add(name)
        except Exception:
            # Keep going on errors (network, rate limits, etc.)
            continue
    return results
