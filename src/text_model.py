"""Portable TF-IDF logistic inference. JSON weights only; no pickle or network."""

import gzip
import json
import math
import re
from collections import Counter
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

MODEL_PATH = Path(__file__).resolve().parents[1] / "models/relevance.json.gz"
TOKEN_PATTERN = re.compile(r"(?u)\b\w\w+\b")


def features(text):
    words = TOKEN_PATTERN.findall(text.lower())
    return words + [a + " " + b for a, b in pairwise(words)]


class RelevanceModel:
    def __init__(self, payload):
        if payload.get("format") != 1:
            raise ValueError("Unsupported relevance model format.")
        self.weights = payload["weights"]
        self.intercept = payload["intercept"]
        self.version = payload["version"]

    def score(self, text):
        counts = Counter(features(text))
        active = [
            (term, (1 + math.log(count)) * self.weights[term][0], self.weights[term][1])
            for term, count in counts.items()
            if term in self.weights
        ]
        norm = math.sqrt(sum(value * value for _, value, _ in active)) or 1.0
        contributions = [(term, value * coef / norm) for term, value, coef in active]
        logit = self.intercept + sum(value for _, value in contributions)
        score = 1 / (1 + math.exp(-max(-40, min(40, logit))))
        strongest = sorted(contributions, key=lambda pair: pair[1], reverse=True)[:3]
        terms = [term for term, value in strongest if value > 0]
        return score, terms, len(active) / max(1, len(counts))


@lru_cache(maxsize=1)
def load_model():
    try:
        with gzip.open(MODEL_PATH, "rt", encoding="utf-8") as source:
            return RelevanceModel(json.load(source))
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Bundled model missing. Restore models/relevance.json.gz from the classification branch."
        ) from exc
