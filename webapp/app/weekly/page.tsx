import { get } from "@/lib/api";
import type { WeeklyEntry, WeeklyRoundup } from "@/lib/types";
import { Badge, EmptyState, PageHeader, SectionCard } from "@/components/ui";

export const dynamic = "force-dynamic";

function EntryList({ entries, tone }: { entries: WeeklyEntry[]; tone: "trends" | "warn" }) {
  const max = Math.max(...entries.map((e) => e.metric ?? 0), 1);
  return (
    <div className="space-y-2">
      {entries.map((e) => (
        <div key={`${e.kind}-${e.key}`} className="grid grid-cols-12 items-center gap-3">
          <div className="col-span-4 flex items-center gap-2 truncate">
            <span className="truncate text-[13px]" title={e.label}>
              {e.label.replace(/_/g, " ")}
            </span>
            <Badge tone={tone}>{e.kind.replace(/_/g, " ")}</Badge>
          </div>
          <div className="col-span-6">
            <div className="h-4 w-full rounded bg-surface2">
              <div
                className={`flex h-4 items-center rounded px-1.5 text-[10.5px] font-medium tabular-nums ${
                  tone === "trends" ? "bg-trends/70" : "bg-warn/70"
                }`}
                style={{ width: `${Math.max(((e.metric ?? 0) / max) * 100, 6)}%` }}
              >
                {e.metric ?? 0}
              </div>
            </div>
          </div>
          <div className="col-span-2 text-right text-[11.5px] tabular-nums text-muted">
            {e.weeks_running != null &&
              `${e.weeks_running} wk${e.weeks_running !== 1 ? "s" : ""} running`}
          </div>
        </div>
      ))}
    </div>
  );
}

export default async function WeeklyPage() {
  const r = await get<WeeklyRoundup | null>("/roundups?period=weekly", null);
  const p = r?.payload;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Weekly roundup"
        accent="bg-trends"
        blurb="The Saturday-to-Saturday view: what emerged this week, what keeps coming back week after week (persistence-weighted — recurring themes outrank one-week spikes), and what the team acted on."
      />

      {!p ? (
        <EmptyState
          title="No weekly roundup yet"
          body="The weekly composes every Saturday 10:00 IST over the Sat-to-Sat window. It appears here (and in Slack/email once creds are in) after the first Saturday run."
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3 text-[12.5px] text-muted">
            <span>
              window {p.window?.from} → {p.window?.to}
            </span>
          </div>

          {r?.week_stats && (
            <SectionCard>
              <div className="micro mb-3">The week in numbers</div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                {(
                  [
                    ["Collected", r.week_stats.collected, "posts + comments pulled in"],
                    ["Duplicates merged", r.week_stats.duplicates_merged, "same content, counted once"],
                    ["Noise filtered", r.week_stats.noise_filtered, "spam / off-topic set aside"],
                    ["Analyzed", r.week_stats.analyzed, "tagged by topic, intent, sentiment"],
                    ["Trends identified", r.week_stats.trends_identified, "topics with 3+ items"],
                    ["Issue segments", r.week_stats.issue_segments, "broker x issue combinations"],
                    ["Feature themes", r.week_stats.feature_themes, "distinct asks (merged by meaning)"],
                    ["Opportunities", r.week_stats.opportunities, "conversations worth joining"],
                    ["Drafts written", r.week_stats.drafts_written, "compliant replies ready"],
                    ["Heads-ups sent", r.week_stats.headsups_sent, "hourly action alerts"],
                  ] as [string, number | undefined, string][]
                ).map(([label, value, hint]) => (
                  <div key={label} className="rounded-[10px] border border-line bg-surface2/40 px-3 py-2.5">
                    <div className="text-xl font-semibold tabular-nums">{value ?? "-"}</div>
                    <div className="mt-0.5 text-[11.5px] font-medium">{label}</div>
                    <div className="text-[11px] leading-snug text-muted">{hint}</div>
                  </div>
                ))}
              </div>
            </SectionCard>
          )}

          {(p.persisted?.length ?? 0) > 0 && (
            <SectionCard>
              <div className="micro mb-3">
                Persisting themes — running for 2+ weeks (weighted up)
              </div>
              <EntryList entries={p.persisted!} tone="warn" />
            </SectionCard>
          )}

          {(p.new_this_week?.length ?? 0) > 0 && (
            <SectionCard>
              <div className="micro mb-3">New this week</div>
              <EntryList entries={p.new_this_week!} tone="trends" />
            </SectionCard>
          )}

          {(p.consistent_features?.length ?? 0) > 0 && (
            <SectionCard>
              <div className="micro mb-3">Feature asks holding steady</div>
              <EntryList entries={p.consistent_features!} tone="warn" />
            </SectionCard>
          )}

          {(p.actions_recap?.status_changes?.length ?? 0) > 0 && (
            <SectionCard>
              <div className="micro mb-3">Team activity on recommendations</div>
              <div className="flex gap-4 text-[13px]">
                {p.actions_recap!.status_changes!.map((s, i) => (
                  <span key={i}>
                    {s.n} {s.status}
                  </span>
                ))}
              </div>
            </SectionCard>
          )}
        </>
      )}
    </div>
  );
}
