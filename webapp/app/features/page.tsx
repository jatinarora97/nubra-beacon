import { get } from "@/lib/api";
import type { Feature } from "@/lib/types";
import { Badge, EmptyState, PageHeader, SectionCard } from "@/components/ui";

export default async function FeaturesPage() {
  const rows = await get<Feature[]>("/features", []);
  const sorted = [...rows].sort((a, b) => b.count - a.count);

  return (
    <div>
      <PageHeader
        title="Feature requests"
        accent="bg-warn"
        blurb="What traders keep asking for, across any broker. Different phrasings of the same ask are merged by meaning (embeddings), so one theme = one card. A theme needs 2+ mentions to appear."
      />

      {sorted.length === 0 ? (
        <EmptyState
          title="No feature theme crossed the bar"
          body="Themes need at least 2 merged mentions. Single one-off asks stay below the line until someone else asks for the same thing."
        />
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {sorted.map((f) => (
            <SectionCard key={f.feature_key}>
              <div className="flex items-start justify-between gap-3">
                <h3 className="text-[14px] font-semibold leading-snug">
                  {f.label}
                </h3>
                <Badge tone="warn">
                  {f.count} mention{f.count !== 1 ? "s" : ""}
                </Badge>
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
