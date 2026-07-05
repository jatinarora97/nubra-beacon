import Link from "next/link";
import { get } from "@/lib/api";
import type { Opportunity } from "@/lib/types";
import { EmptyState, PageHeader } from "@/components/ui";
import { OpportunityCard } from "./opportunity-card";

export default async function OpportunitiesPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status = "suggested" } = await searchParams;
  const rows = await get<Opportunity[]>(
    `/opportunities?status=${encodeURIComponent(status)}&limit=25`,
    [],
  );
  const sorted = [...rows].sort((a, b) => b.priority - a.priority);

  return (
    <div>
      <PageHeader
        title="Opportunities"
        accent="bg-opps"
        blurb="Conversations worth joining, ranked by a 0-100 relevance score. Every card explains why it's worth engaging and carries pre-gated brand and rep drafts — copy, adapt, post. Low-engagement threads never rank top."
      />

      <div className="mb-4 flex gap-1.5">
        {["suggested", "acted", "dismissed"].map((s) => (
          <Link
            key={s}
            href={`/opportunities?status=${s}`}
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
          title={`No ${status} opportunities`}
          body="New opportunities appear after each hourly scoring pass when a conversation crosses the relevance bar."
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
