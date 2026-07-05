import { get } from "@/lib/api";
import type { Trend } from "@/lib/types";
import { Badge, EmptyState, InfoTip, PageHeader, SectionCard } from "@/components/ui";

export default async function TrendsPage() {
  const rows = await get<Trend[]>("/trends?limit=20", []);
  const sorted = [...rows].sort((a, b) => b.count - a.count);
  const max = sorted[0]?.count ?? 1;
  const anyMomentum = sorted.some((t) => t.velocity_z != null);

  return (
    <div>
      <PageHeader
        title="Trending topics"
        accent="bg-trends"
        blurb="What the community is talking about, ranked by volume. A topic needs at least 3 items to count as a trend — one person is not a trend."
      />

      {sorted.length === 0 ? (
        <EmptyState
          title="Nothing crossed the trending bar yet"
          body="Trends require at least 3 items on a topic in the window. Check back after the next hourly run."
        />
      ) : (
        <SectionCard>
          <div className="mb-4 flex items-center gap-6 text-[12px] text-muted">
            <span>
              Momentum
              <InfoTip text="z-score of today's volume vs the topic's own 7-day baseline. Higher = more unusual. Needs 7 days of history." />
            </span>
            <span>
              Spread
              <InfoTip text="Distinct sources the topic appears on (X, Reddit). 2 sources = cross-platform conversation." />
            </span>
            <span>
              Engagement
              <InfoTip text="Sum of real interactions (likes + replies + shares) across the topic's items." />
            </span>
          </div>
          <div className="space-y-2.5">
            {sorted.map((t) => (
              <div key={t.topic_key} className="grid grid-cols-12 items-center gap-3">
                <div className="col-span-4 truncate text-[13px]" title={t.label ?? t.topic_key}>
                  {t.label ?? t.topic_key}
                </div>
                <div className="col-span-5">
                  <div className="h-5 w-full rounded bg-surface2">
                    <div
                      className="flex h-5 items-center rounded bg-trends/70 px-2 text-[11px] font-medium tabular-nums"
                      style={{ width: `${Math.max((t.count / max) * 100, 8)}%` }}
                    >
                      {t.count}
                    </div>
                  </div>
                </div>
                <div className="col-span-3 flex items-center justify-end gap-2">
                  {t.velocity_z != null && (
                    <Badge tone="trends">z {t.velocity_z.toFixed(1)}</Badge>
                  )}
                  {(t.spread ?? 0) > 1 && <Badge>{t.spread} sources</Badge>}
                  <span className="w-14 text-right text-[11.5px] tabular-nums text-muted">
                    {t.engagement_sum ?? 0} eng
                  </span>
                </div>
              </div>
            ))}
          </div>
          {!anyMomentum && (
            <p className="mt-4 border-t border-line pt-3 text-[12px] leading-relaxed text-muted">
              Momentum (z-score) is not shown yet — it needs 7 days of per-topic
              history to establish a baseline. It will appear automatically as
              history accumulates.
            </p>
          )}
        </SectionCard>
      )}
    </div>
  );
}
