import { get } from "@/lib/api";
import type { Proposal } from "@/lib/types";
import { Badge, EmptyState, PageHeader, SectionCard } from "@/components/ui";
import { CopyButton } from "@/components/client";

export default async function ContentPage() {
  const rows = await get<Proposal[]>("/content-proposals", []);
  const sorted = [...rows].sort((a, b) => a.rank - b.rank);

  return (
    <div>
      <PageHeader
        title="Content briefs"
        accent="bg-content"
        blurb="Creator-ready briefs riding today's community signal — ranked, capped at three, each targeted at the platform where it will land best. Hand a card to a creator and they can execute without questions."
      />

      {sorted.length === 0 ? (
        <EmptyState
          title="No briefs for today yet"
          body="Briefs are generated with the daily build from the day's rising topics, issues and feature requests, then pass the compliance gate. Ideas that fail the gate are dropped, so some days ship fewer than three."
        />
      ) : (
        <div className="space-y-4">
          {sorted.map((c) => (
            <SectionCard key={c.rank}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="micro mb-1">brief {c.rank}</div>
                  <h3 className="text-[15px] font-semibold leading-snug">
                    {c.treatment ?? c.format_family ?? "Untitled brief"}
                  </h3>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {c.platform && <Badge tone="content">{c.platform.replace(/_/g, " ")}</Badge>}
                  {c.format_family && <Badge>{c.format_family.replace(/_/g, " ")}</Badge>}
                  {c.window && <Badge>post {c.window}</Badge>}
                </div>
              </div>

              {c.platform_why && (
                <p className="mt-1.5 text-[12.5px] text-muted">
                  Why this platform: {c.platform_why}
                </p>
              )}

              {c.hook && (
                <blockquote className="mt-3 border-l-2 border-content/60 pl-3 text-[14px] font-medium leading-relaxed">
                  {c.hook}
                </blockquote>
              )}

              {(c.beats?.length ?? 0) > 0 && (
                <div className="mt-4">
                  <div className="micro mb-2">production checklist</div>
                  <ol className="space-y-1.5">
                    {c.beats!.map((b, i) => (
                      <li key={i} className="flex gap-2.5 text-[13px] leading-relaxed">
                        <span className="mt-px shrink-0 text-[11.5px] font-semibold tabular-nums text-content">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        <span>{b}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              {(c.caption || (c.hashtags?.length ?? 0) > 0 || c.cta) && (
                <div className="mt-4 rounded-md border border-line bg-surface2/50 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="micro">ready to paste</span>
                    <CopyButton
                      text={[
                        c.caption,
                        (c.hashtags ?? []).join(" "),
                        c.cta,
                      ]
                        .filter(Boolean)
                        .join("\n\n")}
                      label="Copy caption kit"
                    />
                  </div>
                  {c.caption && (
                    <p className="text-[13px] leading-relaxed">{c.caption}</p>
                  )}
                  {(c.hashtags?.length ?? 0) > 0 && (
                    <p className="mt-1.5 text-[12.5px] text-trends">
                      {c.hashtags!.join(" ")}
                    </p>
                  )}
                  {c.cta && (
                    <p className="mt-1.5 text-[12.5px] text-muted">CTA: {c.cta}</p>
                  )}
                </div>
              )}

              <div className="mt-3 flex flex-col gap-1 border-t border-line pt-3 text-[12.5px] text-muted">
                {c.visual_direction && <span>Visual direction: {c.visual_direction}</span>}
                {c.why && <span>Why now: {c.why}</span>}
              </div>
            </SectionCard>
          ))}
        </div>
      )}
    </div>
  );
}
