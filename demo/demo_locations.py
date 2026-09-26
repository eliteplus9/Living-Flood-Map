"""Local demo for the locations -> geocode -> map pipeline.

Run this script directly to verify the pipeline independently of app.py.
It builds a tiny DataFrame of example tweets, extracts locations, geocodes
unique names, and writes a demo HTML map to `demo/demo_map.html`.
"""
from pathlib import Path
import pandas as pd

from src.locations import batch_extract_locations, canonicalize_mentions
from src.geocode import Geocoder
from src.map_view import create_map_from_rows


def main():
    demo_dir = Path(__file__).parent
    demo_map_file = demo_dir / "demo_map.html"

    # Stable demo tweets with explicit tweet_id values
    demo_data = [
        {"tweet_id": 1001, "tweet": "Flooding reported in Thunder Bay near the harbour."},
        {"tweet_id": 1002, "tweet": "Roads closed at Main St in Toronto due to water."},
        {"tweet_id": 1003, "tweet": "Saw water levels rising by Lake Superior."},
        {"tweet_id": 1004, "tweet": "No location here, just noise."},
        {"tweet_id": 1005, "tweet": "Heavy rain in Thunder Bay; reports mention Fort William nearby."},
    ]

    df = pd.DataFrame(demo_data)

    # Extract mentions (one row per tweet/mention)
    extracted = batch_extract_locations(df, tweet_col="tweet", tweet_id_col="tweet_id")
    print("Extracted mentions:\n", extracted)

    # Canonicalize mentions using Geocoder and context-aware heuristics
    gc = Geocoder(user_agent="living-flood-map-demo", min_delay_seconds=1.0)
    canonical = canonicalize_mentions(extracted, geocoder=gc, prefer_country='CA')
    print("Canonicalized mentions:\n", canonical)

    # Prepare rows for mapping: only resolved rows with coordinates
    rows = []
    for _, r in canonical.iterrows():
        if r['status'] == 'resolved' and pd.notna(r['latitude']) and pd.notna(r['longitude']):
            rows.append({
                "tweet": df.loc[df['tweet_id'] == r['tweet_id'], 'tweet'].iat[0],
                "location_name": r['canonical_name'],
                "latitude": float(r['latitude']),
                "longitude": float(r['longitude']),
            })

    if not rows:
        print("No geocoded rows to map; exiting.")
        return

    # Create map and save
    m = create_map_from_rows(rows)
    m.save(demo_map_file.as_posix())
    print(f"Demo map saved to: {demo_map_file}")


if __name__ == "__main__":
    main()
