"""Offline disaster relevance classification with stable integration fields."""

import math
import re

from .data import prepare_tweets
from .text_model import load_model

CATEGORY_PATTERNS = (
    ("evacuation_rescue", r"\b(evacuat\w*|rescu\w*|stranded|shelter\w*)\b"),
    (
        "infrastructure",
        r"\b(road\w*|bridge\w*|highway\w*|power|electricity|outage\w*|water supply|drinking water|boil water)\b",
    ),
    (
        "relief_recovery",
        r"\b(donat\w*|volunteer\w*|relief|cleanup|clean up|supplies|fundrais\w*|red cross)\b",
    ),
    ("solidarity", r"\b(pray\w*|thoughts|solidarity|condolences)\b"),
)

# High-precision surface cues complement the model on new event hashtags.
# Never use "water" alone. Figurative uses must not become map evidence.
EVENT_TAG = re.compile(
    r"#\w*(?:flood(?:s|ing)?|earthquake|hurricane|tornado|wildfire)\d*\b", re.IGNORECASE
)
METAPHOR = re.compile(
    r"\bflood(?:ed|ing|s)?\s+(?:(?:my|your|our|the|his|her)\s+)?(?:inbox|timeline|feed|emails|messages|notifications)\b"
    r"|\bflood(?:ed)?\s+(?:of|with)\s+(?:emails|messages|notifications|tears|memories|likes|followers)\b",
    re.IGNORECASE,
)
INCIDENT = re.compile(
    r"\b(?:evacuation (?:shelter|cent(?:er|re)|order)|mandatory evacuation|flood warning|storm surge|(?:road|bridge) (?:is |has been )?washed (?:out|away))\b",
    re.IGNORECASE,
)
ENTERTAINMENT = re.compile(
    r"\b(?:song|album|movie|film)\s+(?:(?:called|named)\s+)?[\"\']?flood[\"\']?(?:\s+by\b|[.!?]|$)",
    re.IGNORECASE,
)


def classify_tweets(df, model=None, *, threshold=0.5):
    """Return every row with new fields and legacy flood/noise label.

    relevance_score is an uncalibrated hybrid score, not factual truth.
    model_score preserves the raw learned score; classification_method records
    any rule override. Explicit incident/tag floors are 0.85, metaphor caps 0.15.
    Category is a rule-based display aid, not severity. needs_review flags
    borderline/low-vocabulary predictions. Custom models implement
    score(text) -> (score, positive_feature_terms, vocabulary_coverage).
    """
    if (
        not isinstance(threshold, (int, float))
        or not math.isfinite(threshold)
        or not 0 < threshold < 1
    ):
        raise ValueError("threshold must be a finite number strictly between 0 and 1.")
    result = prepare_tweets(df)
    engine = model if model is not None else load_model()
    cache, outputs = {}, []
    for text in result["normalized_tweet"]:
        if text not in cache:
            cache[text] = engine.score(text) if text else (0.0, [], 0.0)
        model_score, terms, coverage = cache[text]
        if not math.isfinite(model_score) or not 0 <= model_score <= 1:
            raise ValueError("Classifier returned an invalid relevance score.")
        score = float(model_score)
        method = "text_model"
        raw = re.sub(
            r"https?://\S+|www\.\S+",
            " ",
            result["tweet"].iloc[len(outputs)],
            flags=re.IGNORECASE,
        )
        if EVENT_TAG.search(raw):
            score = max(score, 0.85)
            method = "event_hashtag"
        elif INCIDENT.search(text):
            score = max(score, 0.85)
            method = "incident_phrase"
        elif ENTERTAINMENT.search(text):
            rest = ENTERTAINMENT.sub(" ", text)
            if not re.search(r"\b(flood\w*|evacuat\w*|rescu\w*|river|storm)\b", rest):
                score = min(score, 0.15)
                method = "entertainment_title"
        elif METAPHOR.search(text):
            # Require a separate literal hazard cue before rejecting a metaphor.
            rest = METAPHOR.sub(" ", text)
            if not re.search(
                r"\b(flood\w*|evacuat\w*|rescu\w*|river|storm|hurricane|tornado|earthquake)\b",
                rest,
            ):
                score = min(score, 0.15)
                method = "figurative_language"
        relevant = bool(text) and score >= threshold
        review = bool(text) and (
            abs(score - threshold) < 0.15
            or coverage < 0.15
            or (score >= threshold) != (model_score >= threshold)
        )
        category = "noise"
        if relevant:
            category = next(
                (
                    name
                    for name, pattern in CATEGORY_PATTERNS
                    if re.search(pattern, text)
                ),
                "disaster_report",
            )
        if not text:
            reason = "No usable tweet text."
            method = "empty"
        elif method == "event_hashtag":
            reason = "Explicit disaster hashtag contributes relevance evidence; the report is not verified."
        elif method == "incident_phrase":
            reason = "Explicit disaster response or impact phrase; the report is not verified."
        elif method == "entertainment_title":
            reason = "Flood is an entertainment title without a separate hazard cue."
        elif method == "figurative_language":
            reason = "Figurative flooding of messages or emotions, without a separate literal hazard cue."
        elif relevant:
            reason = "Model predicts disaster-related content."
            if terms:
                reason += " Strongest positive features: " + ", ".join(terms) + "."
        else:
            reason = "Model predicts unrelated content; no disaster claim is verified by this score."
        if review:
            reason += " Review: borderline score, unfamiliar vocabulary, or rule/model disagreement."
        outputs.append(
            (
                "flood" if relevant else "noise",
                "relevant" if relevant else "unrelated",
                relevant,
                float(score),
                category,
                reason,
                review,
                getattr(engine, "version", "custom"),
                float(model_score),
                method,
            )
        )
    columns = [
        "label",
        "relevance",
        "is_relevant",
        "relevance_score",
        "category",
        "reason",
        "needs_review",
        "classifier_version",
        "model_score",
        "classification_method",
    ]
    for i, column in enumerate(columns):
        result[column] = [row[i] for row in outputs]
    for column in ("is_relevant", "needs_review"):
        result[column] = result[column].astype(bool)
    result["relevance_score"] = result["relevance_score"].astype(float)
    result["model_score"] = result["model_score"].astype(float)
    return result
