"use client";

import { useCallback, useEffect, useState } from "react";
import { del, get, post } from "@/lib/api";
import { Badge, EmptyState, SectionCard } from "@/components/ui";
import type { LandscapeFeature, LandscapeResp } from "../lens";

const STATUS_ORDER = ["shipped", "upcoming", "rumored"] as const;
const STATUS_TONE: Record<string, "opps" | "warn" | "muted"> = {
  shipped: "opps",
  upcoming: "warn",
  rumored: "muted",
};

const inputCls =
  "rounded-[10px] border border-line bg-surface2 px-3 py-2 text-[13px] text-ink outline-none focus:border-warn";

function fmtDate(iso?: string | null): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    timeZone: "Asia/Kolkata",
  });
}

function FeatureRow({
  f,
  onDelete,
}: {
  f: LandscapeFeature;
  onDelete: (f: LandscapeFeature) => void;
}) {
  return (
    <div className="flex items-center gap-2 py-1.5">
      <div className="min-w-0 flex-1 truncate text-[12.5px]" title={f.notes ?? undefined}>
        {f.feature}
        {f.notes && <span className="ml-1.5 text-[11.5px] text-muted">— {f.notes}</span>}
      </div>
      {f.evidence_url && (
        <a
          href={f.evidence_url}
          target="_blank"
          className="shrink-0 text-[11.5px] text-trends hover:underline"
        >
          evidence
        </a>
      )}
      <Badge tone={f.added_by === "auto" ? "muted" : "voices"}>
        {f.added_by === "auto" ? "auto" : f.added_by}
      </Badge>
      <span className="w-16 shrink-0 text-right text-[11px] tabular-nums text-muted">
        {fmtDate(f.last_seen)}
      </span>
      <button
        onClick={() => onDelete(f)}
        title={`Delete "${f.feature}"`}
        className="shrink-0 rounded-md border border-line px-1.5 text-[12px] leading-5 text-muted transition-colors hover:border-danger/50 hover:text-danger"
      >
        ×
      </button>
    </div>
  );
}

function FeatureCatalog({
  competitor,
  features,
  onDelete,
}: {
  competitor: string;
  features: LandscapeFeature[];
  onDelete: (f: LandscapeFeature) => void;
}) {
  return (
    <div>
      <div className="mb-1.5 text-[13px] font-semibold">{competitor}</div>
      {features.length === 0 ? (
        <div className="text-[12px] text-muted">
          No features tracked yet — the weekly monitor or a manual add below fills this in.
        </div>
      ) : (
        STATUS_ORDER.filter((s) => features.some((f) => f.status === s)).map((s) => (
          <div key={s} className="mb-2">
            <div className="mb-0.5 flex items-center gap-2">
              <Badge tone={STATUS_TONE[s]}>{s}</Badge>
            </div>
            <div className="divide-y divide-line/60">
              {features
                .filter((f) => f.status === s)
                .map((f) => (
                  <FeatureRow key={f.id} f={f} onDelete={onDelete} />
                ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

export function LandscapeManager({ days }: { days: number }) {
  const [data, setData] = useState<LandscapeResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);

  // add form
  const [competitor, setCompetitor] = useState("");
  const [feature, setFeature] = useState("");
  const [status, setStatus] = useState("shipped");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const d = await get<LandscapeResp | null>(`/api-trading/landscape?days=${days}`, null);
    setData(d);
    setLoading(false);
  }, [days]);

  useEffect(() => {
    setLoading(true);
    refresh();
  }, [refresh]);

  function flash(text: string) {
    setMsg(text);
    setTimeout(() => setMsg(null), 4000);
  }

  async function add() {
    if (!competitor.trim() || !feature.trim() || busy) return;
    setBusy(true);
    const r = await post("/api-trading/landscape", {
      competitor: competitor.trim(),
      feature: feature.trim(),
      status,
      evidence_url: evidenceUrl.trim() || null,
      notes: notes.trim() || null,
    });
    setBusy(false);
    if (r.ok) {
      setFeature("");
      setEvidenceUrl("");
      setNotes("");
      flash("Added. Same competitor + feature updates the existing row.");
      refresh();
    } else {
      flash(r.detail ?? "Could not add that feature.");
    }
  }

  async function remove(f: LandscapeFeature) {
    if (!window.confirm(`Delete "${f.feature}" (${f.competitor})?`)) return;
    const r = await del(`/api-trading/landscape/${f.id}`);
    if (!r.ok) flash(r.detail ?? "Delete failed.");
    refresh();
  }

  if (loading || !data) {
    return (
      <EmptyState
        title={loading ? "Loading landscape" : "Landscape unavailable"}
        body={
          loading
            ? "Fetching coverage and the feature catalog."
            : "The read-API did not answer — check the backend banner."
        }
      />
    );
  }

  const knownPlayers = data.players.map((p) => p.name);
  const untracked = Object.entries(data.untracked_features);

  return (
    <div className="space-y-5">
      {/* ── coverage strip ─────────────────────────────────────────────── */}
      <div>
        <div className="micro mb-2">coverage in the window</div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          {data.players.map((p) => (
            <div key={p.name} className="rounded-[10px] border border-line bg-surface px-3.5 py-2.5">
              <div className="truncate text-[12.5px] font-semibold" title={p.name}>
                {p.name}
              </div>
              <div className="mt-1 flex items-baseline gap-3 text-[11.5px] tabular-nums text-muted">
                <span title="all corpus mentions">
                  <span className="font-medium text-ink">{p.corpus.toLocaleString("en-IN")}</span> corpus
                </span>
                <span title="items relevant to the API-trader lens">
                  <span className="font-medium text-ink">{p.relevant}</span> lens
                </span>
                <span title="lens items that are frictions">
                  <span className="font-medium text-danger">{p.frictions}</span> friction
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── feature catalog ────────────────────────────────────────────── */}
      <SectionCard>
        <div className="mb-1 flex items-baseline justify-between gap-3">
          <div className="text-[13.5px] font-semibold">Feature catalog</div>
          <span className="text-[11px] text-muted">
            rows added by &quot;auto&quot; refresh weekly from each player&apos;s public docs
          </span>
        </div>
        <p className="mb-4 text-[12px] leading-relaxed text-muted">
          What each competitor ships for API traders, grouped by status. Delete removes a
          row permanently; the weekly monitor re-adds anything still on the public pages.
        </p>
        <div className="grid gap-x-8 gap-y-5 lg:grid-cols-2">
          {data.players.map((p) => (
            <FeatureCatalog
              key={p.name}
              competitor={p.name}
              features={p.features}
              onDelete={remove}
            />
          ))}
          {untracked.map(([name, feats]) => (
            <FeatureCatalog key={name} competitor={`${name} (untracked)`} features={feats} onDelete={remove} />
          ))}
        </div>
        {untracked.length > 0 && (
          <div className="mt-3 border-t border-line pt-2.5 text-[11.5px] text-muted">
            &quot;Untracked&quot; competitors have manual feature rows but no mention
            patterns in the roster, so they get no coverage numbers.
          </div>
        )}
      </SectionCard>

      {/* ── manual add ─────────────────────────────────────────────────── */}
      <SectionCard>
        <div className="mb-3 text-[13.5px] font-semibold">Add a feature manually</div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            list="landscape-players"
            value={competitor}
            onChange={(e) => setCompetitor(e.target.value)}
            placeholder="competitor"
            className={`${inputCls} w-44`}
          />
          <datalist id="landscape-players">
            {knownPlayers.map((n) => (
              <option key={n} value={n} />
            ))}
          </datalist>
          <input
            value={feature}
            onChange={(e) => setFeature(e.target.value)}
            placeholder="feature, e.g. WebSocket order updates"
            className={`${inputCls} min-w-56 flex-1`}
          />
          <select value={status} onChange={(e) => setStatus(e.target.value)} className={inputCls}>
            {STATUS_ORDER.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <input
            value={evidenceUrl}
            onChange={(e) => setEvidenceUrl(e.target.value)}
            placeholder="evidence URL (optional)"
            className={`${inputCls} w-64`}
          />
          <input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="notes (optional)"
            className={`${inputCls} min-w-40 flex-1`}
          />
          <button
            onClick={add}
            disabled={busy || !competitor.trim() || !feature.trim()}
            className="rounded-[10px] border border-line bg-surface2 px-4 py-2 text-[13px] font-medium transition-colors hover:border-warn hover:text-warn disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Adding…" : "Add feature"}
          </button>
        </div>
        {msg && <div className="mt-2.5 text-[12.5px] text-warn">{msg}</div>}
      </SectionCard>
    </div>
  );
}
