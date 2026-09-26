"""Tweet classification utilities.

These functions are intentionally simple placeholders so the rest of the
app can be scaffolded. Replace with a model-based classifier later.
"""
from typing import Optional
import pandas as pd


def classify_tweets(df: pd.DataFrame, model: Optional[object] = None) -> pd.DataFrame:
    """Label tweets as 'flood' or 'noise' using a lightweight heuristic.

    Args:
        df: DataFrame containing a `tweet` text column.
        model: Placeholder argument where a real model instance could be passed.

    Returns:
        DataFrame with an added `label` column.
    """
    tweets = df.copy()
    def _label(text: str) -> str:
        if not isinstance(text, str):
            return "noise"
        low = text.lower()
        keywords = ["flood", "flooding", "inundation", "water", "evacuat"]
        for k in keywords:
            if k in low:
                return "flood"
        return "noise"

    tweets["label"] = tweets.get("tweet", "").apply(_label)
    return tweets
