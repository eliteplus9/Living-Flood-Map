"""Authenticated location adapter around Mutasim's extraction and resolver.

Production requires a configured Nominatim-compatible provider. The public OSM
Nominatim server is deliberately disallowed for bulk application traffic.
"""

import math
import os
import secrets
from contextlib import asynccontextmanager
from threading import BoundedSemaphore

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from src.geocode import Geocoder
from src.locations import batch_extract_locations, canonicalize_mentions

MAX_BYTES = 2 * 1024 * 1024
MAX_BATCH = 50
VERSION = "mutasim-context-v1"


class LocationTweet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tweet_id: StrictStr = Field(min_length=1, max_length=512)
    tweet: StrictStr = Field(max_length=20_000)
    source_row: int = Field(ge=0, strict=True)


class LocateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tweets: list[LocationTweet] = Field(min_length=1, max_length=MAX_BATCH)
    prefer_country: str | None = Field(default=None, pattern=r"^[A-Za-z]{2}$")


def _configured_geocoder():
    domain = os.environ.get("LOCATION_GEOCODER_DOMAIN", "").strip().lower()
    if not domain or "/" in domain or ":" in domain or domain == "nominatim.openstreetmap.org":
        raise RuntimeError("Set LOCATION_GEOCODER_DOMAIN to an approved private or paid Nominatim-compatible host.")
    return Geocoder(user_agent="living-flood-map-location-service", domain=domain, strict_errors=True)


def create_app(geocoder=None):
    @asynccontextmanager
    async def lifespan(app):
        token = os.environ.get("LOCATION_API_KEY", "")
        if len(token) < 32 or not token.isascii():
            raise RuntimeError("Set LOCATION_API_KEY to an ASCII secret of at least 32 characters.")
        app.state.api_key = token
        app.state.geocoder = geocoder if geocoder is not None else _configured_geocoder()
        app.state.busy = BoundedSemaphore(1)
        yield

    app = FastAPI(title="Living Flood Map Locations", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic includes the rejected input by default; never echo tweet text.
        return JSONResponse(
            status_code=422,
            content={"detail": [
                {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                for error in exc.errors()
            ]},
        )

    @app.middleware("http")
    async def request_guard(request: Request, call_next):
        if request.url.path == "/locations":
            expected = getattr(request.app.state, "api_key", "")
            supplied = request.headers.get("authorization", "")
            if not expected or not secrets.compare_digest(supplied.encode(), f"Bearer {expected}".encode()):
                return JSONResponse({"detail": "Invalid or missing API key."}, status_code=401)
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_BYTES:
                    return JSONResponse({"detail": "Location batch must be 2 MB or smaller."}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "locations", "model_version": VERSION, "max_batch": MAX_BATCH}

    @app.post("/locations")
    def locate(payload: LocateInput, request: Request):
        if not request.app.state.busy.acquire(blocking=False):
            raise HTTPException(503, "Location service busy; retry shortly.", headers={"Retry-After": "1"})
        try:
            ids = [row.tweet_id for row in payload.tweets]
            if len(ids) != len(set(ids)) or any(not value.strip() for value in ids):
                raise HTTPException(422, "Tweet IDs must be nonblank and unique within a batch.")
            frame = pd.DataFrame([row.model_dump() for row in payload.tweets])
            mentions = batch_extract_locations(frame)
            if mentions.empty:
                return {"results": [], "warnings": [], "model_version": VERSION}
            resolved = canonicalize_mentions(
                mentions, geocoder=request.app.state.geocoder,
                prefer_country=payload.prefer_country.upper() if payload.prefer_country else None,
            )
            results = []
            for row in resolved.to_dict(orient="records"):
                status = row["status"]
                score = row["location_score"]
                lat, lon = row["latitude"], row["longitude"]
                if status not in {"resolved", "ambiguous", "unresolved"} or not isinstance(score, (float, int)) or not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("Invalid location resolution result.")
                result = {"tweet_id": str(row["tweet_id"]), "mention": str(row["mention"]),
                          "location_score": float(score), "status": status}
                if status == "resolved":
                    if not isinstance(lat, (float, int)) or not isinstance(lon, (float, int)) or not math.isfinite(lat) or not math.isfinite(lon) or abs(lat) > 90 or abs(lon) > 180:
                        raise ValueError("Invalid resolved coordinates.")
                    result.update({"canonical_name": str(row["canonical_name"]), "latitude": float(lat), "longitude": float(lon)})
                results.append(result)
            return {"results": results, "warnings": [], "model_version": VERSION}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, "Location resolution unavailable. Retry this batch.") from exc
        finally:
            request.app.state.busy.release()

    return app


app = create_app()
