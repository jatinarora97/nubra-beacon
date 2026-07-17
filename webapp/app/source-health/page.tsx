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

export default async function SourceHealthPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const live = sp.live === "1";
  const payload = await get<{ sources: SourceHealth[] }>(
    `/source-health${live ? "?live=true" : ""}`,
    { sources: [] },
  );
  const sources = payload.sources;

  return (
    <div>
      <PageHeader
        title="Source health"
        blurb="Collection readiness and last-run status for every Beacon source, with on-demand live probes that hit each API right now. A failed optional source is isolated and does not stop the remaining pipeline."
        accent="bg-opps"
      />

      <div className="mb-5">
        <a
          href={live ? "/source-health" : "/source-health?live=1"}
          className={`rounded-md border px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
            live
              ? "border-opps/50 bg-opps/10 text-opps"
              : "border-line text-muted hover:border-opps hover:text-ink"
          }`}
        >
          {live ? "Live check complete — refresh to re-run" : "Run live checks (hits every API now)"}
        </a>
      </div>

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
                <span className="flex shrink-0 items-center gap-1.5">
                  <Badge tone={statusTone(source.health)}>
                    {source.health.replace(/_/g, " ")}
                  </Badge>
                  {source.live && (
                    <Badge tone={source.live === "ok" ? "opps" : "danger"}>
                      live: {source.live}{source.detail ? ` · ${source.detail}` : ""}
                    </Badge>
                  )}
                </span>
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
