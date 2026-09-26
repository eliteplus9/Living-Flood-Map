import type { BatchResponse, Classification, SourceTweet } from "../shared/contracts";

export interface ClassifierConfig {
  CLASSIFIER_URL?: string;
  CLASSIFIER_API_KEY?: string;
}

type UpstreamRow = {
  tweet_id?: unknown;
  tweet?: unknown;
  source_row?: unknown;
  relevance?: unknown;
  relevance_score?: unknown;
  category?: unknown;
  reason?: unknown;
  needs_review?: unknown;
  classification_method?: unknown;
  classifier_version?: unknown;
};

export class ClassifierError extends Error {
  constructor(message: string, readonly status = 502, readonly retryAfter?: string) { super(message); }
}

export async function classifyWithService(
  tweets: SourceTweet[], config: ClassifierConfig, fetcher: typeof fetch = fetch,
): Promise<BatchResponse<Classification>> {
  if (!config.CLASSIFIER_URL || !config.CLASSIFIER_API_KEY) {
    throw new ClassifierError("The classifier service is not configured. Add its URL and Worker secret, then retry.", 503);
  }
  let endpoint: URL;
  try {
    endpoint = new URL("/classify", config.CLASSIFIER_URL);
    if (endpoint.protocol !== "https:") throw new Error("HTTPS required");
  } catch {
    throw new ClassifierError("The classifier service URL is invalid.", 503);
  }
  let upstream: Response;
  try {
    upstream = await fetcher(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${config.CLASSIFIER_API_KEY}` },
      body: JSON.stringify({ tweets: tweets.map(({ tweet_id, tweet, source_row }) => ({ tweet_id, tweet, source_row })) }),
      redirect: "error",
      signal: AbortSignal.timeout(90_000),
    });
  } catch {
    throw new ClassifierError("Classifier unavailable. Retry this batch.");
  }
  if (!upstream.ok) {
    const status = upstream.status === 503 || upstream.status === 429 ? 503 : 502;
    const retryAfter = upstream.headers.get("retry-after") ?? undefined;
    throw new ClassifierError(
      upstream.status === 503 || upstream.status === 429 ? "Classifier busy. Retry this batch." :
      upstream.status === 401 ? "Classifier authentication failed. Check the Worker secret." :
      `Classifier request failed (${upstream.status}).`, status, retryAfter,
    );
  }
  let payload: { results?: unknown; classifier_version?: unknown };
  try { payload = await upstream.json() as typeof payload; }
  catch { throw new ClassifierError("Classifier returned unreadable results. Retry this batch."); }
  if (!Array.isArray(payload.results) || payload.results.length !== tweets.length ||
    typeof payload.classifier_version !== "string" || !payload.classifier_version) {
    throw new ClassifierError("Classifier returned an incomplete batch. Retry this batch.");
  }
  const originals = new Map(tweets.map(tweet => [tweet.tweet_id, tweet]));
  const seen = new Set<string>();
  const results: Classification[] = [];
  for (const raw of payload.results as UpstreamRow[]) {
    const source = originals.get(raw?.tweet_id as string);
    if (!source || seen.has(source.tweet_id) || raw.tweet !== source.tweet || raw.source_row !== source.source_row ||
      !["relevant", "unrelated", "uncertain"].includes(raw.relevance as string) ||
      typeof raw.relevance_score !== "number" || !Number.isFinite(raw.relevance_score) ||
      raw.relevance_score < 0 || raw.relevance_score > 1 || typeof raw.needs_review !== "boolean" ||
      typeof raw.category !== "string" || typeof raw.reason !== "string" ||
      typeof raw.classifier_version !== "string" || raw.classifier_version !== payload.classifier_version) {
      throw new ClassifierError("Classifier returned mismatched or invalid reports. Retry this batch.");
    }
    seen.add(source.tweet_id);
    results.push({
      tweet_id: source.tweet_id,
      relevance: raw.relevance as Classification["relevance"],
      relevance_score: raw.relevance_score,
      category: raw.category,
      reason: raw.reason,
      model_version: raw.classifier_version,
      needs_review: raw.needs_review,
      classification_method: typeof raw.classification_method === "string" ? raw.classification_method : undefined,
    });
  }
  return { results, warnings: [], model_version: payload.classifier_version };
}
