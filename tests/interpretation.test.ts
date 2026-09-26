import { describe, expect, it, vi } from "vitest";
vi.mock("../frontend/src/MapPanel", () => ({ default: () => null }));
import { interpret, placeRole } from "../shared/interpretation";
import { briefingText } from "../frontend/src/Investigation";
describe("evidence interpretation", () => {
  it.each([
    ["Clothing is no longer needed in Siksika.", "correction"],
    ["There is NO risk of a dam breach.", "correction"],
    ["Can anyone confirm the bridge is closed?", "question"],
    ["We need blankets in Calgary.", "request"],
    ["Our Calgary office is accepting donations for Siksika.", "offer"],
  ])("preserves meaning and evidence: %s", (text, kind) => {
    const result = interpret(text);
    expect(result.signals.length).toBeGreaterThan(0);
    expect(result.signals.every(signal => signal.kind === kind)).toBe(true);
    expect(result.signals.every(signal => text.includes(signal.evidence))).toBe(true);
  });
  it("does not extend reassurance to another clause", () => {
    const result = interpret("The dams are safe and sound. The bridge is closed.");
    expect(result.signals.find(signal => signal.subject === "Access")?.kind).toBe("report");
  });
  it("distinguishes beneficiary and collection point without inventing roles", () => {
    expect(placeRole("Donations for Siksika at our Edmonton office", "Siksika")).toBe("Possible beneficiary");
    expect(placeRole("Donations for Siksika at our Edmonton office", "Edmonton")).toBe("Possible collection point");
    expect(placeRole("Floods in Calgary", "Calgary")).toContain("unresolved");
  });
  it("exports corrections separately from the source and includes uncertainty", () => {
    const text = briefingText([{ tweet_id: "a", source_row: 2, tweet: "Calgary flood", normalized_tweet: "Calgary flood", locations: [] }], "Calgary", { a: { note: "Place needs review", locationDisputed: true, relevance: "uncertain" } });
    expect(text).toContain("LOCATION DISPUTED");
    expect(text).toContain("Reviewer relevance: uncertain");
    expect(text).toContain("Source: Calgary flood");
    expect(text).toContain("chronology");
  });
});
