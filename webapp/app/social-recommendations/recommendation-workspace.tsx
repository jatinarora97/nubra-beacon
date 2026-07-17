"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiBase } from "@/lib/api";
import type {
  SocialRecommendation,
  SocialRecommendationPreview,
  SocialRecommendationStatus,
} from "@/lib/types";
import { Badge, EmptyState, KpiCard, SectionCard } from "@/components/ui";
import { CopyButton } from "@/components/client";

type Segment = "all" | "retail" | "api";

const button =
  "rounded-[9px] border border-line bg-surface2 px-3 py-1.5 text-[12px] font-semibold text-muted transition-colors hover:border-content/50 hover:text-ink disabled:cursor-not-allowed disabled:opacity-40";

export function RecommendationWorkspace({
  initial,
  moduleStatus,
  preview,
}: {
  initial: SocialRecommendation[];
  moduleStatus: SocialRecommendationStatus;
  preview: SocialRecommendationPreview;
}) {
  const router = useRouter();
  const [rows, setRows] = useState(initial);
  const [segment, setSegment] = useState<Segment>("all");
  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const shown = useMemo(
    () => rows.filter((row) => segment === "all" || row.segment === segment),
    [rows, segment],
  );
  const context = moduleStatus.context;
  const latest = moduleStatus.latest_run;

  async function generate() {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(`${apiBase()}/social-recommendations/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ days }),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        setMessage(result.detail ?? result.error ?? "Generation did not complete.");
      } else {
        setMessage(`Generated ${result.recommendations} recommendations.`);
        router.refresh();
      }
    } catch {
      setMessage("Social recommendations are unavailable. Other Beacon pages are unaffected.");
    }
    setBusy(false);
  }

  function updateLocal(id: number, update: Partial<SocialRecommendation>) {
    setRows((current) => current.map((row) => (row.id === id ? { ...row, ...update } : row)));
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="context features" value={context?.feature_count ?? "—"} hint={context?.version} />
        <KpiCard label="live capabilities" value={context?.live_features ?? "—"} />
        <KpiCard label="upcoming capabilities" value={context?.upcoming_features ?? "—"} />
        <KpiCard
          label="latest generation"
          value={latest?.status ?? "not run"}
          hint={latest ? `${latest.window_days} day evidence window` : "Generate when Claude is configured"}
        />
      </div>

      <SectionCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-[14px] font-semibold">Evidence and Nubra context available</div>
            <p className="mt-1 max-w-2xl text-[12.5px] leading-relaxed text-muted">
              {preview.items ?? 0} eligible items from the last 30 days:
              {" "}{preview.retail_items ?? 0} retail and {preview.api_items ?? 0} API.
              The generator selects the relevant subset from every available source,
              then grounds claims against {preview.context_features ?? context?.feature_count ?? 0} Nubra capabilities.
            </p>
          </div>
          <Badge tone={preview.claude_configured ? "opps" : "warn"}>
            Claude {preview.claude_configured ? "configured" : "not configured"}
          </Badge>
        </div>
        {(preview.sources?.length ?? 0) > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {preview.sources!.map((source) => (
              <Badge key={source}>{source.replaceAll("_", " ")}</Badge>
            ))}
          </div>
        )}
      </SectionCard>

      <SectionCard>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[14px] font-semibold">Generate from latest evidence</div>
            <p className="mt-1 text-[12.5px] text-muted">
              Uses the existing Beacon Claude key. Results are stored and do not regenerate on page refresh.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={days}
              onChange={(event) => setDays(Number(event.target.value))}
              className="rounded-[9px] border border-line bg-surface2 px-3 py-1.5 text-[12px] text-ink"
              aria-label="Evidence window"
            >
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </select>
            <button className={button} onClick={generate} disabled={busy}>
              {busy ? "Generating…" : "Generate latest"}
            </button>
          </div>
        </div>
        {latest?.error && (
          <p className="mt-3 rounded-md border border-warn/30 bg-warn/5 p-2 text-[12px] text-warn">
            Last run: {latest.error}
          </p>
        )}
        {message && <p className="mt-3 text-[12.5px] text-muted">{message}</p>}
      </SectionCard>

      <div className="flex flex-wrap gap-2">
        {(["all", "retail", "api"] as Segment[]).map((value) => (
          <button
            key={value}
            onClick={() => setSegment(value)}
            className={`${button} ${segment === value ? "border-content/60 text-content" : ""}`}
          >
            {value === "all" ? "All recommendations" : value === "api" ? "API" : "Retail"}
          </button>
        ))}
      </div>

      {!moduleStatus.ready ? (
        <EmptyState
          title="Social recommendation module is not ready"
          body="Apply the latest database migration and restart the API. Existing Beacon pages continue to work independently."
        />
      ) : shown.length === 0 ? (
        <EmptyState
          title="No stored recommendations yet"
          body="Generate the first set after Beacon has collected data and the Anthropic key is configured. A failed generation does not affect any other section."
        />
      ) : (
        <div className="space-y-4">
          {shown.map((recommendation) => (
            <RecommendationCard
              key={recommendation.id}
              recommendation={recommendation}
              onChange={(update) => updateLocal(recommendation.id, update)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function RecommendationCard({
  recommendation,
  onChange,
}: {
  recommendation: SocialRecommendation;
  onChange: (update: Partial<SocialRecommendation>) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [copy, setCopy] = useState(recommendation.exact_copy);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function setStatus(status: "approved" | "rejected" | "published") {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `${apiBase()}/social-recommendations/${recommendation.id}/status`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        },
      );
      const result = await response.json();
      if (!response.ok) setError(result.detail ?? "Status update failed.");
      else onChange({ status });
    } catch {
      setError("Backend unreachable.");
    }
    setBusy(false);
  }

  async function saveCopy() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `${apiBase()}/social-recommendations/${recommendation.id}/edit`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ exact_copy: copy }),
        },
      );
      const result = await response.json();
      if (!response.ok) setError(
        typeof result.detail === "string" ? result.detail : "Edited copy failed compliance.",
      );
      else {
        onChange({ exact_copy: copy });
        setEditing(false);
      }
    } catch {
      setError("Backend unreachable.");
    }
    setBusy(false);
  }

  return (
    <SectionCard>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={recommendation.segment === "api" ? "voices" : "content"}>
              {recommendation.segment === "api" ? "API" : "Retail"}
            </Badge>
            <Badge>{recommendation.platform}</Badge>
            <Badge>{recommendation.post_format.replaceAll("_", " ")}</Badge>
            <Badge tone={recommendation.status === "approved" ? "opps" : "muted"}>
              {recommendation.status}
            </Badge>
          </div>
          <h2 className="mt-2 text-[16px] font-semibold">{recommendation.title}</h2>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[12px] text-muted">
            priority {Math.round(Number(recommendation.priority_score))}
          </span>
          <CopyButton text={recommendation.exact_copy} label="Copy post" />
        </div>
      </div>

      {editing ? (
        <div className="mt-4">
          <textarea
            value={copy}
            onChange={(event) => setCopy(event.target.value)}
            rows={12}
            className="w-full resize-y rounded-[10px] border border-line bg-surface2 p-3 text-[13.5px] leading-relaxed text-ink outline-none focus:border-content"
          />
          <div className="mt-2 flex gap-2">
            <button className={button} onClick={saveCopy} disabled={busy}>Save after compliance check</button>
            <button className={button} onClick={() => { setCopy(recommendation.exact_copy); setEditing(false); }}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-4 whitespace-pre-wrap rounded-[10px] border border-content/25 bg-content/5 p-4 text-[13.5px] leading-6">
          {recommendation.exact_copy}
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        <button className={button} onClick={() => setEditing(true)} disabled={busy}>Edit</button>
        <button className={button} onClick={() => setStatus("approved")} disabled={busy}>Approve</button>
        <button className={button} onClick={() => setStatus("rejected")} disabled={busy}>Reject</button>
        {recommendation.status === "approved" && (
          <button className={button} onClick={() => setStatus("published")} disabled={busy}>Mark published</button>
        )}
      </div>
      {error && <p className="mt-2 text-[12px] text-danger">{error}</p>}

      <details className="mt-4 border-t border-line pt-3">
        <summary className="cursor-pointer text-[12.5px] font-semibold text-muted">
          Why this recommendation and what supports it
        </summary>
        <div className="mt-3 grid gap-4 text-[12.5px] leading-relaxed lg:grid-cols-2">
          <div>
            <div className="micro mb-1">reason</div>
            <p>{recommendation.rationale}</p>
            <div className="micro mt-4 mb-1">visual direction</div>
            <p>{recommendation.visual_brief}</p>
            {recommendation.recommended_timing && (
              <>
                <div className="micro mt-4 mb-1">timing</div>
                <p>{recommendation.recommended_timing}</p>
              </>
            )}
          </div>
          <div>
            <div className="micro mb-2">Nubra feature grounding</div>
            <div className="space-y-2">
              {recommendation.mapped_features.map((feature) => (
                <div key={feature.id} className="rounded-md border border-line bg-surface2/40 p-2">
                  <div className="font-medium">{feature.name}</div>
                  <div className="mt-0.5 text-muted">
                    {feature.status === "live" ? "Available" : "Upcoming"}
                  </div>
                </div>
              ))}
            </div>
            <div className="micro mt-4 mb-2">supporting evidence</div>
            <div className="space-y-2">
              {recommendation.source_evidence.map((item) => (
                <div key={item.item_id} className="rounded-md border border-line p-2">
                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
                    {item.source}
                  </div>
                  <p>{item.text.slice(0, 300)}{item.text.length > 300 ? "…" : ""}</p>
                  {item.url && (
                    <a href={item.url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-trends">
                      View source
                    </a>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </details>
    </SectionCard>
  );
}
