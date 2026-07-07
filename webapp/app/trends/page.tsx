import { get } from "@/lib/api";
import type { Trend } from "@/lib/types";
import { Badge, EmptyState, PageHeader, SectionCard } from "@/components/ui";
import { TopicSuggestions } from "./topic-suggestions";

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
          <div className="mt-4 space-y-1.5 border-t border-line pt-3 text-[12px] leading-relaxed text-muted">
            <div className="micro mb-2">How each number is computed</div>
            <p>
              <span className="font-medium text-ink">Volume (bar)</span> = distinct
              posts + comments tagged to the topic in the window, duplicates merged.
            </p>
            <p>
              <span className="font-medium text-ink">Momentum (z)</span> = (today&apos;s
              volume − 7-day mean) / (7-day std + 1). Above ~1.5 means unusually busy.
              {!anyMomentum &&
                " Not shown yet — it needs 7 days of per-topic history and will appear automatically."}
            </p>
            <p>
              <span className="font-medium text-ink">Spread</span> = distinct sources
              (X, Reddit) the topic appeared on in the window. 2 sources = the
              conversation is cross-platform, not one community&apos;s echo.
            </p>
            <p>
              <span className="font-medium text-ink">Engagement index (eng)</span> = sum
              over the topic&apos;s items of log(1 + likes + 2·shares + 3·replies). Log-scaled
              per item so one viral post cannot drown the chart — compare topics with it,
              but do not read it as a raw interaction count.
            </p>
            <p>
              <span className="font-medium text-ink">Relevance score</span> is not on this
              page — it is the 0–100 ranking on Opportunities: 30% relevance to Nubra +
              25% freshness/velocity + 15% reach + 15% opportunity type + 15% author
              quality, boosted up to +15% when a topic keeps resurfacing.
            </p>
          </div>
        </SectionCard>
      )}

      <TopicSuggestions />
    </div>
  );
}
