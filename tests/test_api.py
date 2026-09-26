import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api
from src.classify import classify_tweets

TOKEN = "test-secret-" * 4
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CLASSIFIER_API_KEY", TOKEN)
    with TestClient(api.create_app()) as client:
        yield client


def test_health_and_auth(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.post("/classify", json={"tweets": []}).status_code == 401
    assert (
        client.post(
            "/classify", headers={"Authorization": "Bearer wrong"}, json={"tweets": []}
        ).status_code
        == 401
    )


def test_startup_requires_secret(monkeypatch):
    monkeypatch.delenv("CLASSIFIER_API_KEY", raising=False)
    with (
        pytest.raises(RuntimeError, match="CLASSIFIER_API_KEY"),
        TestClient(api.create_app()),
    ):
        pass


def test_output_matches_python_and_preserves_ids(client):
    rows = [
        {"tweet_id": "001", "tweet": "Bridge washed away. #YYCFlood", "source_row": 17},
        {
            "tweet_id": "front-😀",
            "tweet": "Bridge washed away. #YYCFlood",
            "source_row": 28,
        },
        {"tweet_id": "empty", "tweet": "", "source_row": 43},
    ]
    response = client.post("/classify", headers=HEADERS, json={"tweets": rows})
    assert response.status_code == 200
    result = response.json()
    assert result["results"] == classify_tweets(pd.DataFrame(rows)).to_dict(
        orient="records"
    )
    assert result["results"][1]["duplicate_of"] == "001"
    assert result["count"] == 3
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "rows",
    [
        [{"tweet_id": "x", "tweet": "one"}, {"tweet_id": "x", "tweet": "two"}],
        [{"tweet_id": "  ", "tweet": "one"}],
        [{"tweet_id": 123, "tweet": "one"}],
        [{"tweet_id": "x", "tweet": None}],
        [
            {"tweet_id": "x", "tweet": "one", "source_row": 0},
            {"tweet_id": "y", "tweet": "two"},
        ],
        [
            {"tweet_id": "x", "tweet": "one", "source_row": 0},
            {"tweet_id": "y", "tweet": "two", "source_row": 0},
        ],
    ],
)
def test_bad_rows(client, rows):
    assert (
        client.post("/classify", headers=HEADERS, json={"tweets": rows}).status_code
        == 422
    )


@pytest.mark.parametrize("threshold", [0, 1, -0.2, "0.5", True])
def test_invalid_threshold(client, threshold):
    assert (
        client.post(
            "/classify", headers=HEADERS, json={"tweets": [], "threshold": threshold}
        ).status_code
        == 422
    )


def test_empty_and_threshold(client):
    assert (
        client.post("/classify", headers=HEADERS, json={"tweets": []}).json()["results"]
        == []
    )
    rows = [{"tweet_id": "a", "tweet": "flood warning"}]
    response = client.post(
        "/classify", headers=HEADERS, json={"tweets": rows, "threshold": 0.9}
    )
    assert response.json()["results"] == classify_tweets(
        pd.DataFrame(rows), threshold=0.9
    ).to_dict(orient="records")


def test_limits_and_no_input_reflection(client, monkeypatch):
    monkeypatch.setattr(api, "MAX_BYTES", 100)
    response = client.post("/classify", headers=HEADERS, content=b"x" * 101)
    assert response.status_code == 413
    response = client.post(
        "/classify",
        headers=HEADERS,
        json={"tweets": [{"tweet_id": 1, "tweet": "private text"}]},
    )
    assert response.status_code == 422
    assert "private text" not in response.text


def test_row_limit(client):
    rows = [{"tweet_id": str(i), "tweet": "a"} for i in range(api.MAX_BATCH + 1)]
    assert (
        client.post("/classify", headers=HEADERS, json={"tweets": rows}).status_code
        == 422
    )


def test_busy_retry(client):
    api.busy.acquire()
    try:
        response = client.post("/classify", headers=HEADERS, json={"tweets": []})
        assert response.status_code == 503
        assert response.headers["retry-after"] == "1"
    finally:
        api.busy.release()
