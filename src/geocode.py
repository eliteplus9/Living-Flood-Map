"""Geocoding utilities using geopy with caching, candidate lookup,
and simple canonicalization heuristics.
"""
from typing import Dict, Iterable, Optional, Tuple, List, Any
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import math
import time


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # return kilometers between two lat/lon pairs
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(dlambda/2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class Geocoder:
    """Nominatim geocoder with candidate listing, caching and simple
    context-aware canonicalization helpers.

    Methods:
      - geocode_candidates(name, country_codes=None) -> list of candidate dicts
      - choose_candidate(name, candidates, context_coords=None, prefer_country='CA') -> chosen candidate or None
    """

    def __init__(self, user_agent: str = "living-flood-map", min_delay_seconds: float = 1.0, domain: Optional[str] = None, strict_errors: bool = False):
        self.geolocator = Nominatim(user_agent=user_agent, **({"domain": domain} if domain else {}))
        self._geocode = RateLimiter(self.geolocator.geocode, min_delay_seconds=min_delay_seconds, swallow_exceptions=not strict_errors)
        self.strict_errors = strict_errors
        self._cache: Dict[str, Optional[List[Dict[str, Any]]]] = {}

    def geocode_candidates(self, name: str, country_codes: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Return a list of candidate places for `name` (may be None).

        Each candidate is a dict with keys: `display_name`, `lat`, `lon`, and any
        geopy location attributes that help scoring.
        """
        if not name:
            return None
        key = f"candidates:{name}:{country_codes or ''}"
        if key in self._cache:
            return self._cache[key]

        try:
            # Use exactly_one=False to get multiple candidates
            locs = self._geocode(name, exactly_one=False, country_codes=country_codes, addressdetails=True)
            candidates: List[Dict[str, Any]] = []
            if not locs:
                self._cache[key] = None
                return None
            for loc in locs:
                try:
                    raw = getattr(loc, 'raw', {}) or {}
                    display = raw.get('display_name') or getattr(loc, 'address', None) or str(raw)
                    cand = {
                        "display_name": display,
                        "lat": float(loc.latitude),
                        "lon": float(loc.longitude),
                        "raw": raw,
                        "importance": float(raw.get('importance') or 0),
                    }
                    candidates.append(cand)
                except Exception:
                    continue
            self._cache[key] = candidates
            return candidates
        except Exception:
            if self.strict_errors:
                raise
            self._cache[key] = None
            return None

    def choose_candidate(self, name: str, candidates: List[Dict[str, Any]], context_coords: Optional[List[Tuple[float, float]]] = None, prefer_country: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Pick the best candidate using simple heuristics.

        - Prefer candidates with the `prefer_country` in display_name if present.
        - If context_coords provided, prefer candidates geographically closest to any context point.
        - Otherwise prioritize by importance (if present) or display_name specificity.
        """
        if not candidates:
            return None

        # prefer candidates that explicitly include the country or common country markers
        preferred = []
        for c in candidates:
            dn = (c.get('display_name') or '').lower()
            # Only apply a country bias when caller explicitly provided one.
            if prefer_country and prefer_country.lower() in dn:
                preferred.append(c)
        pool = preferred or candidates

        # If the mention looks like a geographic feature (lake/river/mount), prefer natural/water classes
        lower_name = (name or '').lower()
        if 'lake' in lower_name or 'river' in lower_name or 'mount' in lower_name:
            nat = [c for c in pool if (c.get('raw', {}).get('class') in ('natural', 'water') or 'lake' in (c.get('display_name') or '').lower())]
            if nat:
                pool = nat

        # If context coords exist, prefer candidates that are geographically close to any context point.
        if context_coords:
            cand_dists = []
            for c in pool:
                min_d = float('inf')
                for (ctx_lat, ctx_lon) in context_coords:
                    try:
                        d = _haversine(ctx_lat, ctx_lon, c['lat'], c['lon'])
                        if d < min_d:
                            min_d = d
                    except Exception:
                        continue
                cand_dists.append((c, min_d))

            # prefer candidates within 50 km if any
            local = [c for c, d in cand_dists if d <= 50]
            if local:
                best = min([(c, d) for c, d in cand_dists if d <= 50], key=lambda x: x[1])[0]
                return best

            # otherwise prefer candidates within 200 km
            nearby = [c for c, d in cand_dists if d <= 200]
            if nearby:
                best = min([(c, d) for c, d in cand_dists if d <= 200], key=lambda x: x[1])[0]
                return best

            # fall back to scoring if no reasonably local candidates

        # otherwise sort by importance (if available) then by display_name length
        def score(cand: Dict[str, Any]) -> float:
            imp = float(cand.get('importance') or 0)
            spec = float(len(cand.get('display_name') or '')) / 100.0
            return imp + spec

        chosen = max(pool, key=score)
        return chosen


__all__ = ["Geocoder"]


def geocode_locations(locations: Iterable[str], geocoder: Optional[Geocoder] = None, prefer_country: Optional[str] = None) -> List[Dict[str, Any]]:
    """Compatibility wrapper to geocode a sequence of location name strings.

    Returns a list of dict rows compatible with the mapping helper used by
    the Streamlit app: each row contains `tweet`, `location_name`, `latitude`,
    and `longitude`. Unresolved names are omitted.
    """
    g = geocoder or Geocoder()
    rows: List[Dict[str, Any]] = []
    if not locations:
        return rows

    for name in locations:
        if not name:
            continue
        # perform country-biased lookup only when prefer_country provided
        country_codes = prefer_country.lower() if prefer_country else None
        candidates = g.geocode_candidates(name, country_codes=country_codes) or []
        chosen = g.choose_candidate(name, candidates, context_coords=None, prefer_country=prefer_country)
        if chosen:
            rows.append({
                "tweet": "",
                "location_name": chosen.get("display_name") or name,
                "latitude": chosen.get("lat"),
                "longitude": chosen.get("lon"),
            })

    return rows


# Export the backwards-compatible wrapper
__all__.append("geocode_locations")
