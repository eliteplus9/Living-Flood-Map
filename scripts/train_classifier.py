"""Rebuild the portable model from explicitly selected public training events.
Run from repository root: python -m scripts.train_classifier
Training only: scikit-learn>=1.4 (inference needs only the existing pandas).
"""

import gzip
import hashlib
import json
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

from src.data import load_data, normalize_tweet
from src.text_model import RelevanceModel, features

ROOT = Path(__file__).resolve().parents[1]
REV = "d67cddd51131dbb28842209014f67cffe359ff42"
EVENTS = [
    "2012_Sandy_Hurricane",
    "2013_Boston_Bombings",
    "2013_Oklahoma_Tornado",
    "2013_Queensland_Floods",
    "2013_West_Texas_Explosion",
]


def metrics(y, pred):
    return {
        k: round(float(fn(y, pred)), 4)
        for k, fn in [
            ("accuracy", accuracy_score),
            ("precision", precision_score),
            ("recall", recall_score),
            ("f1", f1_score),
        ]
    }


def fit(texts, labels):
    vector = TfidfVectorizer(
        analyzer=features, sublinear_tf=True, min_df=2, max_features=50000
    )
    matrix = vector.fit_transform(texts)
    model = LogisticRegression(C=4.0, max_iter=500, random_state=26).fit(matrix, labels)
    return vector, model


def main():
    training = ROOT / "data/training"
    training.mkdir(parents=True, exist_ok=True)
    frames, sources = [], []
    for event in EVENTS:
        url = f"https://raw.githubusercontent.com/sajao/CrisisLex/{REV}/data/CrisisLexT6/{event}/{event}-ontopic_offtopic.csv"
        path = training / f"{event}.csv"
        if not path.exists():
            path.write_bytes(urllib.request.urlopen(url, timeout=60).read())
        frame = pd.read_csv(path)
        frame.columns = frame.columns.str.strip()
        frame["text"] = frame["tweet"].map(normalize_tweet)
        frame["target"] = frame["label"].map({"on-topic": 1, "off-topic": 0})
        if frame["target"].isna().any():
            raise ValueError(f"Unknown labels in {event}")
        frame["event"] = event
        frames.append(frame[["tweet", "text", "target", "event"]])
        sources.append(
            {
                "event": event,
                "url": url,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    rows = pd.concat(frames, ignore_index=True)
    n_raw = len(rows)
    # Keep the entire supplied event out of training, plus any exact normalized
    # overlap in other events (including reposts with changed URLs/handles).
    supplied = set(load_data()["normalized_tweet"])
    overlap = rows["text"].isin(supplied)
    n_overlap = int(overlap.sum())
    rows = rows[~overlap & rows["text"].ne("")]
    conflicts = rows.groupby("text")["target"].nunique()
    rows = rows[~rows["text"].isin(conflicts[conflicts > 1].index)].drop_duplicates(
        "text"
    )
    train, test = train_test_split(
        rows, test_size=0.2, random_state=26, stratify=rows["target"]
    )
    vector, model = fit(train["text"], train["target"])
    probabilities = model.predict_proba(vector.transform(test["text"]))[:, 1]
    result = metrics(test["target"], probabilities >= 0.5)
    payload = {
        "format": 1,
        "version": "crisislex-no-alberta-v1",
        "intercept": float(model.intercept_[0]),
        "weights": {
            term: [float(vector.idf_[i]), float(model.coef_[0][i])]
            for term, i in vector.vocabulary_.items()
        },
    }
    portable = RelevanceModel(payload)
    portable_p = np.array([portable.score(t)[0] for t in test["text"]])
    error = float(np.max(np.abs(probabilities - portable_p)))
    assert error < 1e-10, error
    # Stress test transfer to a flood event absent from this temporary model.
    cross_train = rows[rows.event.ne("2013_Queensland_Floods")]
    cross_test = rows[rows.event.eq("2013_Queensland_Floods")]
    cv, cm = fit(cross_train.text, cross_train.target)
    cross = metrics(cross_test.target, cm.predict(cv.transform(cross_test.text)))
    output = ROOT / "models"
    output.mkdir(exist_ok=True)
    (output / "relevance.json.gz").write_bytes(
        gzip.compress(json.dumps(payload, separators=(",", ":")).encode(), mtime=0)
    )
    metadata = {
        "version": payload["version"],
        "source": "CrisisLexT6",
        "sources": sources,
        "excluded_event": "2013_Alberta_Floods",
        "raw_rows": n_raw,
        "supplied_overlap_removed": n_overlap,
        "deduplicated_rows": len(rows),
        "train_rows": len(train),
        "test_rows": len(test),
        "threshold": 0.5,
        "features": len(vector.vocabulary_),
        "heldout_metrics": result,
        "cross_event_queensland_metrics": cross,
        "portable_probability_max_error": error,
        "limitations": [
            "English only; not calibrated on unseen events.",
            "Generic disaster relevance, not verification or event identity.",
            "No supplied-event labels fetched or used.",
            "Final bundled model retains the 20% test split; test rows are not refit.",
        ],
    }
    from src.classify import classify_tweets

    metadata["hybrid_heldout_metrics"] = metrics(
        test.target, classify_tweets(test[["tweet"]], model=portable).is_relevant
    )
    baseline = test.tweet.map(
        lambda t: any(
            k in t.lower()
            for k in ["flood", "flooding", "inundation", "water", "evacuat"]
        )
    )
    metadata["original_keyword_heldout_metrics"] = metrics(test.target, baseline)
    (output / "model_card.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
