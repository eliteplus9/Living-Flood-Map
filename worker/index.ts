import type {
  BatchRequest,
  BatchResponse,
  Classification,
  LocationResult,
  SourceTweet,
  SummaryResponse,
} from "../shared/contracts";
import { ClassifierError, classifyWithService, type ClassifierConfig } from "./classifier";
import { LocationServiceError, locateWithService, type LocationConfig } from "./location-service";

interface Env extends ClassifierConfig, LocationConfig {
  ASSETS: Fetcher;
  API_RATE_LIMIT?: { limit(options: { key: string }): Promise<{ success: boolean }> };
}

const MODEL_VERSION = "baseline-rules-2026-09-26";
const FLOOD_TERMS = /\b(flood(?:s|ed|ing)?|evacuat\w*|sandbag\w*|washed out|disaster|emergency|rescu\w*|relief)\b|#(?:yycfloods?|abfloods?|mhflood|calgaryflood)\b/i;
const IMPACT_TERMS = /\b(road|bridge|closed|closure|power|damage|water|river|home|basement|shelter|missing|stranded|supplies|volunteer|donat\w*)\b/i;
const NOISE_TERMS = /#(?:job|hiring)\b|\b(?:apply today|now hiring|job opening)\b/i;

const places = [
  ["Calgary", 51.0447, -114.0719, /\b(?:calgary|yyc)\b/i],
  ["High River", 50.5801, -113.8740, /\bhigh\s*river\b/i],
  ["Canmore", 51.0890, -115.3597, /\bcanmore\b/i],
  ["Medicine Hat", 50.0405, -110.6765, /\b(?:medicine hat|medhat)\b/i],
  ["Siksika Nation", 50.8340, -112.9380, /\b(?:siksika|siksika nation)\b/i],
  ["Bragg Creek", 50.9513, -114.5603, /\bbragg creek\b/i],
  ["Banff", 51.1784, -115.5708, /\bbanff\b/i],
  ["Lethbridge", 49.6956, -112.8451, /\blethbridge\b/i],
  ["Edmonton", 53.5461, -113.4938, /\b(?:edmonton|yeg)\b/i],
  ["Bowness, Calgary", 51.0896, -114.1967, /\bbowness\b/i],
  ["Inglewood, Calgary", 51.0395, -114.0308, /\binglewood\b/i],
  ["Sunnyside, Calgary", 51.0565, -114.0790, /\bsunnyside\b/i],
] as const;

function json(value: unknown, status = 200): Response {
  return Response.json(value, { status, headers: { "cache-control": "no-store" } });
}

async function batchRequest(request: Request, limit = 50): Promise<BatchRequest> {
  const body = await request.json() as Partial<BatchRequest>;
  if (!Array.isArray(body.tweets) || body.tweets.length === 0) throw new Error("A non-empty tweets array is required.");
  if (body.tweets.length > limit) throw new Error(`A maximum of ${limit} tweets is allowed per batch.`);
  const ids = new Set<string>();
  for (const row of body.tweets) {
    if (!row || typeof row.tweet_id !== "string" || !row.tweet_id || ids.has(row.tweet_id) ||
      typeof row.tweet !== "string" || typeof row.normalized_tweet !== "string" ||
      row.tweet.length > 20000 || row.normalized_tweet.length > 20000 ||
      !Number.isInteger(row.source_row) || row.source_row < 1) throw new Error("Each report needs a unique ID, source record and valid text (up to 20,000 characters).");
    ids.add(row.tweet_id);
  }
  if (body.context && (typeof body.context !== "object" ||
    (body.context.region !== undefined && typeof body.context.region !== "string") ||
    (body.context.event_name !== undefined && typeof body.context.event_name !== "string") ||
    (body.context.country_code !== undefined && (typeof body.context.country_code !== "string" || !/^[A-Za-z]{2}$/.test(body.context.country_code))))) throw new Error("Invalid event context.");
  return body as BatchRequest;
}

function classify(tweet: SourceTweet): Classification {
  const text = tweet.normalized_tweet;
  const flood = FLOOD_TERMS.test(text);
  const impact = IMPACT_TERMS.test(text);
  const noise = NOISE_TERMS.test(text);
  let relevance: Classification["relevance"] = "uncertain";
  let score = 0.5;
  let reason = "The report contains limited event evidence and should be reviewed.";
  if (noise && !flood) { relevance = "unrelated"; score = 0.05; reason = "Likely employment or promotional noise."; }
  else if (flood && impact) { relevance = "relevant"; score = 0.94; reason = "Contains both flood-event and impact language."; }
  else if (flood) { relevance = "relevant"; score = 0.82; reason = "Contains explicit flood or emergency language."; }
  else if (!impact) { relevance = "unrelated"; score = 0.22; reason = "No flood-event or impact signal was detected."; }
  const category = /evacuat/i.test(text) ? "evacuation"
    : /road|bridge|closed|closure/i.test(text) ? "access"
    : /donat|volunteer|relief|supplies/i.test(text) ? "relief"
    : /damage|home|basement|power/i.test(text) ? "damage"
    : "general report";
  return { tweet_id: tweet.tweet_id, relevance, relevance_score: score, category, reason, model_version: MODEL_VERSION, needs_review: relevance === "uncertain" };
}

function locate(tweet: SourceTweet, region = ""): LocationResult[] {
  const results: LocationResult[] = [];
  for (const [canonical_name, latitude, longitude, pattern] of places) {
    const match = tweet.normalized_tweet.match(pattern);
    if (!match) continue;
    const neighbourhood = canonical_name.includes(", Calgary");
    const compatible = /alberta|calgary|\byyc\b/i.test(region + " " + tweet.normalized_tweet);
    if (neighbourhood && !compatible) {
      results.push({ tweet_id: tweet.tweet_id, mention: match[0], location_score: 0.4, status: "ambiguous" });
    } else results.push({ tweet_id: tweet.tweet_id, mention: match[0], canonical_name, latitude, longitude, location_score: 0.8, status: "resolved" });
  }
  return results;
}

function summarize(tweets: SourceTweet[]): SummaryResponse {
  const unique = new Map(tweets.map((tweet) => [tweet.normalized_tweet.toLocaleLowerCase(), tweet]));
  const reports = [...unique.values()];
  const counts = places.map(([name, , , pattern]) => [name, reports.filter((tweet) => pattern.test(tweet.normalized_tweet)).length] as const)
    .filter(([, count]) => count > 0).sort((a, b) => b[1] - a[1]).slice(0, 4);
  const impacts = reports.filter((tweet) => IMPACT_TERMS.test(tweet.normalized_tweet)).length;
  const placeText = counts.length ? `The most frequently mentioned resolved areas are ${counts.map(([name, count]) => `${name} (${count})`).join(", ")}.` : "Few reports contain confidently resolved locations.";
  return {
    summary: `${reports.length} unique potentially relevant reports were reviewed. ${impacts} describe impacts, access, needs, or response activity. ${placeText}`,
    evidence_ids: reports.slice(0, 8).map((tweet) => tweet.tweet_id),
    model_version: MODEL_VERSION,
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(request);
    if (request.method === "GET" && url.pathname === "/api/health") {
      const classifier_mode = env.CLASSIFIER || env.CLASSIFIER_URL && env.CLASSIFIER_API_KEY ? "service" : env.CLASSIFIER_URL || env.CLASSIFIER_API_KEY ? "unconfigured" : "preview";
      const location_mode = env.LOCATION || env.LOCATION_URL && env.LOCATION_API_KEY ? "service" : env.LOCATION_URL || env.LOCATION_API_KEY ? "unconfigured" : "preview";
      return json({ ok: true, service: "living-flood-map", classifier_mode, location_mode, model_version: classifier_mode === "preview" ? MODEL_VERSION : undefined });
    }
    if (request.method !== "POST") return json({ error: "Method not allowed." }, 405);
    if (env.API_RATE_LIMIT && !(await env.API_RATE_LIMIT.limit({ key: request.headers.get("CF-Connecting-IP") || "unknown" })).success) {
      return json({ error: "Too many requests. Please retry shortly." }, 429);
    }
    try {
      if (!["/api/classify", "/api/locations", "/api/summarize"].includes(url.pathname)) return json({ error: "API route not found." }, 404);
      const body = await batchRequest(request, url.pathname === "/api/summarize" ? 200 : url.pathname === "/api/classify" ? 500 : 50);
      if (url.pathname === "/api/classify") {
        if (env.CLASSIFIER || env.CLASSIFIER_URL || env.CLASSIFIER_API_KEY) {
          return json(await classifyWithService(body.tweets, env));
        }
        const response: BatchResponse<Classification> = { results: body.tweets.map(classify), warnings: [], model_version: MODEL_VERSION };
        return json(response);
      }
      if (url.pathname === "/api/locations") {
        if (env.LOCATION || env.LOCATION_URL || env.LOCATION_API_KEY) {
          return json(await locateWithService(body.tweets, body.context, env));
        }
        const response: BatchResponse<LocationResult> = { results: body.tweets.flatMap(tweet => locate(tweet, body.context?.region)), warnings: [], model_version: MODEL_VERSION };
        return json(response);
      }
      if (url.pathname === "/api/summarize") return json(summarize(body.tweets));
      return json({ error: "API route not found." }, 404);
    } catch (error) {
      if (error instanceof ClassifierError || error instanceof LocationServiceError) {
        const response = json({ error: error.message }, error.status);
        if (error.retryAfter) response.headers.set("retry-after", error.retryAfter);
        return response;
      }
      return json({ error: error instanceof Error ? error.message : "Request failed." }, 400);
    }
  },
} satisfies ExportedHandler<Env>;
