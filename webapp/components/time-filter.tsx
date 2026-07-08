"use client";

import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { WINDOW_PRESETS, type WindowSearch } from "@/lib/window";

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
  // "custom" = any window that isn't one of the preset chips
  const isPreset = WINDOW_PRESETS.some((p) => p.key === current.window);
  const customActive = !isPreset || Boolean(current.from_ts && current.to_ts);
  const customMatch = (current.window ?? "").match(/^(\d{1,4})([hd])$/);
  const [showCustom, setShowCustom] = useState(customActive);
  const [num, setNum] = useState(customMatch ? customMatch[1] : "2");
  const [unit, setUnit] = useState<"h" | "d">(
    customMatch ? (customMatch[2] as "h" | "d") : "h",
  );
  const [hint, setHint] = useState<string | null>(null);

  function go(params: Record<string, string>) {
    const qs = new URLSearchParams({ ...extra, ...params });
    router.push(`${path}?${qs}`, { scroll: false });
  }

  function applyCustom() {
    let n = Math.floor(Number(num));
    if (!Number.isFinite(n) || n < 1) {
      n = 1;
      setNum("1");
      setHint("Minimum is 1 hour.");
    } else if (unit === "d" && n > 180) {
      n = 180;
      setNum("180");
      setHint("Capped at 180 days (retention horizon).");
    } else if (unit === "h" && n > 4320) {
      n = 4320;
      setNum("4320");
      setHint("Capped at 180 days (retention horizon).");
    } else {
      setHint(null);
    }
    go({ window: `${n}${unit}` });
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
          <span className="text-[12.5px] text-muted">Last</span>
          <input
            type="number"
            min={1}
            value={num}
            onChange={(e) => setNum(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applyCustom()}
            className={`${inputCls} w-20`}
            aria-label="Number of hours or days"
          />
          <select
            value={unit}
            onChange={(e) => setUnit(e.target.value as "h" | "d")}
            className={inputCls}
            aria-label="Unit"
          >
            <option value="h">hours</option>
            <option value="d">days</option>
          </select>
          <button onClick={applyCustom} className={chipCls(false)}>
            Apply
          </button>
          {hint && <span className="text-[11.5px] text-warn">{hint}</span>}
        </div>
      )}
    </div>
  );
}
