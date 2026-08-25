"use client";

import { usePathname, useRouter } from "next/navigation";
import { DAYS_PRESETS } from "./lens";

/** Preset day-window chips for the API-trading section. These endpoints speak
 *  ?days=N (not the window= contract), so this is a slimmer TimeFilter:
 *  state lives in the URL, `extra` carries the page's other params. */
export function DaysFilter({
  days,
  extra = {},
}: {
  days: number;
  extra?: Record<string, string>;
}) {
  const router = useRouter();
  const path = usePathname();

  const chipCls = (active: boolean) =>
    `rounded-md border px-3 py-1 text-[12.5px] font-medium transition-colors ${
      active
        ? "border-trends/50 bg-trends/10 text-trends"
        : "border-line text-muted hover:border-muted hover:text-ink"
    }`;

  return (
    <div className="mb-5 flex flex-wrap items-center gap-1.5">
      {DAYS_PRESETS.map((p) => (
        <button
          key={p.days}
          onClick={() => {
            const qs = new URLSearchParams({ ...extra, days: String(p.days) });
            router.push(`${path}?${qs}`, { scroll: false });
          }}
          className={chipCls(days === p.days)}
        >
          {p.label}
        </button>
      ))}
      {!DAYS_PRESETS.some((p) => p.days === days) && (
        <span className={chipCls(true)}>Last {days} days</span>
      )}
    </div>
  );
}
