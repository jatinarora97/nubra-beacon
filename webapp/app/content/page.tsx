import { get } from "@/lib/api";
import type { Proposal } from "@/lib/types";
import { EmptyState, PageHeader } from "@/components/ui";
import { ProposalCard } from "./proposal-card";
import { DayPicker } from "./day-picker";

export const dynamic = "force-dynamic";

export default async function ContentPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const date = typeof sp.date === "string" ? sp.date : undefined;
  const [rows, taxonomy, days] = await Promise.all([
    get<Proposal[]>(`/content-proposals${date ? `?date=${date}` : ""}`, []),
    get<{ platforms: string[] }>("/content-taxonomy", { platforms: [] }),
    get<{ day: string; briefs: number }[]>("/content-proposals/days", []),
  ]);
  const sorted = [...rows].sort((a, b) => a.rank - b.rank);
  const activeDay = date ?? sorted[0]?.day ?? days[0]?.day ?? "";

  return (
    <div>
      <PageHeader
        title="Content briefs"
        accent="bg-content"
        blurb="Creator-ready briefs riding the day's community signal — ranked, capped at three, each targeted at the platform where it will land best. Briefs regenerate each morning; use the day picker to revisit earlier sets. Edit any card directly, or tell Beacon what to change — revisions re-check compliance and keep history."
      />

      <DayPicker days={days} active={activeDay} />

      {sorted.length === 0 ? (
        <EmptyState
          title={date ? `No briefs on ${date}` : "No briefs for today yet"}
          body="Briefs are generated with the daily build from the day's rising topics, issues and feature requests, then pass the compliance gate. Ideas that fail the gate are dropped — and days before the system went live have none. Pick another day above."
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
