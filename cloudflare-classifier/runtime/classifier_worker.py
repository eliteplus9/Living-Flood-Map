"""Private classifier. Only account-local service bindings can invoke it."""
import json
from workers import WorkerEntrypoint, Response
from src.classify import classify_tweets
from src.text_model import load_model
import pandas as pd


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        from urllib.parse import urlparse
        path = urlparse(request.url).path
        if path == "/health":
            return Response.json({"ok": True, "classifier_version": load_model().version})
        if path != "/classify" or request.method != "POST":
            return Response.json({"error": "Route not found."}, status=404)
        try:
            text = await request.text()
            if len(text.encode("utf-8")) > 2 * 1024 * 1024:
                return Response.json({"error": "Batch exceeds 2 MB."}, status=413)
            payload = json.loads(text)
            rows = payload.get("tweets") if isinstance(payload, dict) else None
            if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
                raise ValueError()
            ids, source_rows = set(), set()
            for row in rows:
                if (not isinstance(row, dict) or set(row) != {"tweet_id", "tweet", "source_row"}
                    or not isinstance(row["tweet_id"], str) or not row["tweet_id"].strip()
                    or len(row["tweet_id"]) > 512 or row["tweet_id"] in ids
                    or not isinstance(row["tweet"], str) or len(row["tweet"]) > 20000
                    or type(row["source_row"]) is not int or row["source_row"] < 0
                    or row["source_row"] in source_rows):
                    raise ValueError()
                ids.add(row["tweet_id"])
                source_rows.add(row["source_row"])
        except (ValueError, TypeError, KeyError):
            return Response.json({"error": "Invalid batch IDs, source rows or text."}, status=422)
        try:
            result = classify_tweets(pd.DataFrame(rows))
            # pandas JSON conversion handles numpy scalars and null duplicate IDs.
            return Response.json({"results": json.loads(result.to_json(orient="records", double_precision=15)),
                                  "classifier_version": load_model().version},
                                 headers={"Cache-Control": "no-store"})
        except Exception:
            return Response.json({"error": "Classifier unavailable."}, status=503)
