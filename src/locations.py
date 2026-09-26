"""Location extraction helpers.

This module provides a small, replaceable interface for extracting
place-name mentions from arbitrary text (tweets). The default extractor
is a conservative heuristic but callers can pass their own extractor
(for example a Gemini-based or spaCy-based extractor) without changing
the surrounding pipeline.
"""
import re
from typing import Callable, Iterable, List, Optional
import pandas as pd
from src.geocode import Geocoder, _haversine


# Type for an extractor function: receives a single text and returns
# a list of zero-or-more extracted location strings.
Extractor = Callable[[str], List[str]]

# Supplemental place vocabulary, not coordinates or disaster relevance cues.
# General extraction and contextual geocoding still handle other regions.
NORTHERN_ONTARIO_PLACES = (
    "Fort Frances", "Nipigon", "Thunder Bay", "Atikokan", "Kenora", "Dryden",
    "Red Lake", "Sioux Lookout", "Schreiber", "Terrace Bay", "Geraldton",
    "Longlac", "Hearst", "Kapuskasing", "Cochrane", "Timmins", "Sudbury",
    "North Bay", "Sault Ste. Marie", "Elliot Lake", "Wawa", "Ignace",
    "Manitouwadge", "Temiskaming Shores", "Rainy River", "Marathon", "Emo",
    "Sioux Narrows", "Pickle Lake", "Moosonee", "Moonbeam", "Smooth Rock Falls",
)
_NORTHERN_PLACE_PATTERNS = [
    (name, re.compile(r"(?<!\w)" + r"[\s_-]*".join(re.escape(part) for part in name.split()) + r"(?!\w)", re.IGNORECASE))
    for name in NORTHERN_ONTARIO_PLACES
]


def _default_extractor(text: str) -> List[str]:
    """Basic heuristic extractor that finds capitalized word sequences
    and common prepositional patterns like "in <Place>" or "near <Place>".

    This is intentionally simple and conservative so it can be swapped
    out for a model-based extractor later.
    """
    if not isinstance(text, str) or not text:
        return []

    # Don't turn place names embedded in URLs into map evidence.
    text = re.sub(r"https?://\S+|www\.\S+", " ", text, flags=re.IGNORECASE)
    results = []
    for name, pattern in _NORTHERN_PLACE_PATTERNS:
        for match in pattern.finditer(text):
            # These names also occur as ordinary words; require geographic wording.
            if name in {"Marathon", "Emo", "Moonbeam"} and not (
                text[max(0, match.start() - 1):match.start()] == "#" or
                re.search(r"\b(?:in|near|at|from|to|around)\s+$", text[:match.start()], re.IGNORECASE)
            ):
                continue
            results.append(name)
    # Stop at lowercase prose instead of sending "Nipigon roads are flooded"
    # as a place query. Retain general extraction outside the vocabulary above.
    word = r"[A-Z][A-Za-z0-9&'\-\.]*"
    prep_patterns = [r"\b(?:in|near|at)\s+(" + word + r"(?:\s+" + word + r")*)"]
    for p in prep_patterns:
        for m in re.findall(p, text):
            candidate = m.strip(' .,!;:\n')
            if len(candidate) >= 3:
                results.append(candidate)

    # Capitalized phrase heuristic (e.g., "Thunder Bay", "Lake Superior")
    cap_pattern = re.compile(r"\b([A-Z][a-z0-9]+(?:[\s\-][A-Z][a-z0-9]+)+)\b")
    for m in cap_pattern.findall(text):
        candidate = m.strip(' .,!;:\n')
        if len(candidate) >= 3:
            results.append(candidate)

    # De-duplicate while preserving order
    seen = set()
    uniq = []
    for r in results:
        if r.casefold() not in seen:
            seen.add(r.casefold())
            uniq.append(r)
    return uniq


def extract_locations(text: str | Iterable[str], extractor: Extractor | None = None) -> List[str]:
    """Extract zero-or-more location names.

    This function is backwards-compatible with the older `app.py` call
    pattern which passes a list of tweet strings. It accepts either a
    single text string or an iterable of strings. When given an iterable
    it returns a flat list of mentions found across the inputs. When
    given a single string it behaves like the original function.

    Args:
        text: The input text (single tweet) or an iterable/list of tweets.
        extractor: Optional callable(text)->List[str]. If not provided,
            the bundled heuristic `_default_extractor` is used.

    Returns:
        A list of extracted location name strings (possibly empty).
    """
    fn = extractor or _default_extractor
    try:
        # If caller passed an iterable of tweets (list), run extractor on each
        # and return a flattened list of mentions — this preserves previous
        # app.py behaviour where `extract_locations(samples)` returned a list.
        if isinstance(text, (list, tuple)) or (hasattr(text, '__iter__') and not isinstance(text, str)):
            mentions: List[str] = []
            for t in text:
                try:
                    mentions.extend(fn(str(t)) or [])
                except Exception:
                    continue
            return mentions
        # single-string path
        return fn(str(text)) or []
    except Exception:
        # Ensure failures in a custom extractor don't crash the pipeline
        return []


def batch_extract_locations(df: pd.DataFrame, tweet_col: str = "tweet", tweet_id_col: str = "tweet_id", extractor: Extractor | None = None) -> pd.DataFrame:
    """Batch-extract locations from a DataFrame of tweets.

    Produces one output row per (tweet, location) pair with columns:
    - `tweet` (original text)
    - `location_name` (extracted place name)

    Tweets with no extracted locations are omitted (zero-or-more per tweet).

    Args:
        df: Input DataFrame containing a tweet/text column.
        tweet_col: Name of the column in `df` that contains the tweet text.
        extractor: Optional extractor function passed to `extract_locations`.

    Returns:
        DataFrame with columns `tweet` and `location_name`.
    """
    if tweet_col not in df.columns:
        raise ValueError(f"tweet column '{tweet_col}' not found in DataFrame")

    rows = []
    for _, r in df.iterrows():
        text = r.get(tweet_col, "")
        tid = r.get(tweet_id_col)
        locs = extract_locations(text, extractor=extractor)
        for loc in locs:
            rows.append({"tweet_id": tid, "tweet": text, "mention": loc})

    return pd.DataFrame(rows, columns=["tweet_id", "tweet", "mention"]) if rows else pd.DataFrame(columns=["tweet_id", "tweet", "mention"]) 


def _clean_mention(mention: str) -> str:
    """Clean trailing noise from an extracted mention.

    Removes trailing phrases like 'near the harbour', 'due to water',
    'because of ...', and similar low-value suffixes.
    """
    if not isinstance(mention, str):
        return mention
    m = mention.strip()
    # split on common noise indicators and take the left-most sensible part
    noise_separators = [" near ", " due to ", " because ", " because of ", " due to ", " due to water", " due to flooding", " and worse near ", " near the "]
    for sep in noise_separators:
        if sep in m.lower():
            parts = re.split(re.escape(sep), m, flags=re.IGNORECASE)
            if parts:
                candidate = parts[0].strip(' .,!;:\n')
                if len(candidate) >= 3:
                    m = candidate
    # remove trailing commas/phrases like ', Scotland' only when too specific handled later
    m = re.sub(r"\s*,\s*$", "", m)
    return m


def canonicalize_mentions(df_mentions: pd.DataFrame, geocoder: Optional[Geocoder] = None, prefer_country: Optional[str] = None) -> pd.DataFrame:
    """Resolve mentions to canonical names and coordinates.

    Input: DataFrame with columns `tweet_id`, `tweet`, `mention`.
    Output: DataFrame with columns: tweet_id, mention, canonical_name, latitude, longitude, location_score, status

    Status is one of: 'resolved', 'ambiguous', 'unresolved'. Ambiguous/unresolved rows have null coords.
    """
    if geocoder is None:
        geocoder = Geocoder()

    required_cols = {"tweet_id", "tweet", "mention"}
    if not required_cols.issubset(set(df_mentions.columns)):
        raise ValueError(f"df_mentions must contain columns: {required_cols}")

    # clean mentions
    df = df_mentions.copy()
    df['mention'] = df['mention'].astype(str).apply(_clean_mention)

    # prefetch candidates for unique mentions (try Canada bias first)
    unique = df['mention'].dropna().unique().tolist()
    candidates_map = {}
    for name in unique:
        # If a prefer_country was supplied, bias the lookup to that country.
        # Otherwise perform a global lookup.
        if prefer_country:
            cand_pref = geocoder.geocode_candidates(name, country_codes=prefer_country.lower())
            if cand_pref:
                candidates_map[name] = cand_pref
                continue
        candidates_map[name] = geocoder.geocode_candidates(name, country_codes=None) or []

    # Preselect a top candidate per mention (first candidate) to build context coords
    preselected_coords = {}
    for name, cands in candidates_map.items():
        if cands:
            first = cands[0]
            preselected_coords[name] = (first['lat'], first['lon'])

    out_rows = []
    # Process per tweet to allow context-aware selection. We first order mentions
    # by their candidate strength so high-confidence places (cities, lakes) are
    # resolved first and can act as context for ambiguous mentions.
    for tid, group in df.groupby('tweet_id'):
        tweet_text = group['tweet'].iloc[0] if not group.empty else ''
        # helper: detect a bare/generic street mention (e.g., 'Main St' without city/context)
        def _is_bare_street(name: str) -> bool:
            if not isinstance(name, str):
                return False
            ln = name.lower()
            # treat explicit 'Main St' or 'Main Street' as bare if no city qualifier (' in ' or comma)
            if ('main st' in ln or 'main street' in ln) and (' in ' not in ln) and (',' not in ln):
                return True
            # generic short street-like mentions without city
            if re.search(r"\b(?:street|st|road|rd|avenue|ave)\b", ln) and (' in ' not in ln) and (',' not in ln):
                # but avoid treating long multiword mentions that include locality info
                if len(ln) <= 20:
                    return True
            return False

        # gather context coords from other mentions in same tweet, excluding bare streets
        context_coords = []
        for m in group['mention']:
            for k, v in preselected_coords.items():
                if k != m and not _is_bare_street(k):
                    context_coords.append(v)

        # Build mention -> max_importance to order processing
        mention_rows = []
        for _, row in group.iterrows():
            m = row['mention']
            cands = candidates_map.get(m) or []
            max_imp = max([float(c.get('importance') or 0) for c in cands]) if cands else 0.0
            mention_rows.append({'mention': m, 'tweet': row['tweet'], 'max_imp': max_imp})

        # process in descending max_imp order so strong places become context
        proc_order = sorted(mention_rows, key=lambda x: x['max_imp'], reverse=True)
        resolved_map = {}
        # resolved_context_coords derived from resolved_map entries
        for item in proc_order:
            mention = item['mention']
            cands = candidates_map.get(mention) or []
            is_bare_st = _is_bare_street(mention)

            # don't resolve bare street mentions (conservative)
            if not cands or is_bare_st:
                resolved_map[mention] = {'chosen': None, 'score': 0.0, 'status': 'unresolved', 'lat': None, 'lon': None, 'canonical': None}
                continue

            # build context coords from already resolved mentions (high-confidence)
            resolved_context = []
            for k, v in resolved_map.items():
                if v.get('chosen') and v.get('lat') and v.get('lon'):
                    resolved_context.append((v['lat'], v['lon']))

            chosen = geocoder.choose_candidate(mention, cands, context_coords=resolved_context or None, prefer_country=prefer_country)

            # compute score
            score = 0.0
            if chosen:
                imp = float(chosen.get('importance') or 0)
                spec = float(len(chosen.get('display_name') or '')) / 100.0
                base = imp + spec
                if resolved_context:
                    try:
                        min_dist = min([_haversine(chosen.get('lat'), chosen.get('lon'), c[0], c[1]) for c in resolved_context])
                    except Exception:
                        min_dist = float('inf')
                    if min_dist <= 50:
                        base += 0.2
                    elif min_dist <= 200:
                        base += 0.1
                    elif min_dist > 500:
                        base = max(0.0, base - 0.2)
                score = max(0.0, min(1.0, base))
            # status logic
            if not chosen:
                resolved_map[mention] = {'chosen': None, 'score': 0.0, 'status': 'unresolved', 'lat': None, 'lon': None, 'canonical': None}
            else:
                dn = (chosen.get('display_name') or '').lower()
                lat = chosen.get('lat')
                lon = chosen.get('lon')
                canonical = chosen.get('display_name')
                inconsistent = False
                if resolved_context:
                    min_dist = min(_haversine(lat, lon, c[0], c[1]) for c in resolved_context)
                    if min_dist > 500 and (not prefer_country or prefer_country.lower() not in dn):
                        inconsistent = True
                if inconsistent:
                    resolved_map[mention] = {'chosen': None, 'score': 0.0, 'status': 'ambiguous', 'lat': None, 'lon': None, 'canonical': None}
                else:
                    if len(cands) > 1 and score < 0.6:
                        resolved_map[mention] = {'chosen': chosen, 'score': round(float(score), 3), 'status': 'ambiguous', 'lat': None, 'lon': None, 'canonical': None}
                    else:
                        resolved_map[mention] = {'chosen': chosen, 'score': round(float(score), 3), 'status': 'resolved', 'lat': chosen.get('lat'), 'lon': chosen.get('lon'), 'canonical': chosen.get('display_name')}

        # Emit rows in original group order
        for _, row in group.iterrows():
            mention = row['mention']
            entry = resolved_map.get(mention, {})
            out_rows.append({
                'tweet_id': tid,
                'mention': mention,
                'canonical_name': entry.get('canonical'),
                'latitude': entry.get('lat'),
                'longitude': entry.get('lon'),
                'location_score': entry.get('score', 0.0),
                'status': entry.get('status', 'unresolved'),
            })

    return pd.DataFrame(out_rows, columns=['tweet_id', 'mention', 'canonical_name', 'latitude', 'longitude', 'location_score', 'status'])


__all__ = ["extract_locations", "batch_extract_locations", "canonicalize_mentions", "Extractor"]
