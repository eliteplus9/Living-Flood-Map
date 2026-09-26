# Classifier API handoff

Status: deployed and verified on Google Cloud Run.

Base URL: https://living-flood-classifier-886360014271.us-central1.run.app

Interactive API docs: https://living-flood-classifier-886360014271.us-central1.run.app/docs

React → existing Cloudflare Worker → Python `/classify` → JSON results.
The API runs the same classifier and model as the CLI. No LLM, external inference
service, training dependencies, database, or tweet storage is required.

## Request

`POST /classify`, `Content-Type: application/json`,
`Authorization: Bearer <CLASSIFIER_API_KEY>`.

```json
{
  "tweets": [
    {"tweet_id": "frontend-001", "tweet": "Bridge washed away. #YYCFlood"}
  ],
  "threshold": 0.5
}
```

`tweet_id` and `tweet` are required strings. IDs must be nonblank and unique per
request; they are returned exactly as supplied. Empty tweet strings are retained.
Optional `source_row` must be a unique nonnegative integer on every row if used;
otherwise zero-based positions are generated within the request. Extra input fields
are rejected: retain UI metadata in the frontend and join results by `tweet_id`.

The response is `{results: [...], count, relevant_count, review_count, threshold,
classifier_version}`. Each result retains `tweet_id`, `tweet`, `source_row` and adds
`label`, `relevance`, `is_relevant`, `relevance_score`, `category`, `needs_review`,
`reason`, `model_score`, `classification_method`, `classifier_version`,
`normalized_tweet`, `is_empty`, and `duplicate_of`.

Relevance is NOT verification or severity. Never silently drop a failed batch or
interpret an API error as “no relevant tweets.” Show a retryable error instead.

Limits: 10,000 rows / 20 MiB JSON body / 20,000 characters per tweet. For larger
uploads send sequential batches; keep frontend IDs/source_row across batches.
`duplicate_of` is batch-local. HTTP 401 = invalid key; 413 = oversized body;
422 = invalid input; 503 = busy, retry after one second. Do not retry 401/413/422.

## Cloudflare integration

Set `CLASSIFIER_URL` to the hosted base URL and `CLASSIFIER_API_KEY` as a Worker
secret. Keep the key out of React, browser requests, source control, and chat.
Use the dashboard's Worker Settings → Variables and Secrets. Call from an existing
Worker route after its normal upload validation and access/rate controls.

```js
// Inside Mailles's existing async Worker handler.
// payload contains only {tweets: [{tweet_id, tweet, source_row?}], threshold?}.
try {
  const upstream = await fetch(new URL('/classify', env.CLASSIFIER_URL), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${env.CLASSIFIER_API_KEY}`,
    },
    body: JSON.stringify(payload),
    redirect: 'error',
    signal: AbortSignal.timeout(90000),
  });
  const status = upstream.status === 401 ? 502 : upstream.status;
  return new Response(upstream.body, {
    status,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store',
      ...(upstream.headers.has('Retry-After')
        ? {'Retry-After': upstream.headers.get('Retry-After')}
        : {}),
    },
  });
} catch {
  return Response.json(
    {detail: 'Classification unavailable. Please retry.'},
    {status: 502, headers: {'Cache-Control': 'no-store'}},
  );
}
```

The response streams through the Worker. The example is not a replacement for
Mailles's router. Preserve his existing authentication and response handling.
CORS is unnecessary between the Worker and Python API; React calls its own Worker.
Official references: [fetch](https://developers.cloudflare.com/workers/runtime-apis/fetch/),
[secrets](https://developers.cloudflare.com/workers/configuration/secrets/).

## Run locally

Install `requirements-api.txt` in a Python 3.12 environment. Set a random ASCII
`CLASSIFIER_API_KEY` of at least 32 characters, then:

```sh
uvicorn api:app --host 127.0.0.1 --port 8080 --workers 1 --no-access-log
```

`GET /health` is public and checks readiness; `/docs` provides interactive schema.
Startup fails if the key or model is missing. `docs/classifier-openapi.json`
is the exported request contract. The server does not log or persist tweet bodies.

## Deployment

`Dockerfile.classifier` includes only the API, src modules, and bundled model.
It runs as a non-root user, respects `PORT`, and has pinned API dependencies.
Build using `docker build -f Dockerfile.classifier -t flood-classifier .`.
Run one worker with at least 512 MiB memory; use 1 GiB for extra headroom at limits.

`render.yaml` is an optional free Render Blueprint for this branch with a generated
secret, `/health` readiness check, and automatic deployment off. Free Render
services sleep after 15 minutes idle, so the first request can be slow. Check
readiness before the demo. [Render limitations](https://render.com/docs/free).
The active deployment uses Cloud Run in `us-central1`, project `agent-s-12345`,
service `living-flood-classifier`, revision `living-flood-classifier-00001-wtf`.
It has 1 CPU, 1 GiB RAM, concurrency 1, minimum 0 / maximum 1 instance, and a
120-second timeout. Scale-to-zero can add cold-start latency. The runtime service
account only has access to its API-key secret. The key lives in Google Secret
Manager as `flood-classifier-api-key` version 1 and is not included in the repo.
The image was built successfully by Google Cloud Build using Dockerfile.classifier
(copied to Dockerfile in a minimal staging directory containing API source/model only).
Deployment contains API code from commit `8bda891`.

## Validation

49 tests pass, including authentication, rejected malformed inputs, strict ID
preservation, empty input, duplicate IDs, limits, concurrency retry, and exact
classifier parity. The supplied 8,024-row dataset returned 4,221 relevant and 456
review rows in about 0.34 seconds through the local HTTP test client, identical to
the Python output. This is local performance, not a hosted latency claim.

Live verification: `/health` returned 200, requests without a key returned 401,
and all 8,024 supplied tweets returned matching IDs, text, labels, categories, and
review flags in 2.84 seconds end-to-end on a warm request. Scores differed by at
most 1.12e-16 across platforms (floating-point rounding). This is a single observed
request, not a latency guarantee.
