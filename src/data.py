"""Validated CSV input and stable row identities shared by every pipeline stage."""

import csv
import hashlib
import html
import io
import re
import unicodedata
from pathlib import Path

import pandas as pd

MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 100_000
MAX_TWEET_CHARS = 20_000
DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data/main_contestant.csv"


class DataValidationError(ValueError):
    """An actionable input error suitable for displaying with st.error()."""


def _hashtag(tag):
    split = re.sub(r"([a-z])([A-Z])", r"\1 \2", tag)
    suffix = re.search(
        r"(flood(?:s|ing)?|earthquake|hurricane|tornado|wildfire|cleanup)\d*$",
        tag,
        re.IGNORECASE,
    )
    return split + (" " + suffix.group(1) if suffix else "")


def normalize_tweet(value):
    """Keep negation and hashtag meaning; remove URLs/handles from model input only."""
    value = unicodedata.normalize("NFKC", html.unescape(value))
    value = re.sub(r"https?://\S+|www\.\S+", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"(?<!\w)@\w+", " ", value)
    value = re.sub(r"\bRT\b\s*:", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\bRT\b", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"#(\w+)", lambda m: _hashtag(m.group(1)), value)
    return re.sub(r"\s+", " ", value).strip().lower()


def prepare_tweets(df):
    """Preserve rows, index and original text. Generated IDs hash original text plus
    duplicate occurrence; source_row is a zero-based data-row position, not line.
    Existing unique IDs are preserved when classifying a filtered frame.
    """
    if not isinstance(df, pd.DataFrame) or "tweet" not in df.columns:
        raise DataValidationError("CSV must contain a 'tweet' column.")
    if not df.columns.is_unique:
        raise DataValidationError("CSV column names must be unique.")
    if len(df) > MAX_ROWS:
        raise DataValidationError(f"CSV must contain at most {MAX_ROWS:,} tweets.")
    result = df.copy(deep=True)
    values = result["tweet"].tolist()
    if any(
        not isinstance(v, str) and (not pd.api.types.is_scalar(v) or not pd.isna(v))
        for v in values
    ):
        raise DataValidationError("Every tweet must be text or blank.")
    values = [v if isinstance(v, str) else "" for v in values]
    if any(len(v) > MAX_TWEET_CHARS for v in values):
        raise DataValidationError(f"A tweet exceeds {MAX_TWEET_CHARS:,} characters.")
    result["tweet"] = values
    if "source_row" not in result:
        result["source_row"] = range(len(result))
    elif (
        result["source_row"].isna().any()
        or result["source_row"].astype(str).str.strip().eq("").any()
        or result["source_row"].duplicated().any()
    ):
        raise DataValidationError(
            "Existing source_row values must be nonblank and unique."
        )
    if "tweet_id" in result:
        ids = result["tweet_id"]
        if (
            ids.isna().any()
            or ids.astype(str).str.strip().eq("").any()
            or ids.astype(str).duplicated().any()
        ):
            raise DataValidationError(
                "Existing tweet_id values must be nonblank and unique."
            )
        result["tweet_id"] = ids.astype(str)
    else:
        occurrences, ids = {}, []
        for value in values:
            digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
            n = occurrences.get(digest, 0)
            occurrences[digest] = n + 1
            ids.append(f"tw_{digest}_{n}")
        result["tweet_id"] = ids
    normalized = [normalize_tweet(v) for v in values]
    result["normalized_tweet"] = normalized
    result["is_empty"] = [not bool(v) for v in normalized]
    first_seen, duplicates = {}, []
    for tid, value in zip(result["tweet_id"], normalized):
        duplicates.append(first_seen.get(value, "") if value else "")
        if value:
            first_seen.setdefault(value, tid)
    result["duplicate_of"] = duplicates
    return result


def read_uploaded_csv(uploaded_file):
    """Read UTF-8/BOM CSV without dropping empty or duplicate rows."""
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    raw = uploaded_file.read(MAX_BYTES + 1)
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise DataValidationError("CSV must be 20 MB or smaller.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataValidationError(
            "Save your CSV with UTF-8 encoding and try again."
        ) from exc
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader, None)
        if not header:
            raise DataValidationError(
                "The uploaded file is empty; upload a CSV with a 'tweet' header."
            )
        header = [h.strip() for h in header]
        if not all(header) or len(header) != len(set(header)):
            raise DataValidationError("CSV headers must be nonblank and unique.")
        if "tweet" not in header:
            raise DataValidationError("CSV must contain a 'tweet' column.")
        rows = []
        for number, row in enumerate(reader, start=1):
            if not row:
                row = [""] * len(header)
            if len(row) != len(header):
                raise DataValidationError(
                    f"CSV data row {number} has {len(row)} fields; expected {len(header)}. Quote commas inside tweets."
                )
            rows.append(row)
            if len(rows) > MAX_ROWS:
                raise DataValidationError(
                    f"CSV must contain at most {MAX_ROWS:,} tweets."
                )
    except csv.Error as exc:
        raise DataValidationError(f"Malformed CSV: {exc}") from exc
    return prepare_tweets(pd.DataFrame(rows, columns=header))


def load_data(path=None):
    path = Path(path) if path is not None else DEFAULT_DATA
    try:
        with path.open("rb") as source:
            return read_uploaded_csv(source)
    except FileNotFoundError as exc:
        raise DataValidationError(
            "Default dataset not found. Upload a CSV or place it at data/main_contestant.csv."
        ) from exc
