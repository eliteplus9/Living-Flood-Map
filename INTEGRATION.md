# Team Integration Contract

Mutasim's shared repository is the source of truth. Roles are flexible; the current leads are Edward for classification, Mutasim for locations/map, and Mailles for UI/integration/deployment.

This integration branch merges the latest classifier and location PR heads
into the tested Cloudflare UI. It is not deployed. Edward's separate
map/3D experiment is intentionally not merged; only its safe coordinate-grouping
idea was adapted into the existing map.

## Stable boundary

Shared request and response types live in `shared/contracts.ts`.

Every result must preserve `tweet_id`. Do not join by tweet text because duplicate posts are present. Scores must be numbers from `0` to `1`. A tweet may return more than one location.

## Classification integration

The UI calls `POST /api/classify` in batches of 400 `SourceTweet` records; the Worker accepts up to 500. It expects `BatchResponse<Classification>`.

When both `CLASSIFIER_URL` and `CLASSIFIER_API_KEY` are set, the Worker calls Edward's hosted API and validates IDs, original tweet text, row numbers, and response fields before adapting results. With neither setting, it uses the labelled local preview. Partial configuration and upstream failures are visible errors, never silent preview fallbacks. Keep the key in a Worker secret or local git-ignored `.dev.vars` file.

Required labels are `relevant`, `unrelated`, and `uncertain`. Edward's current API emits relevant/unrelated plus a separate `needs_review` flag. Its relevance score is uncalibrated and is not verification or severity. Processing failures remain separately visible as unprocessed records with error details and retry controls.

## Location integration

The UI calls `POST /api/locations` with no more than 50 `SourceTweet` records and expects `BatchResponse<LocationResult>`.

When both `LOCATION_URL` and `LOCATION_API_KEY` are set, the Worker calls the separate `location_api.py` adapter, which uses Mutasim's extraction and contextual resolver. It validates IDs, scores, statuses, and coordinates. With neither setting, the UI uses its labelled, limited Alberta preview. Partial configuration and upstream failures are visible errors, not zero-location results. An optional two-letter country code controls country preference; leaving it blank allows worldwide lookup.

The location API requires `LOCATION_GEOCODER_DOMAIN` to name an approved private or paid Nominatim-compatible provider and `LOCATION_API_KEY` to authenticate calls. It refuses to start without them or with the public OSM Nominatim hostname. Install `requirements-location-api.txt` and run `uvicorn location_api:app --host 127.0.0.1 --port 8081`. No approved provider or hosted location endpoint has been configured yet. Do not put the public Nominatim server behind an upload endpoint: its [usage policy](https://operations.osmfoundation.org/policies/nominatim/) limits throughput and discourages bulk geocoding. For the supplied 8,024-row dataset, provider capacity and cache strategy must be decided before enabling this path.

The current map consumes the shared contract. A replacement map should retain source-tweet evidence and explicit uncertainty.

The browser sends report text only to its own Worker. In service mode the Worker forwards the necessary original text to the configured classifier and/or location service. Disclose those processors before accepting sensitive uploads, and put access/rate controls on both public Worker routes before deployment. Paid Cloudflare account selection, secrets, and deployment remain pending.

## Summary integration

The UI currently computes its overview from every report matching the shared filters. It does not call a model or silently sample the dataset. The optional `POST /api/summarize` endpoint accepts up to 200 reports for future integration; a model-backed replacement must disclose sampling and return evidence IDs and a model version.

## Merge checklist

The supplemental interpretation adapter is in `shared/interpretation.ts`.
It does not modify the classifier/location response contracts. Review notes
and disputed locations are separate from original automated outputs. Only the
investigation map applies the dispute exclusion; other views show the original
results. Briefing exports disclose these differences and preserve source IDs.

1. Rebase or merge the latest shared branch.
2. Do not change shared types without notifying the team.
3. Run `npm run verify`.
4. Run `npx wrangler deploy --dry-run`.
5. Test the supplied dataset and a small custom CSV.
6. Verify partial-failure and empty-result behavior.

If integration or deployment becomes unstable, pause feature work and restore the end-to-end path first.
