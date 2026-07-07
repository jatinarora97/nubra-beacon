import { get } from "@/lib/api";
import type { Issue } from "@/lib/types";
import { Badge, EmptyState, PageHeader, SectionCard } from "@/components/ui";
import { Expandable } from "@/components/client";

function sevTone(s?: number | null): { label: string; cls: string } {
  if (s == null) return { label: "n/a", cls: "text-muted" };
  if (s >= 7) return { label: "high", cls: "text-danger" };
  if (s >= 4) return { label: "medium", cls: "text-warn" };
  return { label: "low", cls: "text-muted" };
}

export default async function IssuesPage() {
  const data = await get<{ segments: Issue[]; brokers: string[] }>("/issues", {
    segments: [],
    brokers: [],
  });
  const rows = data.segments;
  // Every watched broker gets a row — a clean row (green zeros) is signal too.
  // Order: Nubra first, then by complaint volume, then alphabetical.
  const volume = new Map<string, number>();
  for (const r of rows) volume.set(r.broker, (volume.get(r.broker) ?? 0) + r.count);
  const brokers = [...new Set([...data.brokers, ...rows.map((r) => r.broker)])].sort(
    (a, b) =>
      Number(b === "nubra") - Number(a === "nubra") ||
      (volume.get(b) ?? 0) - (volume.get(a) ?? 0) ||
      a.localeCompare(b),
  );
  // Columns are data-driven: top 5 issue types by total complaint volume.
  const issueTotals = new Map<string, number>();
  for (const r of rows)
    issueTotals.set(r.issue_key, (issueTotals.get(r.issue_key) ?? 0) + r.count);
  const issueKeys = [...issueTotals.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([k]) => k);
  const clippedIssueTypes = issueTotals.size - issueKeys.length;
  const cell = (b: string, k: string) =>
    rows.find((r) => r.broker === b && r.issue_key === k);
  const maxCount = Math.max(...rows.map((r) => r.count), 1);

  return (
    <div>
      <PageHeader
        title="Broker issues"
        accent="bg-danger"
        blurb="What traders complain about, across every broker we watch — including Nubra, tracked with the same machinery (the positive side lives on Nubra mentions). A green zero means no complaints in the window. No minimum bar — a single high-severity complaint is worth knowing about. Severity blends reach with how negative the sentiment is."
      />

      {rows.length === 0 ? (
        <EmptyState
          title="No complaints in the window"
          body={`All ${brokers.length} watched brokers are clean this window. Complaints are extracted from posts where the intent is a complaint and a broker is explicitly identified.`}
        />
      ) : (
        <div className="space-y-5">
          <SectionCard>
            <div className="micro mb-4">
              complaints by broker × issue type · cell intensity = volume · label = severity
              {clippedIssueTypes > 0 &&
                ` · top 5 issue types shown (${clippedIssueTypes} more below)`}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full border-separate border-spacing-1">
                <thead>
                  <tr>
                    <th className="w-32 text-left text-[11.5px] font-medium text-muted">
                      broker
                    </th>
                    {issueKeys.map((k) => (
                      <th
                        key={k}
                        className="px-1 pb-1 text-center text-[11px] font-medium text-muted"
                      >
                        {k.replace(/_/g, " ")}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {brokers.map((b) => (
                    <tr key={b}>
                      <td className={`pr-2 text-[13px] font-medium ${b === "nubra" ? "text-opps" : ""}`}>
                        {b}
                        {b === "nubra" && <span className="ml-1.5 text-[10px] text-muted">(us)</span>}
                      </td>
                      {issueKeys.map((k) => {
                        const c = cell(b, k);
                        if (!c)
                          return (
                            <td
                              key={k}
                              className="h-11 min-w-20 rounded bg-opps/10 text-center align-middle"
                              title={`${b} · ${k.replace(/_/g, " ")}: no complaints in the window`}
                            >
                              <span className="text-[12.5px] font-medium tabular-nums text-opps">0</span>
                            </td>
                          );
                        const alpha = 0.25 + 0.6 * (c.count / maxCount);
                        const sev = sevTone(c.severity);
                        return (
                          <td
                            key={k}
                            className="h-11 min-w-20 rounded text-center align-middle"
                            style={{ background: `rgba(239,68,68,${alpha * 0.45})` }}
                            title={`${b} · ${k}: ${c.count} complaint(s), severity ${c.severity?.toFixed(1) ?? "n/a"}`}
                          >
                            <div className="text-[13px] font-semibold tabular-nums">
                              {c.count}
                            </div>
                            <div className={`text-[10px] ${sev.cls}`}>{sev.label}</div>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex gap-4 border-t border-line pt-3 text-[11.5px] text-muted">
              <span>severity: <span className="text-danger">high ≥7</span></span>
              <span><span className="text-warn">medium 4-7</span></span>
              <span>low &lt;4</span>
              <span className="ml-auto">
                severity = log(reach) × share of strongly-negative items
              </span>
            </div>
          </SectionCard>

          <SectionCard>
            <div className="mb-3 flex items-baseline gap-2">
              <span className="micro">what people actually said</span>
              <span className="text-[11.5px] font-normal normal-case tracking-normal text-muted/70">
                — every broker × issue segment; click one to expand the quotes
              </span>
            </div>
            <div className="space-y-2">
              {rows.map((r) => {
                const sev = sevTone(r.severity);
                return (
                  <Expandable
                    key={`${r.broker}-${r.issue_key}`}
                    summary={
                      <span className="flex items-center gap-2">
                        <Badge tone="danger">{r.broker}</Badge>
                        <span className="text-[13px]">{r.issue_key.replace(/_/g, " ")}</span>
                        <span className="text-[11.5px] text-muted">
                          {r.count} complaint{r.count !== 1 ? "s" : ""} · severity{" "}
                          <span className={sev.cls}>
                            {sev.label}
                            {r.severity != null && ` (${r.severity.toFixed(1)})`}
                          </span>
                        </span>
                      </span>
                    }
                  >
                    <div className="space-y-2 pl-1">
                      {(r.samples?.length ?? 0) === 0 ? (
                        <p className="text-[12.5px] text-muted">
                          No sample quotes captured for this segment — inspect the raw
                          items on the Explore page.
                        </p>
                      ) : (
                        r.samples!.map((s, i) => (
                          <blockquote
                            key={i}
                            className="border-l-2 border-line pl-3 text-[12.5px] leading-relaxed text-muted"
                          >
                            “{s.text}”
                            {s.url && (
                              <a
                                href={s.url}
                                target="_blank"
                                className="ml-2 text-trends hover:underline"
                              >
                                view thread
                              </a>
                            )}
                          </blockquote>
                        ))
                      )}
                    </div>
                  </Expandable>
                );
              })}
            </div>
          </SectionCard>
        </div>
      )}
    </div>
  );
}
