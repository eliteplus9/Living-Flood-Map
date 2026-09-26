# Team Integration Contract

Mutasim's shared repository is the source of truth. Roles are flexible; the current leads are Edward for classification, Mutasim for locations/map, and Mailles for UI/integration/deployment.

## Stable boundary

Shared request and response types live in `shared/contracts.ts`.

Every result must preserve `tweet_id`. Do not join by tweet text because duplicate posts are present. Scores must be numbers from `0` to `1`. A tweet may return more than one location.

## Classification integration

The UI calls `POST /api/classify` with no more than 50 `SourceTweet` records and optional event context. It expects `BatchResponse<Classification>`.

Replace the `classify` implementation in `worker/index.ts`, or call a separate classifier from that route. Keep the route and response shape unchanged.

Required labels are `relevant`, `unrelated`, and `uncertain`. Processing failures remain separately visible as unprocessed records with error details and retry controls. Do not label a network failure as uncertain content.

## Location integration

The UI calls `POST /api/locations` with no more than 50 `SourceTweet` records and expects `BatchResponse<LocationResult>`.

Replace the `locate` implementation in `worker/index.ts`, or call a separate location service from that route. Preserve ambiguous and unresolved mentions; only `resolved` results with coordinates appear on the map.

The current map consumes the shared contract. A replacement map should retain source-tweet evidence and explicit uncertainty.

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
