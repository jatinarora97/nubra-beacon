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
            <span>· grounding {p.grounding}</span>
            {p.actions_recap?.opportunities_surfaced != null && (
              <span>· {p.actions_recap.opportunities_surfaced} opportunities surfaced</span>
            )}
          </div>

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
