"""Authenticated, stateless HTTP adapter for the existing Python classifier."""

import os
import secrets
from contextlib import asynccontextmanager
from threading import BoundedSemaphore
from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from src.classify import classify_tweets
from src.data import MAX_BYTES, MAX_TWEET_CHARS, DataValidationError
from src.text_model import load_model

MAX_BATCH = 10_000
busy = BoundedSemaphore(1)
bearer = HTTPBearer(auto_error=False)


class TweetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tweet_id: Annotated[StrictStr, Field(min_length=1, max_length=512)]
    tweet: Annotated[StrictStr, Field(max_length=MAX_TWEET_CHARS)]
    source_row: Annotated[int, Field(strict=True, ge=0)] | None = None

    @field_validator("tweet_id")
    @classmethod
    def nonblank_id(cls, value):
        if not value.strip():
            raise ValueError("tweet_id must not be blank")
        return value


class ClassifyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tweets: Annotated[list[TweetInput], Field(max_length=MAX_BATCH)]
    threshold: Annotated[float, Field(gt=0, lt=1, allow_inf_nan=False, strict=True)] = (
        0.5
    )


def create_app():
    @asynccontextmanager
    async def lifespan(app):
        token = os.environ.get("CLASSIFIER_API_KEY", "")
        if len(token) < 32 or not token.isascii():
            raise RuntimeError(
                "Set CLASSIFIER_API_KEY to an ASCII secret of at least 32 characters."
            )
        app.state.api_key = token
        load_model()  # Fail readiness immediately if the bundled model is missing.
        yield

    app = FastAPI(
        title="Living Flood Map Classifier", version="1.0.0", lifespan=lifespan
    )

    @app.middleware("http")
    async def request_guard(request: Request, call_next):
        # Authenticate before buffering/parsing potentially large request bodies.
        if request.url.path == "/classify":
            expected = getattr(request.app.state, "api_key", "")
            supplied = request.headers.get("authorization", "")
            if not expected or not secrets.compare_digest(
                supplied.encode(), f"Bearer {expected}".encode()
            ):
                return JSONResponse(
                    {"detail": "Invalid or missing API key."}, status_code=401
                )
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_BYTES:
                    return JSONResponse(
                        {"detail": "Request must be 20 MB or smaller."}, status_code=413
                    )
                chunks.append(chunk)
            # Starlette's cached request body is forwarded to the route by call_next.
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    def authenticate(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        if credentials is None or not secrets.compare_digest(
            credentials.credentials.encode(), request.app.state.api_key.encode()
        ):
            raise HTTPException(401, "Invalid or missing API key.")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not reflect tweet contents or entire input payloads in errors.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                    for e in exc.errors()
                ]
            },
        )

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "classifier_version": load_model().version,
            "max_batch": MAX_BATCH,
        }

    @app.post("/classify", dependencies=[Depends(authenticate)])
    def classify(payload: ClassifyInput):
        if not busy.acquire(blocking=False):
            raise HTTPException(
                503, "Classifier busy; retry shortly.", headers={"Retry-After": "1"}
            )
        try:
            rows = [row.model_dump(exclude_none=True) for row in payload.tweets]
            supplied_rows = ["source_row" in row for row in rows]
            if any(supplied_rows) and not all(supplied_rows):
                raise HTTPException(
                    422,
                    "Provide source_row for every tweet or omit it for every tweet.",
                )
            frame = (
                pd.DataFrame(rows)
                if rows
                else pd.DataFrame(columns=["tweet_id", "tweet"])
            )
            try:
                output = classify_tweets(frame, threshold=payload.threshold)
            except DataValidationError as exc:
                raise HTTPException(422, str(exc)) from exc
            return {
                "results": output.to_dict(orient="records"),
                "count": len(output),
                "relevant_count": int(output["is_relevant"].sum()),
                "review_count": int(output["needs_review"].sum()),
                "threshold": payload.threshold,
                "classifier_version": load_model().version,
            }
        finally:
            busy.release()

    return app


app = create_app()
