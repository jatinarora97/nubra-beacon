"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, EmptyState, SectionCard } from "@/components/ui";
import { apiBase, post } from "@/lib/api";
import type { CatalogFeature, FeaturesCatalog } from "@/lib/types";

const inputCls =
  "w-full rounded-[10px] border border-line bg-surface2 px-3 py-2 text-[13px] text-ink outline-none focus:border-warn";

export function GroundingEditor() {
  const [catalog, setCatalog] = useState<FeaturesCatalog | null>(null);
  const [rows, setRows] = useState<CatalogFeature[]>([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase()}/features-catalog`, { cache: "no-store" });
      if (res.ok) {
        const d: FeaturesCatalog = await res.json();
        setCatalog(d);
        setRows(d.features.map((f) => ({ ...f, seo_keywords: f.seo_keywords ?? [] })));
        setDirty(false);
      }
    } catch {
      /* banner handles backend-down */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  function edit(i: number, patch: Partial<CatalogFeature>) {
    setRows((r) => r.map((f, j) => (j === i ? { ...f, ...patch } : f)));
    setDirty(true);
  }

  function addRow() {
    setRows((r) => [
      ...r,
      { feature: "", description: "", status: "upcoming", category: "custom", seo_keywords: [] },
    ]);
    setDirty(true);
  }

  function removeRow(i: number) {
    setRows((r) => r.filter((_, j) => j !== i));
    setDirty(true);
  }

  async function publish() {
    if (busy) return;
    setBusy(true);
    const r = await post("/features-catalog", { features: rows });
    setBusy(false);
    if (r.ok) {
      setMsg("Published — the next draft run grounds on this version.");
      refresh();
    } else {
      setMsg(r.detail ?? "Publish failed.");
    }
    setTimeout(() => setMsg(null), 6000);
  }

  if (!catalog) {
    return <EmptyState title="Loading catalog" body="Fetching the current grounding version." />;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-[12.5px] text-muted">
        <span>
          current version <span className="font-medium text-ink">{catalog.version}</span>
        </span>
        {catalog.published_at && (
          <span>
            published{" "}
            {new Date(catalog.published_at).toLocaleString("en-IN", {
              day: "2-digit",
              month: "short",
              hour: "2-digit",
              minute: "2-digit",
              timeZone: "Asia/Kolkata",
            })}{" "}
            IST
          </span>
        )}
        {catalog.version?.startsWith("assumed") && (
          <Badge tone="warn">engineering-assumed — awaiting marketing&apos;s vetted catalog</Badge>
        )}
      </div>

      <div className="space-y-3">
        {rows.map((f, i) => (
          <SectionCard key={i}>
            <div className="grid gap-3 lg:grid-cols-12">
              <div className="lg:col-span-3">
                <div className="micro mb-1.5">feature</div>
                <input
                  value={f.feature}
                  onChange={(e) => edit(i, { feature: e.target.value })}
                  placeholder="e.g. Flexi Orders"
                  className={inputCls}
                />
              </div>
              <div className="lg:col-span-5">
                <div className="micro mb-1.5">what we can claim</div>
                <textarea
                  value={f.description}
                  onChange={(e) => edit(i, { description: e.target.value })}
                  rows={2}
                  className={`${inputCls} resize-y`}
                />
              </div>
              <div className="lg:col-span-3">
                <div className="micro mb-1.5">keywords (comma-separated)</div>
                <input
                  value={(f.seo_keywords ?? []).join(", ")}
                  onChange={(e) =>
                    edit(i, {
                      seo_keywords: e.target.value.split(",").map((k) => k.trim()).filter(Boolean),
                    })
                  }
                  className={inputCls}
                />
              </div>
              <div className="flex flex-col items-end justify-between lg:col-span-1">
                <button
                  onClick={() => edit(i, { status: f.status === "live" ? "upcoming" : "live" })}
                  className={`rounded-md border px-2.5 py-1 text-[11.5px] font-medium transition-colors ${
                    f.status === "live"
                      ? "border-opps/40 text-opps"
                      : "border-warn/40 text-warn"
                  }`}
                  title="Toggle live / upcoming"
                >
                  {f.status}
                </button>
                <button
                  onClick={() => removeRow(i)}
                  className="rounded-md border border-line px-2.5 py-1 text-[11.5px] text-muted transition-colors hover:border-danger hover:text-danger"
                >
                  Remove
                </button>
              </div>
            </div>
          </SectionCard>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={addRow}
          className="rounded-[10px] border border-line bg-surface2 px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:border-warn"
        >
          Add feature
        </button>
        <button
          onClick={publish}
          disabled={!dirty || busy}
          className="rounded-[10px] border border-warn/50 bg-warn/10 px-4 py-2 text-[13px] font-semibold text-warn transition-colors hover:bg-warn/20 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "Publishing…" : "Publish as new version"}
        </button>
        <span className="text-[12px] text-muted">
          {dirty
            ? "Unpublished edits — publishing creates the next version; drafts pick it up on the next run."
            : "No pending edits."}
        </span>
        {msg && <span className="text-[12px] text-ink">{msg}</span>}
      </div>
    </div>
  );
}
