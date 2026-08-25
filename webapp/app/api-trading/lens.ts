/** Shared vocabulary + types for the API-trading section (server + client
 *  safe). The lens tracks traders who trade via code/APIs, not charts —
 *  taxonomy mirrors community/enrich/api_trader.py. */

export type FunnelStage = {
  stage: string;
  total: number;
  kinds: Record<string, number>;
};
export type FunnelResp = {
  days: number;
  stages: FunnelStage[];
  first_api_split: Record<string, number>;
};

export type ThemeItem = {
  item_id: number;
  gist: string | null;
  stage: string | null;
  source: string;
  url: string | null;
  text: string;
  eng: number;
};
export type ThemeRow = { theme: string; n: number; items: ThemeItem[] };
export type ThemesResp = { days: number; kind: string; themes: ThemeRow[] };

export type Candidate = {
  key: string;
  title: string;
  themes: string[];
  grounding: string[];
  current: number;
  previous: number;
  trend: "up" | "down" | "flat";
};

export type LandscapeFeature = {
  id: number;
  competitor: string;
  feature: string;
  status: string;
  evidence_url: string | null;
  first_seen: string | null;
  last_seen: string | null;
  added_by: string;
  notes: string | null;
};
export type LandscapePlayer = {
  name: string;
  corpus: number;
  relevant: number;
  frictions: number;
  features: LandscapeFeature[];
};
export type LandscapeResp = {
  days: number;
  players: LandscapePlayer[];
  untracked_features: Record<string, LandscapeFeature[]>;
};

export type LensItem = {
  item_id: number;
  stage: string | null;
  first_api_type: string | null;
  layer: string | null;
  kind: string | null;
  tools: string[] | null;
  gist: string | null;
  friction_theme: string | null;
  working_theme: string | null;
  source: string;
  url: string | null;
  text: string;
  created_at: string | null;
  author: string | null;
  engagement: number;
};

/* ── days window (these endpoints take ?days=N, not the window= contract) ── */

export const DAYS_PRESETS = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 180, label: "180 days" },
] as const;

export function pickDays(
  sp: Record<string, string | string[] | undefined>,
  fallback = 90,
): number {
  const raw = Array.isArray(sp.days) ? sp.days[0] : sp.days;
  const n = Number(raw);
  return Number.isInteger(n) && n >= 1 && n <= 365 ? n : fallback;
}

/* ── taxonomy display names ─────────────────────────────────────────────── */

export const STAGE_ORDER = [
  "exploring",
  "first_api",
  "building",
  "scaling",
  "churning",
] as const;

export const STAGE_META: Record<string, { label: string; meaning: string }> = {
  exploring: { label: "Exploring", meaning: "researching before touching an API" },
  first_api: { label: "First API", meaning: "first API setup: keys, auth, first order" },
  building: { label: "Building", meaning: "strategy + backtest development" },
  scaling: { label: "Scaling", meaning: "running live money, multi-strategy" },
  churning: { label: "Churning", meaning: "giving up / walking away" },
};

export const KIND_ORDER = [
  "friction",
  "guidance_seeking",
  "showcase",
  "comparison",
] as const;

export const KIND_META: Record<string, { label: string; bar: string }> = {
  friction: { label: "friction", bar: "bg-danger/70" },
  guidance_seeking: { label: "guidance seeking", bar: "bg-warn/70" },
  showcase: { label: "showcase", bar: "bg-opps/70" },
  comparison: { label: "comparison", bar: "bg-content/70" },
};
export const KIND_FALLBACK_BAR = "bg-muted/50";

export const FIRST_API_SPLIT_LABELS: Record<string, string> = {
  broker: "first broker API",
  any: "first API ever",
  unclear: "unclear",
};

export const FRICTION_THEME_LABELS: Record<string, string> = {
  cost_pricing: "Cost & pricing",
  reliability: "Reliability & uptime",
  order_primitives: "Order primitives & execution",
  backtest_trust: "Backtest trust",
  data_access: "Data access",
  deployment_infra: "Deployment & infra",
  onboarding_auth: "Onboarding & auth",
  risk_controls: "Risk controls",
  regulation: "Regulation",
  data_quality: "Data quality",
};

export const WORKING_THEME_LABELS: Record<string, string> = {
  automation_live: "Automation running live",
  live_pnl: "Live P&L shared",
  backtest_proof: "Backtest proof",
  free_data_builds: "Free-data builds",
  ai_assisted: "AI-assisted building",
  no_code: "No-code builders",
};

export const THEME_LABELS: Record<string, string> = {
  ...FRICTION_THEME_LABELS,
  ...WORKING_THEME_LABELS,
};

export function themeLabel(key: string): string {
  return THEME_LABELS[key] ?? key.replace(/_/g, " ");
}

export const LAYERS = [
  "broker_api",
  "no_code_builder",
  "backtesting",
  "data_feed",
  "charting_signal",
  "community_learning",
] as const;

export const SOURCE_LABELS: Record<string, string> = {
  twitter: "X / Twitter",
  reddit: "Reddit",
  youtube: "YouTube",
  github: "GitHub",
  community_forum: "Broker community",
  app_review: "App review",
  instagram: "Instagram",
};
