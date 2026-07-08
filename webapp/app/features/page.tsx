import { get } from "@/lib/api";
import type { Feature } from "@/lib/types";
import { Badge, EmptyState, PageHeader, SectionCard } from "@/components/ui";

export default async function FeaturesPage() {
  const rows = await get<Feature[]>("/features", []);
  // Mentions first, real interactions as the tiebreak.
  const sorted = [...rows].sort(
    (a, b) => b.count - a.count || (b.interactions ?? 0) - (a.interactions ?? 0),
  );

  return (
    <div>
      <PageHeader
        title="Feature requests"
        accent="bg-warn"
        blurb="What traders are asking for, across any broker — sorted by mentions, then by the interactions (likes + replies + shares) those mentions draw. Different phrasings of the same ask are merged by meaning, so one theme = one card; even a single mention appears."
      />

      {sorted.length === 0 ? (
        <EmptyState
          title="No feature requests in the window"
          body="Feature asks are extracted from posts where someone is requesting a capability. They appear here as soon as one is picked up."
        />
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {sorted.map((f) => (
            <SectionCard key={f.feature_key}>
              <div className="flex items-start justify-between gap-3">
                <h3 className="text-[14px] font-semibold leading-snug">
                  {f.label}
                </h3>
                <span className="flex shrink-0 items-center gap-1.5">
                  <Badge tone="warn">
                    {f.count} mention{f.count !== 1 ? "s" : ""}
                  </Badge>
                  <span
                    className="text-[11.5px] tabular-nums text-muted"
                    title="Real interactions summed across this theme's mentions: likes + upvotes + replies + comments + shares"
                  >
                    {f.interactions ?? 0} interaction{(f.interactions ?? 0) !== 1 ? "s" : ""}
                  </span>
                </span>
              </div>
              {(f.brokers_mentioned?.length ?? 0) > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {f.brokers_mentioned!.map((b) => (
                    <Badge key={b}>{b}</Badge>
                  ))}
                </div>
              )}
              {(f.samples?.length ?? 0) > 0 && (
                <div className="mt-3 space-y-2 border-t border-line pt-3">
                  <div className="micro">in their words</div>
                  {f.samples!.slice(0, 3).map((s, i) => (
                    <blockquote
                      key={i}
                      className="border-l-2 border-warn/40 pl-3 text-[12.5px] leading-relaxed text-muted"
                    >
                      “{s.text}”
                      {s.url && (
                        <a
                          href={s.url}
                          target="_blank"
                          className="ml-2 text-trends hover:underline"
                        >
                          source
                        </a>
                      )}
                    </blockquote>
                  ))}
                </div>
              )}
            </SectionCard>
          ))}
        </div>
      )}
    </div>
  );
}
