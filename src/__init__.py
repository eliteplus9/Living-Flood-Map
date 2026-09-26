"""Living Flood Map core package with optional frontend dependencies loaded lazily."""

from importlib import import_module

__version__ = "0.1.0"
_EXPORTS = {
    "load_data": "data",
    "read_uploaded_csv": "data",
    "classify_tweets": "classify",
    "extract_locations": "locations",
    "batch_extract_locations": "locations",
    "geocode_locations": "geocode",
    "Geocoder": "geocode",
    "create_map": "map_view",
    "create_map_from_rows": "map_view",
    "semantic_search": "rag",
    "summarize_reports": "rag",
}
__all__ = list(_EXPORTS)

def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{_EXPORTS[name]}", __name__), name)
    globals()[name] = value
    return value
