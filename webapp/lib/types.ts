export type Kpis = {
  items_today?: number;
  analyzed_today?: number;
  actions_on_table?: number;
  new_high_priority_today?: number;
  nubra_mentions_24h?: number;
  drafts_ready?: number;
  items_last_hour?: number;
  analyzed_last_hour?: number;
  new_actions_last_hour?: number;
};

export type TopAction = {
  id: number;
  kind?: string;
  kind_label?: string;
  priority: number;
  why_engage?: string;
  title?: string;
  url?: string;
  interactions?: number;
};

export type Freshness = {
  sources?: Record<string, string>;
  source_schedule?: Record<string, { cadence: string; last?: string | null; next?: string }>;
  enriched_up_to?: string | null;
  schedule_installed?: boolean;
  next_hourly_run?: string;
  next_morning_build?: string;
};

/** Window echo returned by windowed endpoints (dashboard date filter). */
export type WindowEcho = { from?: string | null; to?: string | null };

export type Overview = {
  date?: string;
  headline?: string;
  kpis?: Kpis;
  top_actions?: TopAction[];
  top_movers?: { topic_key: string; label?: string; count: number }[];
  freshness?: Freshness;
  window?: WindowEcho;
  llm_last_run?: {
    run_id: string;
    cost_usd?: string | number | null;
    calls?: number;
    stages?: number;
    ts?: string;
  } | null;
};

export type LlmUsageSummary = {
  window_days: number;
  totals?: {
    cost_usd?: string | number | null;
    calls?: number;
    input_tokens?: number;
    output_tokens?: number;
    batch_cost?: string | number | null;
    batch_calls?: number;
    traced_calls?: number;
    unpriced_calls?: number;
  };
  by_day?: {
    day: string;
    cost_usd?: string | number | null;
    input_tokens?: number;
    output_tokens?: number;
    calls: number;
  }[];
  by_stage?: {
    stage: string;
    cost_usd?: string | number | null;
    calls: number;
    tokens?: number;
  }[];
  by_model?: {
    model: string;
    batch: boolean;
    cost_usd?: string | number | null;
    calls: number;
    input_tokens?: number;
    output_tokens?: number;
  }[];
  recent_runs?: {
    run_id: string;
    started?: string;
    ended?: string;
    calls: number;
    stages: number;
    stage_list?: string[];
    tokens?: number;
    cost_usd?: string | number | null;
  }[];
};

export type NubraMentions = {
  window_days?: number;
  window?: WindowEcho;
  kpis?: {
    mentions_24h?: number;
    mentions_window?: number;
    positive_share?: number | null;
    complaints_window?: number;
  };
  positives?: {
    source: string;
    external_id: string;
    text: string;
    url?: string;
    created_at?: string;
    author?: string;
    sentiment?: number | null;
    intent?: string;
    topic_key?: string;
  }[];
};

export type WeeklyEntry = {
  key: string;
  kind: string;
  label: string;
  metric?: number;
  rank_score?: number;
  weeks_running?: number;
};

export type WeekStats = {
  collected?: number;
  duplicates_merged?: number;
  noise_filtered?: number;
  analyzed?: number;
  trends_identified?: number;
  issue_segments?: number;
  feature_themes?: number;
  opportunities?: number;
  drafts_written?: number;
  headsups_sent?: number;
};

export type WeeklyRoundup = {
  period: string;
  date: string;
  week_stats?: WeekStats;
  payload: {
    window?: { from?: string; to?: string };
    grounding?: string;
    new_this_week?: WeeklyEntry[];
    consistent_features?: WeeklyEntry[];
    persisted?: WeeklyEntry[];
    actions_recap?: {
      opportunities_surfaced?: number;
      status_changes?: { status?: string; n?: number }[];
    };
  };
};

export type Trend = {
  topic_key: string;
  label?: string;
  count: number;
  velocity_z?: number | null;
  spread?: number | null;
  engagement_sum?: number | null;
};

export type IssueSample = { text: string; url?: string };
export type Issue = {
  broker: string;
  issue_key: string;
  count: number;
  severity?: number | null;
  sentiment_avg?: number | null;
  samples?: IssueSample[];
  day_counts?: unknown;
};

export type Feature = {
  feature_key: string;
  label: string;
  count: number;
  interactions?: number;
  brokers_mentioned?: string[];
  samples?: { text: string; url?: string; source?: string }[];
};

export type Voice = {
  handle: string;
  source: string;
  profile_url?: string;
  followers?: number | null;
  niche_topics?: string[];
  why?: string;
  recent_thread?: { title?: string; url?: string } | null;
  authenticity_flag?: boolean;
};

export type Opportunity = {
  id: number;
  priority: number;
  kind?: string;
  kind_label?: string;
  why_engage?: string;
  interactions?: number | null;
  age_h?: number | null;
  url?: string;
  title?: string;
  brand_reply?: string | null;
  rep_reply?: string | null;
  when_action?: string;
  when_window?: string;
  when_why?: string;
  status: string;
};

export type CatalogFeature = {
  feature: string;
  description: string;
  status: "live" | "upcoming";
  category?: string | null;
  seo_keywords?: string[];
};

export type FeaturesCatalog = {
  version?: string | null;
  published_at?: string | null;
  features: CatalogFeature[];
};

export type Proposal = {
  day?: string;
  rank: number;
  revisions_count?: number;
  last_revised_by?: string | null;
  treatment?: string;
  format_family?: string;
  platform?: string;
  platform_why?: string;
  hook?: string;
  beats?: string[];
  caption?: string;
  hashtags?: string[];
  cta?: string;
  visual_direction?: string;
  why?: string;
  window?: string;
};

export type Item = {
  item_id: number;
  source: string;
  source_type?: string;
  external_id?: string;
  text: string;
  url?: string;
  author?: string;
  created_at?: string;
  ingested_at?: string;
  engagement?: { score?: number; native?: Record<string, number> };
  duplicate_count?: number;
  topic_key?: string;
  intent?: string;
};

export type SourceHealth = {
  live?: string;
  detail?: string;
  name: string;
  stored_source: string;
  enabled: boolean;
  health: "working" | "enabled_not_run" | "needs_key" | "error" | "disabled" | string;
  credential: "configured" | "missing" | "optional_missing" | "not_required" | string;
  required_key?: string | null;
  optional_key?: string | null;
  last_success_at?: string | null;
  last_error?: string | null;
  last_error_at?: string | null;
  watermark?: string | null;
  items_last_run?: number | null;
  stored_items: number;
};

export type SocialRecommendation = {
  id: number;
  run_id: number;
  day: string;
  recommendation_key: string;
  segment: "retail" | "api";
  platform: "linkedin" | "x" | "instagram" | "youtube";
  post_format: "text_post" | "thread" | "carousel" | "short_video" | "product_demo";
  title: string;
  hook: string;
  body: string;
  cta: string;
  exact_copy: string;
  hashtags: string[];
  mapped_features: {
    id: string;
    name: string;
    status: "live" | "upcoming";
    segment: "retail" | "api" | "shared";
    description?: string;
  }[];
  source_evidence: {
    item_id: number;
    source: string;
    source_type?: string;
    text: string;
    url?: string;
    created_at?: string;
  }[];
  rationale: string;
  visual_brief: string;
  recommended_timing?: string;
  priority_score: number | string;
  status: "draft" | "approved" | "rejected" | "published";
  compliance_status: "passed" | "failed";
  model: string;
  prompt_version: string;
  context_version: string;
  edited_by?: string | null;
  created_at: string;
  updated_at: string;
};

export type SocialRecommendationStatus = {
  module: string;
  ready: boolean;
  context?: {
    version: string;
    updated_at: string;
    feature_count: number;
    live_features: number;
    upcoming_features: number;
    retail_features: number;
    api_features: number;
  };
  latest_run?: {
    id: number;
    status: "running" | "succeeded" | "failed" | "skipped";
    model: string;
    prompt_version: string;
    context_version: string;
    window_days: number;
    stats?: Record<string, unknown>;
    error?: string | null;
    created_at: string;
    completed_at?: string | null;
  } | null;
};

export type SocialRecommendationPreview = {
  items?: number;
  sources?: string[];
  retail_items?: number;
  api_items?: number;
  context_version?: string;
  context_features?: number;
  candidate_features?: { retail?: number; api?: number };
  claude_configured?: boolean;
};

export const DISMISS_REASONS = [
  "not_relevant",
  "already_handled",
  "too_late",
  "too_risky",
  "other",
] as const;
