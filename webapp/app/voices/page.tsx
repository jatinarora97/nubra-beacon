import { get } from "@/lib/api";
import type { Voice } from "@/lib/types";
import { Badge, EmptyState, PageHeader, SectionCard } from "@/components/ui";

export default async function VoicesPage() {
  const rows = await get<Voice[]>("/voices?limit=12", []);

  return (
    <div>
      <PageHeader
        title="Rising voices"
        accent="bg-voices"
        blurb="Community members worth building a relationship with — consistently relevant, active across topics, and gaining traction. Ranked by voice score (relevance × consistency × breadth)."
      />

      {rows.length === 0 ? (
        <EmptyState
          title="Not enough history yet"
          body="Voice scores build up as authors post repeatedly over the trailing 30 days."
        />
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {rows.map((v, i) => (
            <SectionCard key={`${v.source}-${v.handle}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-semibold text-muted">#{i + 1}</span>
                    <a
                      href={v.profile_url ?? "#"}
                      target="_blank"
                      className="truncate text-[14.5px] font-semibold text-voices hover:underline"
                    >
                      @{v.handle}
                    </a>
                    <Badge>{v.source}</Badge>
                    {v.authenticity_flag && (
                      <Badge tone="warn">authenticity flagged</Badge>
                    )}
                  </div>
                  {v.followers != null && (
                    <div className="mt-1 text-[12px] text-muted">
                      {v.followers.toLocaleString("en-IN")} followers
                    </div>
                  )}
                </div>
              </div>

              {(v.niche_topics?.length ?? 0) > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {v.niche_topics!.map((t) => (
                    <Badge key={t} tone="voices">
                      {t}
                    </Badge>
                  ))}
                </div>
              )}

              {v.why && (
                <p className="mt-2.5 text-[12.5px] leading-relaxed text-muted">
                  {v.why}
                </p>
              )}

              {v.recent_thread?.url && (
                <a
                  href={v.recent_thread.url}
                  target="_blank"
                  className="mt-2.5 block truncate border-t border-line pt-2.5 text-[12.5px] text-trends hover:underline"
                >
                  Recent: “{v.recent_thread.title ?? v.recent_thread.url}”
                </a>
              )}
            </SectionCard>
          ))}
        </div>
      )}
    </div>
  );
}
