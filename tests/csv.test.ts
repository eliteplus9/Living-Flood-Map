import { describe, expect, it } from "vitest";
import { rowsToTweets } from "../frontend/src/csv";

describe("rowsToTweets", () => {
  it("preserves source rows and links duplicate text", () => {
    const rows = [{ tweet: "Flood in Calgary" }, { tweet: "Flood in Calgary" }, { tweet: "" }];
    const tweets = rowsToTweets(rows, "tweet");
    expect(tweets).toHaveLength(2);
    expect(tweets[0].source_row).toBe(2);
    expect(tweets[1].duplicate_of).toBe(tweets[0].tweet_id);
  });
});
