import pytest
from fastapi.testclient import TestClient

import location_api

TOKEN = "location-test-key-" * 3
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


class FakeGeocoder:
    def geocode_candidates(self, name, country_codes=None):
        if name == "Calgary":
            return [{"display_name": "Calgary, Alberta, Canada", "lat": 51.0447,
                     "lon": -114.0719, "importance": 0.7, "raw": {"class": "place"}}]
        return []

    def choose_candidate(self, name, candidates, context_coords=None, prefer_country=None):
        return candidates[0] if candidates else None


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LOCATION_API_KEY", TOKEN)
    with TestClient(location_api.create_app(geocoder=FakeGeocoder())) as app:
        yield app


def test_location_service_preserves_ids_and_resolves_mentions(client):
    payload = {"tweets": [
        {"tweet_id": "source-1", "tweet": "Flood in Calgary", "source_row": 17},
        {"tweet_id": "source-2", "tweet": "No place mentioned", "source_row": 18},
    ]}
    response = client.post("/locations", headers=HEADERS, json=payload)
    assert response.status_code == 200, response.text
    rows = response.json()["results"]
    assert rows[0]["tweet_id"] == "source-1"
    assert rows[0]["status"] == "resolved"
    assert rows[0]["latitude"] == 51.0447
    assert all(row["tweet_id"] in {"source-1", "source-2"} for row in rows)


def test_auth_and_invalid_batch_are_visible(client):
    payload = {"tweets": [{"tweet_id": "x", "tweet": "Flood in Calgary", "source_row": 1}]}
    assert client.post("/locations", json=payload).status_code == 401
    assert client.post("/locations", headers=HEADERS, json={"tweets": payload["tweets"] * 2}).status_code == 422
    assert client.post("/locations", headers=HEADERS, json={"tweets": [{**payload["tweets"][0], "extra": "private"}]}).status_code == 422


def test_validation_error_does_not_echo_uploaded_text(client):
    secret_text = "Private report text should not appear in errors"
    response = client.post("/locations", headers=HEADERS, json={"tweets": [
        {"tweet_id": "x", "tweet": secret_text, "source_row": "invalid"}]})
    assert response.status_code == 422
    assert secret_text not in response.text


def test_provider_failure_is_not_an_empty_location_result(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise ConnectionError("private provider failure")
    monkeypatch.setattr(location_api, "canonicalize_mentions", unavailable)
    response = client.post("/locations", headers=HEADERS, json={"tweets": [
        {"tweet_id": "x", "tweet": "Flood in Calgary", "source_row": 1}]})
    assert response.status_code == 503
    assert "private provider failure" not in response.text


def test_public_nominatim_is_not_a_production_default(monkeypatch):
    monkeypatch.setenv("LOCATION_API_KEY", TOKEN)
    monkeypatch.delenv("LOCATION_GEOCODER_DOMAIN", raising=False)
    with pytest.raises(RuntimeError, match="LOCATION_GEOCODER_DOMAIN"):
        with TestClient(location_api.create_app()):
            pass
    monkeypatch.setenv("LOCATION_GEOCODER_DOMAIN", "nominatim.openstreetmap.org")
    with pytest.raises(RuntimeError, match="LOCATION_GEOCODER_DOMAIN"):
        with TestClient(location_api.create_app()):
            pass
