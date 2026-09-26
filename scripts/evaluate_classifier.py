"""Evaluate the supplied sample and run the complete CSV without external calls."""

import hashlib
import json
from pathlib import Path
from time import perf_counter

from src.classify import classify_tweets
from src.data import load_data

ROOT = Path(__file__).resolve().parents[1]


def metric(truth, pred):
    tp = sum(a and b for a, b in zip(truth, pred))
    fp = sum(not a and b for a, b in zip(truth, pred))
    fn = sum(a and not b for a, b in zip(truth, pred))
    tn = sum(not a and not b for a, b in zip(truth, pred))
    return {
        "accuracy": (tp + tn) / len(truth),
        "precision": tp / max(1, tp + fp),
        "recall": tp / max(1, tp + fn),
        "f1": 2 * tp / max(1, 2 * tp + fp + fn),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def main():
    labels = json.loads((ROOT / "tests/supplied_sample_labels.json").read_text())
    digest = hashlib.sha256(
        (ROOT / "data/main_contestant.csv").read_bytes()
    ).hexdigest()
    if digest != labels["dataset_sha256"]:
        raise ValueError(
            "Sample labels belong to a different dataset; do not evaluate by row number."
        )
    positive = labels["positive_source_rows"]
    negative = labels["negative_source_rows"]
    ids = positive + negative
    truth = [True] * len(positive) + [False] * len(negative)
    t = perf_counter()
    data = load_data()
    read_seconds = perf_counter() - t
    t = perf_counter()
    result = classify_tweets(data)
    seconds = perf_counter() - t
    sample = result.set_index("source_row").loc[ids]
    predicted = sample.is_relevant.tolist()
    baseline = [
        any(
            k in text.lower()
            for k in ["flood", "flooding", "inundation", "water", "evacuat"]
        )
        for text in sample.tweet
    ]
    errors = [
        {
            "source_row": i,
            "expected": bool(a),
            "actual": bool(b),
            "score": float(sample.loc[i].relevance_score),
        }
        for i, a, b in zip(ids, truth, predicted)
        if a != b
    ]
    summary = {
        "rows": len(result),
        "dataset_sha256": hashlib.sha256(
            (ROOT / "data/main_contestant.csv").read_bytes()
        ).hexdigest(),
        "read_seconds": read_seconds,
        "classification_seconds": seconds,
        "relevant_rows": int(result.is_relevant.sum()),
        "needs_review_rows": int(result.needs_review.sum()),
        "duplicate_rows": int(result.duplicate_of.ne("").sum()),
        "sample_size": len(ids),
        "sample_label_origin": labels["description"],
        "sample_metrics": metric(truth, predicted),
        "original_keyword_metrics": metric(truth, baseline),
        "sample_errors": errors,
    }
    (ROOT / "docs/evaluation.json").write_text(json.dumps(summary, indent=2) + "\n")
    result.to_csv(ROOT / "data/classified_tweets.csv", index=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
