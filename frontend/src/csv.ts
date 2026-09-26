import Papa from "papaparse";
import type { SourceTweet } from "../../shared/contracts";

export interface ParsedCsv {
  rows: Record<string, unknown>[];
  columns: string[];
  warnings: string[];
}

export function parseCsv(file: File): Promise<ParsedCsv> {
  if (file.size > 10 * 1024 * 1024) return Promise.reject(new Error("Choose a CSV smaller than 10 MB."));
  return new Promise((resolve, reject) => {
    Papa.parse<Record<string, unknown>>(file, {
      header: true,
      skipEmptyLines: "greedy",
      transformHeader: (header) => header.replace(/^\uFEFF/, "").trim(),
      complete: ({ data, meta, errors }) => {
        const fatal = errors.find((error) => error.type === "Quotes" || error.type === "FieldMismatch");
        if (fatal) {
          reject(new Error(`CSV could not be parsed: ${fatal.message}`));
          return;
        }
        if (data.length > 25000) { reject(new Error("Choose a CSV with at most 25,000 rows.")); return; }
        // A single-column CSV has no delimiter to detect; that is a valid input.
        const warnings = errors.filter(error => !(error.code === "UndetectableDelimiter" && meta.fields?.length === 1))
          .slice(0, 5).map((error) => `Record ${error.row ?? "?"}: ${error.message}`);
        resolve({ rows: data, columns: meta.fields ?? [], warnings });
      },
      error: (error) => reject(error),
    });
  });
}

export function normalizeTweet(value: string): string {
  return value
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#(?:39|x27);/gi, "'")
    .replace(/&#(\d+);/g, (match, code: string) => Number(code) <= 0x10ffff ? String.fromCodePoint(Number(code)) : match)
    .replace(/\s+/g, " ")
    .trim();
}

function fnv1a(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(36);
}

export function rowsToTweets(rows: Record<string, unknown>[], column: string): SourceTweet[] {
  const firstByText = new Map<string, string>();
  return rows.flatMap((row, index) => {
    const raw = row[column];
    const tweet = raw == null ? "" : String(raw);
    if (!tweet.trim()) return [];
    const normalized_tweet = normalizeTweet(tweet);
    const tweet_id = `row-${index + 2}-${fnv1a(normalized_tweet)}`;
    const duplicate_of = firstByText.get(normalized_tweet.toLocaleLowerCase());
    if (!duplicate_of) firstByText.set(normalized_tweet.toLocaleLowerCase(), tweet_id);
    return [{ tweet_id, source_row: index + 2, tweet, normalized_tweet, duplicate_of }];
  });
}
