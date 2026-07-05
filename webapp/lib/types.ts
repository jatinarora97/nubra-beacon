export type Kpis = {
  items_today?: number;
  analyzed_today?: number;
  actions_on_table?: number;
  new_high_priority_today?: number;
  nubra_mentions_24h?: number;
  drafts_ready?: number;
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

export type Overview = {
  date?: string;
  headline?: string;
  kpis?: Kpis;
  top_actions?: TopAction[];
  top_movers?: { topic_key: string; label?: string; count: number }[];
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

export type Proposal = {
  rank: number;
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

export const DISMISS_REASONS = [
  "not_relevant",
  "already_handled",
  "too_late",
  "too_risky",
  "other",
] as const;
