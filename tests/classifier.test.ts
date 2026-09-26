import { describe, expect, it, vi } from "vitest";
import { classifyWithService, ClassifierError } from "../worker/classifier";
import type { SourceTweet } from "../shared/contracts";

const tweets: SourceTweet[] = [{ tweet_id: "source-1", source_row: 2, tweet: "  flood warning  ", normalized_tweet: "flood warning" }];
const config = { CLASSIFIER_URL: "https://classifier.example", CLASSIFIER_API_KEY: "secret-for-test" };
const valid = () => ({ results: [{ tweet_id: "source-1", source_row: 2, tweet: "  flood warning  ", relevance: "relevant", relevance_score: 0.91, category: "warning", reason: "Incident phrase", needs_review: true, classification_method: "incident_phrase", classifier_version: "test-v1" }], classifier_version: "test-v1" });

describe("hosted classifier adapter", () => {
  it("sends only accepted fields with the Worker-held bearer key and preserves report IDs", async () => {
    const fetcher = vi.fn(async (_url: URL, init: RequestInit) => {
      expect(init.headers).toMatchObject({ authorization: "Bearer secret-for-test" });
      expect(JSON.parse(init.body as string)).toEqual({ tweets: [{ tweet_id: "source-1", tweet: "  flood warning  ", source_row: 2 }] });
      return Response.json(valid());
    });
    const response = await classifyWithService(tweets, config, fetcher as typeof fetch);
    expect(fetcher.mock.calls[0][0].toString()).toBe("https://classifier.example/classify");
    expect(response.results[0]).toMatchObject({ tweet_id: "source-1", relevance: "relevant", relevance_score: 0.91, needs_review: true, model_version: "test-v1" });
  });

  it("rejects mismatched text and IDs instead of accepting incomplete classifications", async () => {
    for (const wrong of [{ ...valid(), results: [{ ...valid().results[0], tweet: "changed" }] }, { ...valid(), results: [{ ...valid().results[0], tweet_id: "other" }] }]) {
      await expect(classifyWithService(tweets, config, async () => Response.json(wrong))).rejects.toThrow(ClassifierError);
    }
  });

  it("keeps configuration, authentication and busy failures distinct", async () => {
    await expect(classifyWithService(tweets, { CLASSIFIER_URL: config.CLASSIFIER_URL })).rejects.toMatchObject({ status: 503 });
    await expect(classifyWithService(tweets, config, async () => new Response(null, { status: 401 }))).rejects.toMatchObject({ status: 502, message: expect.stringContaining("authentication") });
    await expect(classifyWithService(tweets, config, async () => new Response(null, { status: 503, headers: { "retry-after": "1" } }))).rejects.toMatchObject({ status: 503, retryAfter: "1" });
  });
});
