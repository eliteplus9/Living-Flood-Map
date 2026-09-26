import type { AnalysisContext, BatchResponse, Classification, LocationResult, SourceTweet } from "../../shared/contracts";

class HttpError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export async function processBatches<T extends { tweet_id: string }>(
  tweets: SourceTweet[], path: string, context: AnalysisContext,
  onBatch: (rows: SourceTweet[], results: T[], error?: string) => void,
  onProgress: (done: number, total: number) => void,
  signal: AbortSignal,
): Promise<void> {
  const batchSize = path.endsWith("/classify") ? 400 : 40;
  for (let start = 0; start < tweets.length; start += batchSize) {
    signal.throwIfAborted();
    const batch = tweets.slice(start, start + batchSize);
    let failure = "";
    let output: T[] = [];
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const response = await fetch(path, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ tweets: batch, context }),
          signal: AbortSignal.any([signal, AbortSignal.timeout(95_000)]),
        });
        if (!response.ok) {
          const detail = await response.json().catch(() => null) as { error?: string } | null;
          throw new HttpError(detail?.error ?? `Request failed (${response.status}).`, response.status);
        }
        const body = await response.json() as BatchResponse<T>;
        const ids = new Set(batch.map(row => row.tweet_id));
        if (!Array.isArray(body.results) || body.results.some(row => !row || !ids.has(row.tweet_id))) {
          throw new HttpError("Service returned invalid report IDs.", 422);
        }
        if (path.endsWith("/classify")) {
          const rows = body.results as unknown as Classification[];
          if (new Set(rows.map(row => row.tweet_id)).size !== batch.length || rows.length !== batch.length ||
            rows.some(row => !["relevant", "unrelated", "uncertain"].includes(row.relevance) ||
              !Number.isFinite(row.relevance_score) || row.relevance_score < 0 || row.relevance_score > 1)) {
            throw new HttpError("Classification response is incomplete or invalid.", 422);
          }
        } else {
          const rows = body.results as unknown as LocationResult[];
          if (rows.some(row => !["resolved", "ambiguous", "unresolved"].includes(row.status) ||
            typeof row.mention !== "string" || !Number.isFinite(row.location_score) ||
            (row.status === "resolved" && (!Number.isFinite(row.latitude) || !Number.isFinite(row.longitude) ||
              Math.abs(row.latitude!) > 90 || Math.abs(row.longitude!) > 180)))) {
            throw new HttpError("Location response contains invalid coordinates.", 422);
          }
        }
        output = body.results; failure = ""; break;
      } catch (error) {
        signal.throwIfAborted();
        failure = error instanceof Error ? error.message : String(error);
        if (error instanceof HttpError && error.status < 500 && error.status !== 429) break;
        if (attempt < 2) await new Promise(resolve => setTimeout(resolve, 1000 * 2 ** attempt));
      }
    }
    signal.throwIfAborted();
    onBatch(batch, output, failure || undefined);
    onProgress(Math.min(start + batch.length, tweets.length), tweets.length);
  }
}
