import { get } from "@/lib/api";
import type { Proposal } from "@/lib/types";
import { EmptyState, PageHeader } from "@/components/ui";
import { ProposalCard } from "./proposal-card";

export const dynamic = "force-dynamic";

export default async function ContentPage() {
  const [rows, taxonomy] = await Promise.all([
    get<Proposal[]>("/content-proposals", []),
    get<{ platforms: string[] }>("/content-taxonomy", { platforms: [] }),
  ]);
  const sorted = [...rows].sort((a, b) => a.rank - b.rank);

  return (
    <div>
      <PageHeader
        title="Content briefs"
        accent="bg-content"
        blurb="Creator-ready briefs riding today's community signal — ranked, capped at three, each targeted at the platform where it will land best. Hand a card to a creator and they can execute without questions. Edit any card directly, or tell Beacon what to change — revisions re-check compliance and keep history."
      />

      {sorted.length === 0 ? (
        <EmptyState
          title="No briefs for today yet"
          body="Briefs are generated with the daily build from the day's rising topics, issues and feature requests, then pass the compliance gate. Ideas that fail the gate are dropped, so some days ship fewer than three."
        />
      ) : (
        <div className="space-y-4">
          {sorted.map((c) => (
            <ProposalCard key={`${c.day}-${c.rank}`} initial={c} platforms={taxonomy.platforms} />
          ))}
        </div>
      )}
    </div>
  );
}
