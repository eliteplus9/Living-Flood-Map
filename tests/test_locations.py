import pandas as pd
from src.locations import canonicalize_mentions

class FakeGeocoder:
    def geocode_candidates(self, name, country_codes=None):
        mapping = {
            'Thunder Bay': [
                {'display_name': 'Thunder Bay, Thunder Bay District, Northwestern Ontario, Ontario, Canada', 'lat': 48.406414, 'lon': -89.259796, 'importance': 0.6, 'raw': {'class': 'place'}}
            ],
            'Toronto': [
                {'display_name': 'Toronto, Golden Horseshoe, Ontario, Canada', 'lat': 43.653482, 'lon': -79.383935, 'importance': 0.7, 'raw': {'class': 'place'}}
            ],
            'Fort William': [
                {'display_name': "Fort William, St. John's, Newfoundland, Newfoundland and Labrador, Canada", 'lat': 47.573632, 'lon': -52.700473, 'importance': 0.16, 'raw': {'class': 'place'}},
                {'display_name': 'Fort William, McKellar, Thunder Bay, Thunder Bay District, Northwestern Ontario, Ontario, Canada', 'lat': 48.382409, 'lon': -89.245615, 'importance': 0.14, 'raw': {'class': 'place'}}
            ],
            'Main St': [
                {'display_name': 'Main Street, Toronto, Ontario, Canada', 'lat': 43.689041, 'lon': -79.301621, 'importance': 0.2, 'raw': {'class': 'highway'}}
            ],
            'Lake Superior': [
                {'display_name': 'Lake Superior', 'lat': 47.7, 'lon': -84.5, 'importance': 0.75, 'raw': {'class': 'natural'}}
            ]
        }
        return mapping.get(name, [])

    def choose_candidate(self, name, candidates, context_coords=None, prefer_country='CA'):
        # If Fort William and Thunder Bay present in context, pick the Thunder Bay candidate
        if name == 'Fort William' and context_coords:
            for c in candidates:
                if abs(c['lon'] + 89.245615) < 1.0:
                    return c
        return candidates[0] if candidates else None


def make_mentions():
    # Construct df_mentions with multiple mentions per tweet as in demo
    rows = [
        {'tweet_id': 1001, 'tweet': 'Flooding reported in Thunder Bay near the harbour.', 'mention': 'Thunder Bay'},
        {'tweet_id': 1002, 'tweet': 'Roads closed at Main St in Toronto due to water.', 'mention': 'Toronto'},
        {'tweet_id': 1002, 'tweet': 'Roads closed at Main St in Toronto due to water.', 'mention': 'Main St'},
        {'tweet_id': 1003, 'tweet': 'Saw water levels rising by Lake Superior.', 'mention': 'Lake Superior'},
        # both Thunder Bay and Fort William in same tweet_id to test context
        {'tweet_id': 1005, 'tweet': 'Heavy rain in Thunder Bay; reports mention Fort William nearby.', 'mention': 'Thunder Bay'},
        {'tweet_id': 1005, 'tweet': 'Heavy rain in Thunder Bay; reports mention Fort William nearby.', 'mention': 'Fort William'},
    ]
    return pd.DataFrame(rows)


def test_canonical_output_contract_and_values():
    df_mentions = make_mentions()
    geocoder = FakeGeocoder()
    out = canonicalize_mentions(df_mentions, geocoder=geocoder, prefer_country='CA')

    # exact columns
    expected_cols = ['tweet_id', 'mention', 'canonical_name', 'latitude', 'longitude', 'location_score', 'status']
    assert list(out.columns) == expected_cols

    # Convert to dict keyed by (tweet_id, mention)
    lookup = {(int(r.tweet_id), r.mention): r for r in out.itertuples()}

    # Thunder Bay resolves to Thunder Bay, ON
    tb = lookup[(1001, 'Thunder Bay')]
    assert 'Thunder Bay' in tb.canonical_name
    assert abs(tb.latitude - 48.406414) < 0.001
    assert abs(tb.longitude - (-89.259796)) < 0.001
    assert tb.status == 'resolved'

    # Toronto resolves to Toronto, ON
    tor = lookup[(1002, 'Toronto')]
    assert 'Toronto' in tor.canonical_name
    assert abs(tor.latitude - 43.653482) < 0.001
    assert tor.status == 'resolved'

    # Fort William with Thunder Bay context resolves to Thunder Bay candidate
    fw = lookup[(1005, 'Fort William')]
    assert 'Thunder Bay' in fw.canonical_name
    assert abs(fw.latitude - 48.382409) < 0.01
    assert fw.status == 'resolved'

    # Main St remains unresolved (bare street)
    ms = lookup[(1002, 'Main St')]
    import pandas as _pd
    assert _pd.isna(ms.canonical_name)
    assert ms.status == 'unresolved'

    # Lake Superior prefers lake/natural
    ls = lookup[(1003, 'Lake Superior')]
    assert 'Lake Superior' in ls.canonical_name
    assert ls.status == 'resolved'
