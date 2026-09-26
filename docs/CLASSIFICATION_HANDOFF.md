# Edward's classification component

Ready to integrate: `src/data.py`, `src/classify.py`, `src/text_model.py`, and the bundled `models/relevance.json.gz`.
The existing `classify_tweets(df)` call and `label == "flood"` filter still work. Use Python 3.10 or newer. The model needs no API key, network access, scikit-learn, or model download at runtime. The existing project requirements remain sufficient.

## Use from the app

```python
from src.data import read_uploaded_csv, load_data, DataValidationError
from src.classify import classify_tweets

try:
    frame = read_uploaded_csv(uploaded_file) if uploaded_file is not None else load_data()
    classified = classify_tweets(frame)
except (DataValidationError, RuntimeError) as exc:
    st.error(str(exc))
    st.stop()

relevant = classified.loc[classified.is_relevant].copy()
# Pass relevant tweets WITH tweet_id to location extraction.
# Retain classified in session_state for filters, summaries and downloads.
records = classified.to_dict(orient="records")
```

The UI owner should add this error handling and persist the returned DataFrame. The existing app is still a scaffold: location extraction currently reads the raw input, not classification results. This PR does not change the map or shared app.py. A working classifier alone does not complete the app pipeline.

## Integration contract

| Field | Type | Meaning |
|---|---|---|
| tweet_id | string | Unique per row in this upload; preserve when filtering and joining |
| source_row | integer by default | Zero-based input data row, not a physical line number |
| tweet | string | Original text; blank/null becomes empty string |
| normalized_tweet | string | Model input; URLs/handles removed, negation retained |
| relevance | string | `relevant` or `unrelated` |
| is_relevant | boolean | Equivalent boolean for filtering |
| relevance_score | float 0–1 | Hybrid relevance estimate; not calibrated confidence or factual verification |
| model_score | float 0–1 | Raw trained model output before rule adjustments |
| label | string | Legacy alias: `flood` / `noise`; `flood` means disaster-related, not confirmed inundation |
| category | string | Rule-based display category, not a trained severity label |
| reason | string | Model feature explanation or the rule used |
| needs_review | boolean | Borderline score, unfamiliar vocabulary, or rule/model disagreement |
| classification_method | string | `text_model`, `event_hashtag`, `incident_phrase`, `figurative_language`, `entertainment_title`, `empty` |
| classifier_version | string | Version of the learned weights |
| duplicate_of | string | First equivalent normalized row ID in this batch, or empty |
| is_empty | boolean | No usable normalized text |

Categories: `evacuation_rescue`, `infrastructure`, `relief_recovery`, `solidarity`, `disaster_report`, `noise`. These describe broad relevance; a prayer or denial of flooding must not be presented as confirmed physical damage. Categories do not establish that a tweet is firsthand, current, true, or about the selected event.

Generated IDs hash original text plus the occurrence number for exact duplicate text. IDs are deterministic for an unchanged upload. Preserve them through every pipeline stage. Different uploads need separate dataset scopes if stored together. Existing nonblank unique `tweet_id` and `source_row` values are preserved; invalid ones cause a validation error. Duplicate rows remain present, but normalized duplicates are scored once per call. `duplicate_of` is batch-local and recalculated for filtered frames.

## Input handling

- Required header: `tweet`; UTF-8 and UTF-8 BOM supported. Header whitespace is trimmed.
- Quoted commas/newlines, blank tweets, and literal `NA` text are preserved.
- Empty files, missing/duplicate headers, malformed row widths, invalid encoding/IDs and excessive input produce `DataValidationError`.
- Header-only CSV returns an empty frame with the full result schema.
- Limits: 20 MB, 100,000 rows, 20,000 characters per tweet. No silent truncation.
- Additional input columns remain intact; derived output columns are recomputed.

## Classification design

A word/unigram–bigram TF-IDF logistic model was trained on five CrisisLexT6 events. The entire Alberta event was excluded, and exact normalized matches with the supplied CSV were also screened out. Training used 35,100 deduplicated rows, with 8,775 separate rows retained for evaluation. Final weights do not refit the test split. Weights are portable gzip JSON, not executable pickle.

Explicit disaster hashtags and certain incident phrases set a score floor of 0.85. Clear figurative flooding or entertainment-title contexts can cap the score at 0.15, unless separate hazard cues remain. The default threshold is 0.5; scores within 0.15 of the chosen threshold, vocabulary coverage below 0.15, and rule/model disagreements are flagged. Rules and model scores are exposed separately. These scores are not calibrated probabilities.

The model recognizes generic English disaster-related content. It does not resolve which event a report belongs to, distinguish historical reports, verify assertions, infer coordinates, or reliably interpret all irony, negation, languages, or indirect reports. A separate held-out-event stress test shows substantially weaker recall than the within-source test. Keep review and uncertainty visible.

## Validation and reproducibility

`models/model_card.json` records source URLs, pinned revision, checksums, training counts, held-out metrics and a cross-event stress test. `docs/evaluation.json` records local timing and the supplied sample results. The 60 supplied-row labels were reviewed by Codex, not independently by a human; that sample subsequently informed development, so it is a sanity check, not an unbiased accuracy benchmark. The original keyword baseline is reported alongside the new model, including where the old baseline does better.

```sh
python -m pytest -q
python -m scripts.evaluate_classifier
python -m scripts.classify_csv data/main_contestant.csv data/new-results.json
```

Only retraining needs scikit-learn (`pip install scikit-learn`):

```sh
python -m scripts.train_classifier
```

Training downloads only the five named public events into ignored `data/training/`. The supplied dataset must be placed at `data/main_contestant.csv` to perform overlap exclusion. No supplied-event answer labels are downloaded. Raw datasets and classified outputs remain ignored by Git.

Source: [CrisisLexT6](https://crisislex.org/data-collections.html), Olteanu, Castillo, Diaz and Vieweg (2014), *CrisisLex: A Lexicon for Collecting and Filtering Microblogged Communications in Crises*, ICWSM. The source repository's MIT notice is retained in `models/CRISISLEX_LICENSE.txt`.
