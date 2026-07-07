import Link from "next/link";
import { get } from "@/lib/api";
import type { NubraMentions } from "@/lib/types";
import { Badge, EmptyState, KpiCard, PageHeader, SectionCard } from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function NubraPage() {
  const data = await get<NubraMentions>("/nubra-mentions", { window_days: 7 });
  const k = data.kpis ?? {};
  const positives = data.positives ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Nubra mentions"
        accent="bg-opps"
        blurb={`What people say about Nubra — the positive and neutral side: praise, organic recommendations, honest questions. Complaints are tracked with the same machinery as every competitor and appear on the Broker issues page. Window: last ${data.window_days} days.`}
      />

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard label="Mentions 24h" value={k.mentions_24h ?? 0} />
        <KpiCard label={`Mentions ${data.window_days}d`} value={k.mentions_window ?? 0} />
        <KpiCard
          label="Positive share"
          value={k.positive_share != null ? `${Math.round(k.positive_share * 100)}%` : "–"}
          hint="of window mentions with non-negative sentiment"
        />
        <KpiCard
          label={`Complaints ${data.window_days}d`}
          value={k.complaints_window ?? 0}
          hint="rendered on Broker issues"
        />
      </section>

      {positives.length === 0 ? (
        <EmptyState
          title="No Nubra mentions captured yet"
          body="Beacon watches for Nubra across everything it collects, on every source. Mentions appear here the moment they are picked up."
        />
      ) : (
        <SectionCard>
          <div className="micro mb-3">in their words — most positive first</div>
          <div className="space-y-3">
            {positives.map((p) => (
              <blockquote
                key={`${p.source}-${p.external_id}`}
                className="border-l-2 border-opps/50 pl-3"
              >
                <p className="text-[13px] leading-relaxed">“{p.text}”</p>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-[11.5px] text-muted">
                  <Badge>{p.source}</Badge>
                  {p.intent && <Badge>{p.intent.replace(/_/g, " ")}</Badge>}
                  {p.sentiment != null && (
                    <span>sentiment {p.sentiment > 0 ? "+" : ""}{p.sentiment.toFixed(2)}</span>
                  )}
                  {p.author && <span>@{p.author}</span>}
                  {p.created_at && (
                    <span>
                      {new Date(p.created_at).toLocaleDateString("en-IN", {
                        day: "2-digit",
                        month: "short",
                        timeZone: "Asia/Kolkata",
                      })}
                    </span>
                  )}
                  {p.url && (
                    <a href={p.url} target="_blank" className="text-trends hover:underline">
                      view thread
                    </a>
                  )}
                </div>
              </blockquote>
            ))}
          </div>
        </SectionCard>
      )}

      <p className="text-[12.5px] text-muted">
        Looking for the negative side?{" "}
        <Link href="/issues" className="text-danger hover:underline">
          Broker issues
        </Link>{" "}
        includes Nubra as a watched broker — complaints about us surface there with
        the same severity scoring as competitors.
      </p>
    </div>
  );
}
