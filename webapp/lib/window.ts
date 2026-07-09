/** Shared time-window handling (server + client safe).
 *  Default = last hour: the dashboard opens on the freshest hourly view. */

export type WindowSearch = { window?: string; from_ts?: string; to_ts?: string };

export const WINDOW_PRESETS = [
  { key: "1h", label: "Last hour" },
  { key: "24h", label: "24 hours" },
  { key: "7d", label: "7 days" },
  { key: "30d", label: "30 days" },
] as const;

type RawSearch = Record<string, string | string[] | undefined>;

const one = (v?: string | string[]) => (Array.isArray(v) ? v[0] : v);

/** Any "last N hours/days" is a valid window (backend contract: \d+h|\d+d). */
const WINDOW_RE = /^\d{1,4}[hd]$/;

/** Resolve URL search params to the active window.
 *  Default: last hour (flow pages). Inventory pages (Opportunities) pass
 *  defaultAll=true — no params resolves to {} = no window = everything open. */
export function pickWindow(sp: RawSearch, defaultAll = false): WindowSearch {
  const from_ts = one(sp.from_ts);
  const to_ts = one(sp.to_ts);
  if (from_ts && to_ts) return { from_ts, to_ts };
  const w = one(sp.window);
  if (w && WINDOW_RE.test(w)) return { window: w };
  return defaultAll ? {} : { window: "1h" };
}

/** Query-string fragment for API calls (empty string = unwindowed). */
export function windowQuery(w: WindowSearch): string {
  if (w.from_ts && w.to_ts)
    return `from_ts=${encodeURIComponent(w.from_ts)}&to_ts=${encodeURIComponent(w.to_ts)}`;
  return w.window ? `window=${w.window}` : "";
}

/** Human phrase for blurbs/hints/empty states ("the last hour", "the last 8 hours"). */
export function windowLabel(w: WindowSearch): string {
  if (w.from_ts && w.to_ts) return "the selected range";
  if (!w.window && !w.from_ts) return "all time";
  const m = (w.window ?? "1h").match(/^(\d{1,4})([hd])$/);
  if (!m) return "the window";
  const n = Number(m[1]);
  const unit = m[2] === "h" ? "hour" : "day";
  return n === 1 ? `the last ${unit}` : `the last ${n} ${unit}s`;
}
