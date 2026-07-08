import Link from "next/link";
import { get } from "@/lib/api";
import type { Opportunity } from "@/lib/types";
import { EmptyState, PageHeader } from "@/components/ui";
import { TimeFilter } from "@/components/time-filter";
import { pickWindow, windowLabel, windowQuery } from "@/lib/window";
import { OpportunityCard } from "./opportunity-card";

export default async function OpportunitiesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const status = (Array.isArray(sp.status) ? sp.status[0] : sp.status) ?? "suggested";
  const w = pickWindow(sp);
  const qs = windowQuery(w);
  const rows = await get<Opportunity[]>(
    `/opportunities?status=${encodeURIComponent(status)}&limit=50&${qs}`,
    [],
  );
  const sorted = [...rows].sort((a, b) => b.priority - a.priority);
  // status tabs keep the active window; window chips keep the active status
  const tabQs = (s: string) => `status=${s}&${qs}`;

  return (
    <div>
      <PageHeader
        title="Opportunities"
        accent="bg-opps"
        blurb="Conversations worth joining, ranked by a 0-100 relevance score. Every card explains why it's worth engaging and carries pre-gated brand and rep drafts — copy, adapt, post. Low-engagement threads never rank top."
      />

      <TimeFilter current={w} extra={{ status }} />

      <div className="mb-4 flex gap-1.5">
        {["suggested", "acted", "dismissed"].map((s) => (
          <Link
            key={s}
            href={`/opportunities?${tabQs(s)}`}
            className={`rounded-md border px-3 py-1 text-[12.5px] font-medium ${
              s === status
                ? "border-opps/50 bg-opps/10 text-opps"
                : "border-line text-muted hover:text-ink"
            }`}
          >
            {s}
          </Link>
        ))}
      </div>

      {sorted.length === 0 ? (
        <EmptyState
          title={`No ${status} opportunities in ${windowLabel(w)}`}
          body="New opportunities appear after each hourly scoring pass when a conversation crosses the relevance bar. Widen the window above to look further back."
        />
      ) : (
        <div className="space-y-3">
          {sorted.map((o, i) => (
            <OpportunityCard key={o.id} opp={o} rank={i + 1} />
          ))}
        </div>
      )}
    </div>
  );
}
