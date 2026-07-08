"use client";

import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { WINDOW_PRESETS, type WindowSearch } from "@/lib/window";

const HOUR_MS = 3_600_000;

/** Local datetime-input value for a Date (what <input type=datetime-local> wants). */
function toLocalInput(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function fmtIst(iso?: string | null): string {
  if (!iso) return "?";
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  });
}

/** Preset chips + custom range. Window state lives in the URL; `extra` carries
 *  the page's other params (e.g. opportunities' status) so chips preserve them. */
export function TimeFilter({
  current,
  extra = {},
  resolved,
}: {
  current: WindowSearch;
  extra?: Record<string, string>;
  resolved?: { from?: string | null; to?: string | null } | null;
}) {
  const router = useRouter();
  const path = usePathname();
  const customActive = Boolean(current.from_ts && current.to_ts);
  const [showCustom, setShowCustom] = useState(customActive);
  const [fromVal, setFromVal] = useState(
    current.from_ts ? toLocalInput(new Date(current.from_ts)) : toLocalInput(new Date(Date.now() - 24 * HOUR_MS)),
  );
  const [toVal, setToVal] = useState(
    current.to_ts ? toLocalInput(new Date(current.to_ts)) : toLocalInput(new Date()),
  );
  const [hint, setHint] = useState<string | null>(null);

  function go(params: Record<string, string>) {
    const qs = new URLSearchParams({ ...extra, ...params });
    router.push(`${path}?${qs}`, { scroll: false });
  }

  function applyCustom() {
    const from = new Date(fromVal);
    let to = new Date(toVal);
    if (isNaN(from.getTime()) || isNaN(to.getTime())) {
      setHint("Pick both a start and an end.");
      return;
    }
    if (to.getTime() - from.getTime() < HOUR_MS) {
      to = new Date(from.getTime() + HOUR_MS);
      setToVal(toLocalInput(to));
      setHint("Minimum span is 1 hour — end adjusted.");
    } else {
      setHint(null);
    }
    go({ from_ts: from.toISOString(), to_ts: to.toISOString() });
  }

  const chipCls = (active: boolean) =>
    `rounded-md border px-3 py-1 text-[12.5px] font-medium transition-colors ${
      active
        ? "border-trends/50 bg-trends/10 text-trends"
        : "border-line text-muted hover:border-muted hover:text-ink"
    }`;
  const inputCls =
    "rounded-md border border-line bg-surface2 px-2.5 py-1.5 text-[12.5px] text-ink outline-none focus:border-trends";

  return (
    <div className="mb-5">
      <div className="flex flex-wrap items-center gap-1.5">
        {WINDOW_PRESETS.map((p) => (
          <button
            key={p.key}
            onClick={() => {
              setShowCustom(false);
              go({ window: p.key });
            }}
            className={chipCls(!customActive && current.window === p.key)}
          >
            {p.label}
          </button>
        ))}
        <button onClick={() => setShowCustom((s) => !s)} className={chipCls(customActive)}>
          Custom
        </button>
        {resolved?.from && resolved?.to && (
          <span className="ml-2 text-[11.5px] text-muted">
            showing {fmtIst(resolved.from)} – {fmtIst(resolved.to)} IST
          </span>
        )}
      </div>
      {showCustom && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input
            type="datetime-local"
            value={fromVal}
            onChange={(e) => setFromVal(e.target.value)}
            className={inputCls}
            aria-label="From"
          />
          <span className="text-[12px] text-muted">to</span>
          <input
            type="datetime-local"
            value={toVal}
            onChange={(e) => setToVal(e.target.value)}
            className={inputCls}
            aria-label="To"
          />
          <button onClick={applyCustom} className={chipCls(false)}>
            Apply
          </button>
          {hint && <span className="text-[11.5px] text-warn">{hint}</span>}
        </div>
      )}
    </div>
  );
}
