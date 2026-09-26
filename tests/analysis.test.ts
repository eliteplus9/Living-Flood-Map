import { describe, expect, it } from "vitest";
import { defaultFilters, exportCsv, filterReports } from "../frontend/src/analysis";
import { normalizeTweet, rowsToTweets } from "../frontend/src/csv";
import worker from "../worker/index";
const source = rowsToTweets([{ tweet: "Flooded bridge" }, { tweet: "Flooded bridge" }], "tweet");
describe("report accounting", () => {
  it("keeps failed rows available independently of classifier uncertainty", () => {
    const rows = source.map(row => ({ ...row, locations: [], classification_error: "offline" }));
    expect(filterReports(rows, { ...defaultFilters, relevance: "failed", unique: false })).toHaveLength(2);
    expect(filterReports(rows, { ...defaultFilters, relevance: "failed" })).toHaveLength(1);
  });
  it("preserves original whitespace and prevents spreadsheet formulas in export", () => {
    const [row] = rowsToTweets([{ tweet: "  text &amp; water  " }], "tweet");
    expect(row.tweet).toBe("  text &amp; water  ");
    expect(row.normalized_tweet).toBe("text & water");
    expect(normalizeTweet("&#999999999;")).toBe("&#999999999;");
    expect(exportCsv([{ ...row, tweet: "=1+1", locations: [] }])).toContain('"\'=1+1"');
  });
});
describe("worker contract", () => {
  const call = (route: string, tweets: unknown[]) => worker.fetch(new Request("https://test/api/" + route, {
    method: "POST", body: JSON.stringify({ tweets }), headers: { "content-type": "application/json" },
  }), {} as Parameters<typeof worker.fetch>[1]);
  it("supports the documented 200-report summary but limits classifier batches", async () => {
    const rows = Array.from({ length: 200 }, (_, i) => ({ ...source[0], tweet_id: String(i) }));
    expect((await call("summarize", rows)).status).toBe(200);
    expect((await call("classify", rows)).status).toBe(200);
    const tooMany = Array.from({ length: 501 }, (_, i) => ({ ...source[0], tweet_id: String(i) }));
    expect((await call("classify", tooMany)).status).toBe(400);
  });
  it("rejects malformed and duplicate IDs", async () => {
    expect((await call("classify", [{ tweet_id: "bad" }])).status).toBe(400);
    expect((await call("classify", [source[0], source[0]])).status).toBe(400);
  });
  it("does not assign an ambiguous neighbourhood to Calgary without context", async () => {
    const [row] = rowsToTweets([{ tweet: "Flooding in Inglewood" }], "tweet");
    const response = await call("locations", [row]);
    expect((await response.json() as any).results[0].status).toBe("ambiguous");
  });
});
