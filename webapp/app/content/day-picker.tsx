"use client";

import { usePathname, useRouter } from "next/navigation";

/** Briefs regenerate each morning — the natural filter is a day, not a time
 *  window. Chips for recent days, a select for the rest. */
export function DayPicker({
  days,
  active,
}: {
  days: { day: string; briefs: number }[];
  active: string;
}) {
  const router = useRouter();
  const path = usePathname();
  if (days.length === 0) return null;

  const fmt = (d: string) =>
    new Date(`${d}T00:00:00`).toLocaleDateString("en-IN", {
      day: "2-digit",
      month: "short",
      timeZone: "Asia/Kolkata",
    });
  const go = (d: string) => router.push(`${path}?date=${d}`, { scroll: false });
  const chips = days.slice(0, 5);

  return (
    <div className="mb-5 flex flex-wrap items-center gap-1.5">
      <span className="text-[12.5px] text-muted">Briefs for</span>
      {chips.map((d) => (
        <button
          key={d.day}
          onClick={() => go(d.day)}
          className={`rounded-md border px-3 py-1 text-[12.5px] font-medium transition-colors ${
            d.day === active
              ? "border-content/50 bg-content/10 text-content"
              : "border-line text-muted hover:border-muted hover:text-ink"
          }`}
          title={`${d.briefs} brief${d.briefs !== 1 ? "s" : ""}`}
        >
          {fmt(d.day)}
        </button>
      ))}
      {/* calendar for anything further back — bounded by the brief history */}
      <input
        type="date"
        value={active}
        min={days[days.length - 1]?.day}
        max={days[0]?.day}
        onChange={(e) => e.target.value && go(e.target.value)}
        className="rounded-md border border-line bg-surface2 px-2.5 py-1 text-[12.5px] text-muted outline-none focus:border-content"
        aria-label="Pick any date"
        title="Jump to any date — days without briefs show an empty state"
      />
    </div>
  );
}
