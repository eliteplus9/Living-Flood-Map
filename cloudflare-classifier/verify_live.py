"""Compare deployed batches to original Python predictions without logging text."""
import json
import subprocess
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.classify import classify_tweets

frame = pd.read_csv(ROOT / "frontend/public/data/main_contestant.csv", keep_default_na=False)
rows = [{"tweet_id": f"parity-{i}", "source_row": i + 1,
         "tweet": text, "normalized_tweet": text} for i, text in enumerate(frame["tweet"])]
expected = {row["tweet_id"]: row for row in classify_tweets(pd.DataFrame(rows)).to_dict(orient="records")}
fields = ("tweet_id", "relevance", "category", "reason", "needs_review", "classification_method")
checked = 0
for start in range(0, len(rows), 400):
    batch = rows[start:start + 400]
    response = subprocess.run([
        "curl.exe", "--fail-with-body", "-sS", "--max-time", "90",
        "-H", "Content-Type: application/json", "--data-binary", "@-",
        "https://living-flood-map.eliteplus9.workers.dev/api/classify",
    ], input=json.dumps({"tweets": batch}), text=True, capture_output=True, check=True)
    actual = json.loads(response.stdout)["results"]
    assert len(actual) == len(batch)
    assert {row["tweet_id"] for row in actual} == {row["tweet_id"] for row in batch}
    for row in actual:
        original = expected[row["tweet_id"]]
        assert all(row[field] == original[field] for field in fields), row["tweet_id"]
        assert abs(row["relevance_score"] - original["relevance_score"]) < 1e-12, row["tweet_id"]
    checked += len(actual)
print(f"PASS: {checked} deployed predictions match original classifier fields and scores.")
