import { afterEach, describe, expect, it, vi } from "vitest";
import type { SourceTweet } from "../shared/contracts";
import { LocationServiceError, locateWithService } from "../worker/location-service";
import worker from "../worker/index";

const tweets: SourceTweet[] = [{ tweet_id: "source-1", source_row: 2, tweet: "Flood in Calgary", normalized_tweet: "Flood in Calgary" }];
const config = { LOCATION_URL: "https://locations.example", LOCATION_API_KEY: "test-key" };
const valid = () => ({ results: [{ tweet_id: "source-1", mention: "Calgary", canonical_name: "Calgary, Canada", latitude: 51.04, longitude: -114.07, location_score: 0.8, status: "resolved" }], warnings: [], model_version: "mutasim-context-v1" });

afterEach(() => vi.unstubAllGlobals());
describe("location service boundary", () => {
  it("calls the private location binding without exposing a provider key", async () => {
    const privateFetch = vi.fn(async (_url: string, init: RequestInit) => {
      expect(init.headers).toEqual({ "content-type": "application/json" });
      expect(init.redirect).toBe("manual");
      return Response.json(valid());
    });
    const publicFetch = vi.fn();
    const response = await locateWithService(tweets, undefined, { LOCATION: { fetch: privateFetch as typeof fetch } }, publicFetch);
    expect(response.results[0].tweet_id).toBe("source-1");
    expect(publicFetch).not.toHaveBeenCalled();
  });
  it("passes stable IDs and explicit country choice while retaining multiple mentions", async () => {
    const fetcher = vi.fn(async (_url: URL, init: RequestInit) => {
      expect(init.headers).toMatchObject({ authorization: "Bearer test-key" });
      expect(JSON.parse(init.body as string)).toEqual({ tweets: [{ tweet_id: "source-1", tweet: "Flood in Calgary", source_row: 2 }], prefer_country: "CA" });
      return Response.json({ ...valid(), results: [...valid().results, { ...valid().results[0], mention: "Alberta" }] });
    });
    const output = await locateWithService(tweets, { country_code: "CA" }, config, fetcher as typeof fetch);
    expect(fetcher.mock.calls[0][0].toString()).toBe("https://locations.example/locations");
    expect(output.results).toHaveLength(2);
  });

  it("rejects invalid IDs and coordinates, and never interprets an outage as no locations", async () => {
    await expect(locateWithService(tweets, undefined, config, async () => Response.json({ ...valid(), results: [{ ...valid().results[0], tweet_id: "other" }] }))).rejects.toThrow(LocationServiceError);
    await expect(locateWithService(tweets, undefined, config, async () => Response.json({ ...valid(), results: [{ ...valid().results[0], latitude: 999 }] }))).rejects.toThrow(LocationServiceError);
    await expect(locateWithService(tweets, undefined, config, async () => new Response(null, { status: 503 }))).rejects.toMatchObject({ status: 503 });
  });

  it("uses preview only with no service configuration and surfaces partial configuration", async () => {
    const request = () => new Request("https://test/api/locations", { method: "POST", body: JSON.stringify({ tweets }) });
    const preview = await worker.fetch(request(), {} as Parameters<typeof worker.fetch>[1]);
    expect(preview.status).toBe(200);
    expect((await preview.json() as { results: unknown[] }).results.length).toBeGreaterThan(0);
    const partial = await worker.fetch(request(), { LOCATION_URL: config.LOCATION_URL } as Parameters<typeof worker.fetch>[1]);
    expect(partial.status).toBe(503);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(valid())));
    const remote = await worker.fetch(request(), config as Parameters<typeof worker.fetch>[1]);
    expect(remote.status).toBe(200);
    expect((await remote.json() as { model_version: string }).model_version).toBe("mutasim-context-v1");
  });
});
