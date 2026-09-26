import type { ProcessedTweet } from "../../shared/contracts";

// Adapted from the map experiment: one marker per valid coordinate, one count per tweet ID.
export function groupPlaces(rows: ProcessedTweet[]) {
  const groups = new Map<string, { name: string; coordinates: [number, number]; reports: ProcessedTweet[] }>();
  for (const row of rows) for (const location of row.locations) {
    if (location.status !== "resolved" || !Number.isFinite(location.latitude) || !Number.isFinite(location.longitude) ||
      Math.abs(location.latitude!) > 90 || Math.abs(location.longitude!) > 180) continue;
    const coordinates: [number, number] = [location.latitude!, location.longitude!];
    const key = coordinates.join(",");
    const group = groups.get(key) ?? { name: location.canonical_name ?? location.mention, coordinates, reports: [] };
    if (!group.reports.some(item => item.tweet_id === row.tweet_id)) group.reports.push(row);
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => b.reports.length - a.reports.length);
}
