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


def test_global_default_handles_distant_places_without_country_bias():
    mentions = pd.DataFrame([
        {'tweet_id': 'global-1', 'tweet': 'Toronto and Thunder Bay', 'mention': 'Toronto'},
        {'tweet_id': 'global-1', 'tweet': 'Toronto and Thunder Bay', 'mention': 'Thunder Bay'},
    ])
    output = canonicalize_mentions(mentions, geocoder=FakeGeocoder())
    assert len(output) == 2
    assert set(output['status']).issubset({'resolved', 'ambiguous', 'unresolved'})


def test_northern_ontario_extraction_handles_case_hashtags_and_single_word_towns():
    from src.locations import extract_locations
    for text, expected in [
        ("flood warning: fort frances and nipigon", {"Fort Frances", "Nipigon"}),
        ("Nipigon roads are flooded", {"Nipigon"}),
        ("Evacuations #FortFrances #SiouxLookout #RedLake", {"Fort Frances", "Sioux Lookout", "Red Lake"}),
        ("Road washed out near Atikokan and Kenora", {"Atikokan", "Kenora"}),
        ("flood warning in marathon and near emo", {"Marathon", "Emo"}),
    ]:
        assert expected.issubset(set(extract_locations(text)))
    assert extract_locations("flooding in Nipigon roads are closed") == ["Nipigon"]
    assert extract_locations("my movie marathon and emo playlist") == []
    assert extract_locations("https://example.com/nipigon/fort-frances") == []
    assert "Tokyo" in extract_locations("Flood warning in Tokyo today")


def test_northern_towns_preserve_source_ids_and_do_not_define_relevance():
    from src.locations import batch_extract_locations
    from src.classify import classify_tweets
    source = pd.DataFrame([
        {"tweet_id": "north-1", "tweet": "Flood warning in Fort Frances"},
        {"tweet_id": "north-2", "tweet": "Flood warning in Nipigon"},
        {"tweet_id": "north-3", "tweet": "Coffee and a movie in Nipigon"},
    ])
    output = classify_tweets(source)
    assert output.iloc[0].is_relevant and output.iloc[1].is_relevant
    assert not output.iloc[2].is_relevant
    mentions = batch_extract_locations(source)
    assert set(mentions.tweet_id) == {"north-1", "north-2", "north-3"}
    assert mentions.loc[mentions.tweet_id == "north-1", "tweet"].iloc[0] == source.iloc[0].tweet
