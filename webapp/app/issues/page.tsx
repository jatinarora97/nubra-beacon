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
  const rows = await get<Issue[]>("/issues", []);
  const brokers = [...new Set(rows.map((r) => r.broker))];
  const issueKeys = [...new Set(rows.map((r) => r.issue_key))];
  const cell = (b: string, k: string) =>
    rows.find((r) => r.broker === b && r.issue_key === k);
  const maxCount = Math.max(...rows.map((r) => r.count), 1);

  return (
    <div>
      <PageHeader
        title="Broker issues"
        accent="bg-danger"
        blurb="What traders complain about, per broker. No minimum bar here — a single high-severity complaint is worth knowing about. Severity blends reach with how negative the sentiment is."
      />

      {rows.length === 0 ? (
        <EmptyState
          title="No broker complaints in the window"
          body="Complaints are extracted from posts where the intent is a complaint and a broker is explicitly identified."
        />
      ) : (
        <div className="space-y-5">
          <SectionCard>
            <div className="micro mb-4">
              complaints by broker × issue type · cell intensity = volume · label = severity
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
                      <td className="pr-2 text-[13px] font-medium">{b}</td>
                      {issueKeys.map((k) => {
                        const c = cell(b, k);
                        if (!c)
                          return (
                            <td key={k} className="h-11 rounded bg-surface2/40" />
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
            <div className="micro mb-3">what people actually said</div>
            <div className="space-y-2">
              {rows
                .filter((r) => (r.samples?.length ?? 0) > 0)
                .map((r) => (
                  <Expandable
                    key={`${r.broker}-${r.issue_key}`}
                    summary={
                      <span className="flex items-center gap-2">
                        <Badge tone="danger">{r.broker}</Badge>
                        <span className="text-[13px]">{r.issue_key.replace(/_/g, " ")}</span>
                        <span className="text-[11.5px] text-muted">
                          {r.count} complaint{r.count !== 1 ? "s" : ""}
                        </span>
                      </span>
                    }
                  >
                    <div className="space-y-2 pl-1">
                      {r.samples!.map((s, i) => (
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
                      ))}
                    </div>
                  </Expandable>
                ))}
            </div>
          </SectionCard>
        </div>
      )}
    </div>
  );
}
