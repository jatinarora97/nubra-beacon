import { get } from "@/lib/api";
import type { SourceHealth } from "@/lib/types";
import { Badge, EmptyState, PageHeader, SectionCard } from "@/components/ui";

export const dynamic = "force-dynamic";

const LABELS: Record<string, string> = {
  twitter: "X / Twitter",
  reddit: "Reddit",
  youtube: "YouTube",
  github: "GitHub",
  broker_communities: "Broker communities",
  app_reviews: "App reviews",
};

function statusTone(status: string): "opps" | "warn" | "danger" | "muted" {
  if (status === "working") return "opps";
  if (status === "error") return "danger";
  if (status === "needs_key") return "warn";
  return "muted";
}

function timestamp(value?: string | null): string {
  if (!value) return "Not run yet";
  return new Date(value).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  });
}

export default async function SourceHealthPage() {
  const payload = await get<{ sources: SourceHealth[] }>("/source-health", { sources: [] });
  const sources = payload.sources;

  return (
    <div>
      <PageHeader
        title="Source health"
        blurb="Collection readiness and last-run status for every Beacon source. A failed optional source is isolated and does not stop the remaining pipeline."
        accent="bg-muted"
      />

      {sources.length === 0 ? (
        <EmptyState
          title="Source health is unavailable"
          body="The API may still be starting. Existing dashboard pages continue to work."
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {sources.map((source) => (
            <SectionCard key={source.name}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-[15px] font-semibold">
                    {LABELS[source.name] ?? source.name}
                  </h2>
                  <p className="mt-1 text-[12px] text-muted">
                    Stored as <span className="font-mono">{source.stored_source}</span>
                  </p>
                </div>
                <Badge tone={statusTone(source.health)}>
                  {source.health.replace(/_/g, " ")}
                </Badge>
              </div>

              <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 text-[12.5px]">
                <div>
                  <dt className="text-muted">Stored records</dt>
                  <dd className="mt-0.5 font-medium tabular-nums">{source.stored_items}</dd>
                </div>
                <div>
                  <dt className="text-muted">Last run collected</dt>
                  <dd className="mt-0.5 font-medium tabular-nums">
                    {source.items_last_run ?? "—"}
                  </dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-muted">Last successful run</dt>
                  <dd className="mt-0.5 font-medium">{timestamp(source.last_success_at)}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-muted">Credentials</dt>
                  <dd className="mt-0.5 font-medium">
                    {source.credential.replace(/_/g, " ")}
                    {source.required_key ? ` · ${source.required_key}` : ""}
                    {source.optional_key ? ` · optional ${source.optional_key}` : ""}
                  </dd>
                </div>
              </dl>

              {source.last_error && (
                <div className="mt-4 rounded-md border border-danger/30 bg-danger/5 p-3 text-[12px] leading-relaxed text-danger">
                  {source.last_error}
                </div>
              )}
            </SectionCard>
          ))}
        </div>
      )}
    </div>
  );
}
