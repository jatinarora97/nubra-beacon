import { get } from "@/lib/api";
import { Badge, EmptyState, PageHeader, SectionCard } from "@/components/ui";

export const dynamic = "force-dynamic";

type Person = {
  email: string;
  visits: number;
  active_days: number;
  first_seen: string;
  last_seen: string;
  sources_added: number;
  access_decisions: number;
  keys_minted: number;
};

function ist(ts: string | null | undefined): string {
  if (!ts) return "–";
  return new Date(ts).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  });
}

function actions(p: Person): string {
  const bits = [
    p.sources_added ? `${p.sources_added} source${p.sources_added !== 1 ? "s" : ""} added` : null,
    p.access_decisions ? `${p.access_decisions} access decision${p.access_decisions !== 1 ? "s" : ""}` : null,
    p.keys_minted ? `${p.keys_minted} API key${p.keys_minted !== 1 ? "s" : ""} minted` : null,
  ].filter(Boolean);
  return bits.length ? bits.join(" · ") : "–";
}

export default async function TeamActivityPage() {
  const r = await get<{ days: number; people: Person[] } | null>(
    "/team-activity?days=30", null);
  const people = r?.people ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Team activity"
        accent="bg-muted"
        blurb="Who uses Beacon and what they do with it, from Google sign-ins over the last 30 days. A visit is a session (activity gaps over 30 minutes start a new one), not a click count. Actions cover the attributed ones: sources added, access decisions, API keys minted."
      />

      {people.length === 0 ? (
        <EmptyState
          title="No sign-ins recorded yet"
          body="Tracking starts from the release that shipped this page — as teammates log in through Google, they appear here."
        />
      ) : (
        <SectionCard>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px]">
              <thead className="bg-surface2/70">
                <tr className="text-left">
                  {["person", "visits (30d)", "active days", "last seen", "first seen", "actions"].map((h) => (
                    <th key={h} className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {people.map((p) => (
                  <tr key={p.email}>
                    <td className="px-3 py-2.5 text-[12.5px]">
                      <span className="mr-2">{p.email}</span>
                      {p.visits > 0 && <Badge>active</Badge>}
                    </td>
                    <td className="px-3 py-2.5 text-[12.5px] tabular-nums">{p.visits}</td>
                    <td className="px-3 py-2.5 text-[12.5px] tabular-nums">{p.active_days}</td>
                    <td className="px-3 py-2.5 text-[11.5px] tabular-nums text-muted">{ist(p.last_seen)}</td>
                    <td className="px-3 py-2.5 text-[11.5px] tabular-nums text-muted">{ist(p.first_seen)}</td>
                    <td className="px-3 py-2.5 text-[12px] text-muted">{actions(p)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </div>
  );
}
