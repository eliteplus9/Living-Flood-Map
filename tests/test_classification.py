import io

import pandas as pd
import pytest

from src.classify import classify_tweets
from src.data import (
    DataValidationError,
    normalize_tweet,
    prepare_tweets,
    read_uploaded_csv,
)


def test_upload_preserves_quoted_commas_newlines_blanks_and_na_text():
    frame = read_uploaded_csv(
        io.BytesIO(
            b'\xef\xbb\xbftweet,extra\r\n"Flooding, bridge shut",a\r\n"two\nlines",b\r\n,c\r\nNA,d\r\n'
        )
    )
    assert frame.tweet.tolist() == ["Flooding, bridge shut", "two\nlines", "", "NA"]
    assert frame.source_row.tolist() == [0, 1, 2, 3]
    assert frame.extra.tolist() == ["a", "b", "c", "d"]


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"wrong\nabc",
        b"tweet,tweet\na,b",
        b"tweet\na,b",
        b'tweet\n"unclosed',
        b"tweet\n\xff",
    ],
)
def test_malformed_uploads_are_actionable(raw):
    with pytest.raises(DataValidationError):
        read_uploaded_csv(io.BytesIO(raw))


def test_ids_duplicates_and_filtered_rows_stay_aligned():
    original = pd.DataFrame(
        {"tweet": ["Bridge closed", "Bridge closed", None]}, index=[9, 2, 7]
    )
    before = original.copy(deep=True)
    prepared = prepare_tweets(original)
    assert prepared.tweet_id.is_unique
    assert prepared.duplicate_of.iloc[1] == prepared.tweet_id.iloc[0]
    assert prepared.tweet_id.tolist() == prepare_tweets(original).tweet_id.tolist()
    subset = prepared.iloc[[1, 0]]
    classified = classify_tweets(subset)
    assert classified.tweet_id.tolist() == subset.tweet_id.tolist()
    assert classified.index.tolist() == [2, 9]
    assert classified.source_row.tolist() == [1, 0]
    pd.testing.assert_frame_equal(original, before)


@pytest.mark.parametrize("ids", [["x", "x"], ["x", ""], ["x", None]])
def test_invalid_external_ids_rejected(ids):
    with pytest.raises(DataValidationError):
        prepare_tweets(pd.DataFrame({"tweet": ["a", "b"], "tweet_id": ids}))


def test_empty_and_header_only_have_full_schema():
    df = classify_tweets(read_uploaded_csv(io.BytesIO(b"tweet\n")))
    assert len(df) == 0
    assert {"tweet_id", "relevance", "category", "reason", "label"} <= set(df.columns)
    df = classify_tweets(pd.DataFrame({"tweet": [None, "", "  "]}))
    assert not df.is_relevant.any()
    assert df.relevance_score.eq(0).all()
    assert df.label.eq("noise").all()


def test_normalization_preserves_negation_and_original():
    text = "RT @person: No flooding here &amp; no evacuation. #NewTownFlood2026 https://example.com"
    cleaned = normalize_tweet(text)
    assert "no flooding" in cleaned and "no evacuation" in cleaned
    assert "flood" in cleaned and "https" not in cleaned and "@person" not in cleaned
    assert prepare_tweets(pd.DataFrame({"tweet": [text]})).tweet.iloc[0] == text


@pytest.mark.parametrize("threshold", [0, 1, -1, 2, float("nan"), float("inf")])
def test_invalid_threshold(threshold):
    with pytest.raises(ValueError):
        classify_tweets(pd.DataFrame({"tweet": ["x"]}), threshold=threshold)


def test_duplicates_scored_once_and_contract_is_consistent():
    class Model:
        version = "fixture"
        calls = 0

        def score(self, text):
            self.calls += 1
            return 0.6, ["bridge"], 0.8

    model = Model()
    result = classify_tweets(
        pd.DataFrame({"tweet": ["Bridge closed", "Bridge closed", ""]}), model
    )
    assert model.calls == 1
    assert result.label.tolist() == ["flood", "flood", "noise"]
    assert result.relevance.tolist() == ["relevant", "relevant", "unrelated"]
    assert result.needs_review.tolist() == [True, True, False]
    assert result.relevance_score.between(0, 1).all()
    assert result.classifier_version.eq("fixture").all()


def test_unfamiliar_language_is_flagged():
    result = classify_tweets(
        pd.DataFrame({"tweet": ["洪水が家に入ってきた", "zzzyxqv xxyqz"]})
    )
    assert result.needs_review.all()


def test_real_model_basic_signal_vs_chatter():
    result = classify_tweets(
        pd.DataFrame(
            {
                "tweet": [
                    "Severe flooding has forced thousands of people to evacuate their homes.",
                    "Drinking a glass of water while watching my favorite movie.",
                    "The river has overflowed and flooded the road. Rescue teams are here.",
                    "Happy birthday! Have fun at your party tonight.",
                ]
            }
        )
    )
    assert result.is_relevant.tolist() == [True, False, True, False]


@pytest.mark.parametrize(
    "tweet,expected",
    [
        ("My inbox is flooded with emails.", False),
        ("A flood of memories came back to me.", False),
        ("Floodlight tickets are on sale.", False),
        ("Families need clean blankets at the evacuation shelter.", True),
        ("I love the song Flood by Jars of Clay.", False),
        ("Unusual situation downtown #NewPlaceFlood2026", True),
        (
            "No flooding here today.",
            True,
        ),  # Relatedness is not a claim that flooding occurred.
    ],
)
def test_hybrid_relevance_boundaries(tweet, expected):
    row = classify_tweets(pd.DataFrame({"tweet": [tweet]})).iloc[0]
    assert bool(row.is_relevant) == expected
    assert 0 <= row.model_score <= 1


def test_url_fragment_is_not_an_event_hashtag():
    row = classify_tweets(
        pd.DataFrame({"tweet": ["Happy birthday https://example.org/#flood"]})
    ).iloc[0]
    assert row.classification_method == "text_model"


def test_invalid_injected_model_score_is_not_silently_accepted():
    class BadModel:
        def score(self, text):
            return float("nan"), [], 1

    with pytest.raises(ValueError):
        classify_tweets(pd.DataFrame({"tweet": ["hello"]}), BadModel())
