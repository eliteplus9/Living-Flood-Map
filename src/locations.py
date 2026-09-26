"""Location extraction helpers.

This module provides a minimal, dependency-light interface to extract
location mentions from free text. Replace or extend with an NLP model
or gazetteer when ready.
"""
import re
from typing import List


def extract_locations(texts: List[str]) -> List[str]:
    """Extract probable location mentions from a list of texts.

    This is a simple heuristic extractor (capitalized word sequences).

    Args:
        texts: List of text strings.

    Returns:
        A list of location strings (may contain duplicates).
    """
    locations = []
    pattern = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")
    for t in texts:
        if not isinstance(t, str):
            continue
        matches = pattern.findall(t)
        for m in matches:
            # crude filter: skip short words that are unlikely locations
            if len(m) >= 3:
                locations.append(m)
    return locations
