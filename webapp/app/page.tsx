import Link from "next/link";
import { get } from "@/lib/api";
import type { Overview } from "@/lib/types";
import { Badge, KpiCard, SectionCard } from "@/components/ui";
import { TimeFilter } from "@/components/time-filter";
import { pickWindow, windowLabel, windowQuery } from "@/lib/window";

const NAV_CARDS = [
  {
    href: "/trends",
    title: "What's happening",
    body: "Trending topics, broker issues, and the feature requests traders keep raising.",
    tone: "bg-trends",
  },
  {
    href: "/opportunities",
    title: "What to do",
    body: "Ranked conversations worth joining, with compliant brand and rep drafts ready.",
    tone: "bg-opps",
  },
  {
    href: "/content",
    title: "What to make",
    body: "Creator-ready content briefs riding today's signal, with platform targeting.",
    tone: "bg-content",
  },
  {
    href: "/explore",
    title: "Verify the data",
    body: "Inspect the raw posts and comments behind every number on this dashboard.",
    tone: "bg-voices",
  },
];

// Only the numbers visible on THIS page — each page explains its own metrics.
const GLOSSARY = [
  ["Engagement", "real interactions: likes + replies + shares. Views and followers are reach, not engagement."],
  ["Relevance score", "0-100 blend of freshness, relevance to Nubra, reach, opportunity type and author quality — the score on each action card."],
];

function fmtIst(iso?: string | null): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  });
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const w = pickWindow(await searchParams);
  const label = windowLabel(w);
  const ov = await get<Overview>(`/overview?${windowQuery(w)}`, {});
  const k = ov.kpis ?? {};
  const f = ov.freshness;
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight">
          Nubra Beacon
        </h1>
        <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-muted">
          Beacon listens to Indian trading communities on X and Reddit,
          understands what is trending, breaking and being asked for, and
          recommends the smartest compliant way for Nubra to join the
          conversation. Humans act — Beacon only recommends.
        </p>
      </section>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {NAV_CARDS.map((c) => (
          <Link
            key={c.href}
            href={c.href}
            className="group rounded-[10px] border border-line bg-surface p-4 transition-colors hover:border-muted"
          >
            <span className={`mb-3 block h-1.5 w-8 rounded-full ${c.tone}`} />
            <div className="text-[14px] font-semibold group-hover:text-ink">
              {c.title}
            </div>
            <div className="mt-1 text-[12.5px] leading-relaxed text-muted">
              {c.body}
            </div>
          </Link>
        ))}
      </section>

      <TimeFilter current={w} resolved={ov.window} />

      {f && (
        <section className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded-[10px] border border-line bg-surface/50 px-4 py-2.5 text-[12px] text-muted">
          <span className="micro">freshness</span>
          {Object.entries(f.sources ?? {}).map(([src, ts]) => (
            <span key={src}>
              {src === "twitter" ? "X" : src} last item{" "}
              <span className="text-ink">{fmtIst(ts)}</span>
            </span>
          ))}
          {f.enriched_up_to && (
            <span>
              analyzed up to <span className="text-ink">{fmtIst(f.enriched_up_to)}</span>
            </span>
          )}
          <span className="ml-auto">
            next update <span className="text-ink">{fmtIst(f.next_hourly_run)}</span> · morning
            build <span className="text-ink">{fmtIst(f.next_morning_build)}</span>
          </span>
        </section>
      )}

      <section className="grid grid-cols-3 gap-3 lg:grid-cols-7">
        <KpiCard label="Items posted" value={k.items_today ?? "-"} hint={`in ${label}`} />
        <KpiCard
          label="Analyzed"
          value={k.analyzed_today ?? "-"}
          hint={`analysis completed in ${label}`}
        />
        <KpiCard
          label="Actions on table"
          value={k.actions_on_table ?? "-"}
          hint="open recommendations (all time)"
        />
        <KpiCard label="New high-priority" value={k.new_high_priority_today ?? "-"} hint={`in ${label}`} />
        <KpiCard label="Nubra mentions" value={k.nubra_mentions_24h ?? "-"} hint={`in ${label}`} />
        <KpiCard label="Drafts ready" value={k.drafts_ready ?? "-"} hint="compliant, awaiting a human" />
        <KpiCard
          label="AI cost, last run"
          value={
            ov.llm_last_run?.cost_usd != null
              ? `$${Number(ov.llm_last_run.cost_usd).toFixed(
                  Number(ov.llm_last_run.cost_usd) > 0 &&
                    Number(ov.llm_last_run.cost_usd) < 0.01
                    ? 4
                    : 2,
                )}`
              : "-"
          }
          hint={
            ov.llm_last_run
              ? `${ov.llm_last_run.calls} AI call${(ov.llm_last_run.calls ?? 0) !== 1 ? "s" : ""} in the last pipeline run`
              : "no runs recorded yet"
          }
        />
      </section>

      {ov.headline && (
        <SectionCard>
          <div className="micro mb-2">Today in one line</div>
          <p className="text-[14.5px] leading-relaxed">{ov.headline}</p>
        </SectionCard>
      )}

      {(ov.top_actions?.length ?? 0) > 0 && (
        <section>
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-[15px] font-semibold">Top actions right now</h2>
            <Link
              href="/opportunities"
              className="text-[12.5px] text-opps hover:underline"
            >
              all opportunities →
            </Link>
          </div>
          <div className="space-y-2.5">
            {ov.top_actions!.slice(0, 3).map((a, i) => (
              <SectionCard key={a.id} className="flex items-start gap-4">
                <div className="mt-0.5 text-[13px] font-semibold text-muted">
                  {i + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="opps">{a.kind_label ?? a.kind ?? "action"}</Badge>
                    <span className="text-[11.5px] text-muted">
                      score {a.priority}/100
                      {a.interactions != null &&
                        ` · ${a.interactions} interactions`}
                    </span>
                  </div>
                  {a.why_engage && (
                    <p className="mt-1.5 text-[13.5px] leading-relaxed">
                      {a.why_engage}
                    </p>
                  )}
                  {a.title && (
                    <p className="mt-1 truncate text-[12.5px] text-muted">
                      “{a.title}”
                    </p>
                  )}
                </div>
              </SectionCard>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-[10px] border border-line bg-surface/50 p-5">
        <div className="micro mb-3">How to read the numbers</div>
        <div className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
          {GLOSSARY.map(([term, def]) => (
            <div key={term} className="text-[12.5px] leading-relaxed">
              <span className="font-medium text-ink">{term}</span>{" "}
              <span className="text-muted">— {def}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
