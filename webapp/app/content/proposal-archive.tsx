"use client";

import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { Badge, EmptyState, SectionCard } from "@/components/ui";

/* Read-only archive of the pre-queue "content proposals" (generated daily by
   the v1 pipeline until 2026-09) — kept visible so earlier briefs and their
   platforms aren't lost under the new queue (user ask 2026-09-17). */

type Proposal = {
  day: string;
  rank: number;
  treatment: string;
  format_family: string | null;
  platform: string | null;
  hook: string;
  outline: string | null;
  why: string | null;
  recommended_timing: string | null;
};

const PLATFORM_LABELS: Record<string, string> = {
  x_post: "X post",
  x_thread: "X thread",
  linkedin_post: "LinkedIn",
  instagram_post: "Instagram",
  youtube_short: "YouTube Short",
  reddit_post: "Reddit",
};

export function ProposalArchive() {
  const [days, setDays] = useState<{ day: string; briefs: number }[]>([]);
  const [day, setDay] = useState<string>("");
  const [rows, setRows] = useState<Proposal[] | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    get<{ day: string; briefs: number }[]>("/content-proposals/days", []).then(
      (d) => {
        setDays(d);
        if (d.length > 0) setDay(d[0].day);
      },
    );
  }, []);

  useEffect(() => {
    if (!open || !day) return;
    setRows(null);
    get<Proposal[]>(`/content-proposals?date=${day}`, []).then(setRows);
  }, [open, day]);

  if (days.length === 0) return null;

  return (
    <section className="mt-8">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 text-[13.5px] font-semibold"
      >
        <span className="text-[10px] text-muted">{open ? "▼" : "▶"}</span>
        Earlier briefs (archive)
        <span className="micro font-normal">
          daily proposals from the previous system · {days.length} days
        </span>
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          <select
            value={day}
            onChange={(e) => setDay(e.target.value)}
            className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-[12.5px]"
          >
            {days.map((d) => (
              <option key={d.day} value={d.day}>
                {d.day} ({d.briefs})
              </option>
            ))}
          </select>
          {rows === null ? (
            <div className="micro">loading…</div>
          ) : rows.length === 0 ? (
            <EmptyState title="No briefs on this day" body="" />
          ) : (
            rows.map((p) => (
              <SectionCard key={`${p.day}-${p.rank}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="muted">
                    {PLATFORM_LABELS[p.platform ?? ""] ?? p.platform ?? "any"}
                  </Badge>
                  {p.format_family && <Badge tone="content">{p.format_family}</Badge>}
                  <span className="micro">#{p.rank}</span>
                  {p.recommended_timing && (
                    <span className="micro ml-auto">{p.recommended_timing}</span>
                  )}
                </div>
                <div className="mt-2 text-[13px] font-medium">{p.hook}</div>
                <p className="mt-1 text-[12.5px] leading-relaxed text-muted">
                  {p.treatment}
                </p>
                {p.outline && (
                  <details className="mt-2">
                    <summary className="micro cursor-pointer">outline</summary>
                    <p className="mt-1 whitespace-pre-wrap text-[12px] text-muted">
                      {p.outline}
                    </p>
                  </details>
                )}
              </SectionCard>
            ))
          )}
        </div>
      )}
    </section>
  );
}
