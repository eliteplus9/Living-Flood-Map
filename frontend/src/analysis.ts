import type { ProcessedTweet } from "../../shared/contracts";

export interface Filters { query: string; relevance: string; category: string; location: string; minScore: number; unique: boolean }
export const defaultFilters: Filters = { query: "", relevance: "relevant", category: "all", location: "all", minScore: 0, unique: true };
export function filterReports(rows: ProcessedTweet[], filters: Filters) {
  const seen = new Set<string>();
  return rows.filter(row => {
    const label = row.classification?.relevance ?? "failed";
    if (filters.relevance !== "all" && filters.relevance !== label) return false;
    if (row.classification && row.classification.relevance_score < filters.minScore) return false;
    if (filters.category !== "all" && row.classification?.category !== filters.category) return false;
    if (filters.location !== "all" && !row.locations.some(loc => (loc.canonical_name ?? loc.mention) === filters.location)) return false;
    if (filters.query && ![row.tweet, ...row.locations.map(loc => loc.canonical_name ?? loc.mention)].join(" ").toLowerCase().includes(filters.query.toLowerCase())) return false;
    const key = row.normalized_tweet.toLowerCase();
    if (filters.unique && seen.has(key)) return false;
    seen.add(key); return true;
  });
}
export function rankedCounts(rows: ProcessedTweet[], kind: "category" | "location") {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const names = kind === "category" ? [row.classification?.category ?? "Unprocessed"] :
      [...new Set(row.locations.filter(loc => loc.status === "resolved").map(loc => loc.canonical_name ?? loc.mention))];
    for (const name of names) counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts].sort((a, b) => b[1] - a[1]);
}
export function exportCsv(rows: ProcessedTweet[]) {
  const quote = (value: unknown) => {
    const text = String(value ?? "");
    return '"' + (/^[=+@\-\t\r]/.test(text) ? "'" + text : text).replaceAll('"', '""') + '"';
  };
  return [
    ["tweet_id", "source_record", "tweet", "relevance", "relevance_score", "category", "needs_review", "classifier_version", "locations_json", "duplicate_of", "processing_error"].join(","),
    ...rows.map(row => [row.tweet_id, row.source_row, row.tweet, row.classification?.relevance ?? "unprocessed",
      row.classification?.relevance_score, row.classification?.category, row.classification?.needs_review, row.classification?.model_version, JSON.stringify(row.locations), row.duplicate_of,
      row.classification_error ?? row.location_error].map(quote).join(",")),
  ].join("\r\n");
}
