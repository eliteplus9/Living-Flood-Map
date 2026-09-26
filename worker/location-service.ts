import type { AnalysisContext, BatchResponse, LocationResult, SourceTweet } from "../shared/contracts";

export interface LocationConfig {
  LOCATION?: { fetch: typeof fetch };
  LOCATION_URL?: string;
  LOCATION_API_KEY?: string;
}

export class LocationServiceError extends Error {
  constructor(message: string, readonly status = 502, readonly retryAfter?: string) { super(message); }
}

export async function locateWithService(
  tweets: SourceTweet[], context: AnalysisContext | undefined, config: LocationConfig, fetcher: typeof fetch = fetch,
): Promise<BatchResponse<LocationResult>> {
  if (!config.LOCATION && (!config.LOCATION_URL || !config.LOCATION_API_KEY)) {
    throw new LocationServiceError("The location service is not fully configured.", 503);
  }
  let endpoint: URL;
  try {
    endpoint = new URL("/locations", config.LOCATION ? "https://locations.internal" : config.LOCATION_URL);
    if (endpoint.protocol !== "https:" && !(endpoint.protocol === "http:" && ["localhost", "127.0.0.1"].includes(endpoint.hostname))) {
      throw new Error("HTTPS required");
    }
  } catch {
    throw new LocationServiceError("The location service URL is invalid.", 503);
  }
  let upstream: Response;
  try {
    upstream = await (config.LOCATION ? config.LOCATION.fetch.bind(config.LOCATION) : fetcher)(config.LOCATION ? endpoint.toString() : endpoint, {
      method: "POST", redirect: "manual",
      headers: { "content-type": "application/json", ...(config.LOCATION ? {} : { authorization: `Bearer ${config.LOCATION_API_KEY}` }) },
      body: JSON.stringify({
        tweets: tweets.map(({ tweet_id, tweet, source_row }) => ({ tweet_id, tweet, source_row })),
        ...(context?.country_code ? { prefer_country: context.country_code } : {}),
      }),
      signal: AbortSignal.timeout(90_000),
    });
  } catch {
    throw new LocationServiceError("Location service unavailable. Retry this batch.");
  }
  if (!upstream.ok) {
    const retryAfter = upstream.headers.get("retry-after") ?? undefined;
    throw new LocationServiceError(
      upstream.status === 401 ? "Location service authentication failed. Check the Worker secret." :
      upstream.status === 503 || upstream.status === 429 ? "Location service busy. Retry this batch." :
      `Location service request failed (${upstream.status}).`,
      upstream.status === 503 || upstream.status === 429 ? 503 : 502, retryAfter,
    );
  }
  let payload: { results?: unknown; model_version?: unknown; warnings?: unknown };
  try { payload = await upstream.json() as typeof payload; }
  catch { throw new LocationServiceError("Location service returned unreadable results."); }
  if (!Array.isArray(payload.results) || typeof payload.model_version !== "string" || !payload.model_version) {
    throw new LocationServiceError("Location service returned an invalid batch.");
  }
  const ids = new Set(tweets.map(tweet => tweet.tweet_id));
  const results: LocationResult[] = [];
  for (const raw of payload.results as Record<string, unknown>[]) {
    if (!raw || typeof raw.tweet_id !== "string" || !ids.has(raw.tweet_id) || typeof raw.mention !== "string" ||
      !["resolved", "ambiguous", "unresolved"].includes(raw.status as string) ||
      typeof raw.location_score !== "number" || !Number.isFinite(raw.location_score) || raw.location_score < 0 || raw.location_score > 1 ||
      (raw.status === "resolved" && (typeof raw.canonical_name !== "string" || !raw.canonical_name ||
        typeof raw.latitude !== "number" || !Number.isFinite(raw.latitude) || Math.abs(raw.latitude) > 90 ||
        typeof raw.longitude !== "number" || !Number.isFinite(raw.longitude) || Math.abs(raw.longitude) > 180)) ||
      (raw.status !== "resolved" && (raw.latitude != null || raw.longitude != null))) {
      throw new LocationServiceError("Location service returned invalid report IDs or coordinates.");
    }
    results.push({
      tweet_id: raw.tweet_id, mention: raw.mention, status: raw.status as LocationResult["status"],
      location_score: raw.location_score,
      ...(raw.status === "resolved" ? { canonical_name: raw.canonical_name as string,
        latitude: raw.latitude as number, longitude: raw.longitude as number } : {}),
    });
  }
  return { results, warnings: Array.isArray(payload.warnings) ? payload.warnings.filter((value): value is string => typeof value === "string") : [], model_version: payload.model_version };
}
