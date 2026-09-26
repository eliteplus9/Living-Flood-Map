# Private classifier Worker

Uses the original classifier and bundled model, copied by `prepare.ps1` rather
than maintained as a fork. The Python runtime lock uses pandas 3.0.2; the local
parity probe matched the original pandas 2.2.3 output for blank, duplicated,
literal hazard, unrelated and figurative inputs.

Run `./prepare.ps1`, then `uvx --from workers-py pywrangler deploy` from this
directory. `workers_dev` and preview URLs are disabled. Only a Cloudflare service
binding should invoke this Worker; it deliberately has no public API key.

POST `/classify` accepts up to 500 rows, each containing only `tweet_id`, `tweet`
and `source_row`. GET `/health` loads the model. No tweet storage is configured.

The eliteplus9 app is connected using its `CLASSIFIER` service binding. Public
API routes have a 120 requests/minute per-IP limiter, not user authentication or
a global classifier spending cap. Locations use Mutasim's resolver with
prefetched LocationIQ candidates through `GEOCODER_SERVICE`. The private gateway
is configured by `wrangler.geocoder.jsonc` in the repo root. Its provider key is
a separate Worker secret. Run `prepare.ps1` before packaging source updates.

Live validation: `verify_live.py` checked all 8,024 supplied rows through the
deployed app in 400-row batches. IDs, labels, categories, reasons, review flags
and rule provenance matched the original classifier; score differences were
below 1e-12. This verifies implementation parity, not model accuracy.
