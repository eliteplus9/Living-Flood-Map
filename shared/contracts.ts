export type Relevance = "relevant" | "unrelated" | "uncertain";
export type LocationStatus = "resolved" | "ambiguous" | "unresolved";

export interface SourceTweet {
  tweet_id: string;
  source_row: number;
  tweet: string;
  normalized_tweet: string;
  duplicate_of?: string;
}

export interface Classification {
  tweet_id: string;
  relevance: Relevance;
  relevance_score: number;
  category?: string;
  reason?: string;
  model_version: string;
  needs_review?: boolean;
  classification_method?: string;
}

export interface LocationResult {
  tweet_id: string;
  mention: string;
  canonical_name?: string;
  latitude?: number;
  longitude?: number;
  location_score: number;
  status: LocationStatus;
}

export interface ProcessedTweet extends SourceTweet {
  classification?: Classification;
  locations: LocationResult[];
  classification_error?: string;
  location_error?: string;
}

export interface AnalysisContext {
  event_name?: string;
  region?: string;
  country_code?: string;
}

export interface BatchRequest {
  tweets: SourceTweet[];
  context?: AnalysisContext;
}

export interface BatchResponse<T> {
  results: T[];
  warnings: string[];
  model_version: string;
}

export interface SummaryResponse {
  summary: string;
  evidence_ids: string[];
  model_version: string;
}
