"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiBase, get, post } from "@/lib/api";
import { Badge, EmptyState, SectionCard, StatInline } from "@/components/ui";
import { CopyButton } from "@/components/client";
import {
  CONTENT_PLATFORMS,
  CONTENT_PLATFORM_LABELS,
  type ContentBrief,
} from "../lens";

type Tab = "draft" | "published" | "rejected";

const TABS: { key: Tab; label: string }[] = [
  { key: "draft", label: "Ready" },
  { key: "published", label: "Acted" },
  { key: "rejected", label: "Dismissed" },
];

const subtleBtn =
  "rounded-[9px] border border-line bg-surface2 px-3 py-1.5 text-[12px] font-semibold text-muted transition-colors hover:border-content/50 hover:text-ink disabled:cursor-not-allowed disabled:opacity-40";
const primaryBtn =
  "rounded-[9px] border border-content/50 bg-content/10 px-3 py-1.5 text-[12px] font-semibold text-content transition-colors hover:bg-content/20 disabled:cursor-not-allowed disabled:opacity-40";
const inputCls =
  "rounded-[10px] border border-line bg-surface2 px-3 py-1.5 text-[12.5px] text-ink outline-none focus:border-content";

function platformLabel(p: string): string {
  return CONTENT_PLATFORM_LABELS[p] ?? p.replace(/_/g, " ");
}

function fmtDay(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    timeZone: "Asia/Kolkata",
  });
}

function BriefCard({
  brief,
  readOnly,
  onTransition,
}: {
  brief: ContentBrief;
  readOnly: boolean;
  onTransition: (brief: ContentBrief, action: "act" | "dismiss", note: string) => void;
}) {
  const [mode, setMode] = useState<null | "act" | "dismiss">(null);
  const [note, setNote] = useState("");

  const isSeed = brief.post_format === "seed_reply";
  const seedEvidence =
    brief.source_evidence?.find((e) => e.url && e.url === brief.seed_url) ??
    brief.source_evidence?.[0];

  return (
    <SectionCard>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="content">{platformLabel(brief.platform)}</Badge>
        <Badge tone={isSeed ? "warn" : "muted"}>
          {isSeed ? "seed reply" : "standalone"}
        </Badge>
        <span className="text-[11.5px] tabular-nums text-muted">
          priority {Math.round(Number(brief.priority_score ?? 0))}
        </span>
        {readOnly && (
          <>
            <Badge tone={brief.status === "published" ? "opps" : "danger"}>
              {brief.status === "published" ? "acted" : "dismissed"}
            </Badge>
            <span className="text-[11.5px] text-muted">{fmtDay(brief.day)}</span>
          </>
        )}
        <div className="ml-auto">
          <CopyButton text={brief.exact_copy} label="Copy" />
        </div>
      </div>

      <div className="micro mt-2.5">{brief.title}</div>

      <pre className="mt-2 max-h-96 overflow-y-auto whitespace-pre-wrap rounded-[10px] border border-content/25 bg-content/5 p-4 font-mono text-[12.5px] leading-relaxed">
        {brief.exact_copy}
      </pre>

      {brief.seed_url && (
        <div className="mt-3 rounded-[10px] border border-warn/30 bg-warn/5 p-3">
          <a
            href={brief.seed_url}
            target="_blank"
            rel="noreferrer"
            className="text-[13px] font-semibold text-warn hover:underline"
          >
            Target thread — post this reply there
          </a>
          {seedEvidence?.gist && (
            <p className="mt-1 text-[12px] leading-relaxed text-muted">
              {seedEvidence.gist}
            </p>
          )}
        </div>
      )}

      {(brief.mapped_features?.length ?? 0) > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {brief.mapped_features!.map((f) => (
            <Badge key={f.name}>{f.name}</Badge>
          ))}
        </div>
      )}

      {brief.recommended_timing && (
        <div className="micro mt-2.5">{brief.recommended_timing}</div>
      )}

      {brief.rationale && (
        <details className="mt-3 border-t border-line pt-2.5">
          <summary className="cursor-pointer text-[12.5px] font-semibold text-muted">
            Why this
          </summary>
          <p className="mt-2 max-w-3xl text-[12.5px] leading-relaxed">
            {brief.rationale}
          </p>
        </details>
      )}

      {!readOnly &&
        (mode === null ? (
          <div className="mt-3 flex gap-2">
            <button className={primaryBtn} onClick={() => setMode("act")}>
              Acted
            </button>
            <button className={subtleBtn} onClick={() => setMode("dismiss")}>
              Dismiss
            </button>
          </div>
        ) : (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={
                mode === "act" ? "link to your post (optional)" : "reason (optional)"
              }
              className={`${inputCls} min-w-64 flex-1`}
            />
            <button
              className={mode === "act" ? primaryBtn : subtleBtn}
              onClick={() => onTransition(brief, mode, note)}
            >
              {mode === "act" ? "Mark acted" : "Confirm dismiss"}
            </button>
            <button
              className={subtleBtn}
              onClick={() => {
                setMode(null);
                setNote("");
              }}
            >
              Cancel
            </button>
          </div>
        ))}
    </SectionCard>
  );
}

export function ContentQueue() {
  const [rows, setRows] = useState<ContentBrief[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("draft");
  const [platform, setPlatform] = useState<string>("all");
  const [topping, setTopping] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const d = await get<ContentBrief[] | null>(
      "/api-trading/content?status=all&limit=200",
      null,
    );
    setRows(d);
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  function flash(text: string) {
    setMsg(text);
    setTimeout(() => setMsg(null), 5000);
  }

  async function transition(
    brief: ContentBrief,
    action: "act" | "dismiss",
    note: string,
  ) {
    const target = action === "act" ? "published" : "rejected";
    const prev = brief.status;
    // Optimistic: move the card out of Ready now, revert if the POST fails.
    setRows((cur) =>
      cur?.map((r) => (r.id === brief.id ? { ...r, status: target } : r)) ?? cur,
    );
    const trimmed = note.trim();
    const r = await post(
      `/api-trading/content/${brief.id}/${action}`,
      trimmed ? { note: trimmed } : {},
    );
    if (!r.ok) {
      setRows((cur) =>
        cur?.map((x) => (x.id === brief.id ? { ...x, status: prev } : x)) ?? cur,
      );
      flash(r.detail ?? `Update failed (${r.status || "backend unreachable"}).`);
      if (r.status === 409) refresh(); // someone else moved it — resync
    }
  }

  async function topUp() {
    setTopping(true);
    try {
      const res = await fetch(`${apiBase()}/api-trading/content/top-up`, {
        method: "POST",
      });
      const j = await res.json().catch(() => null);
      if (!res.ok) {
        flash(
          typeof j?.detail === "string" ? j.detail : `Top-up failed (${res.status}).`,
        );
      } else {
        const ready = j?.ready
          ? Object.entries(j.ready as Record<string, number>)
              .map(([p, n]) => `${platformLabel(p)} ${n}`)
              .join(", ")
          : "";
        flash(
          `Top-up: ${j?.status ?? "done"}` +
            (j?.stored ? `, stored ${j.stored}` : "") +
            (ready ? ` — ready: ${ready}` : ""),
        );
        await refresh();
      }
    } catch {
      flash("Top-up failed: backend unreachable.");
    }
    setTopping(false);
  }

  const readyCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of rows ?? []) {
      if (r.status === "draft") counts[r.platform] = (counts[r.platform] ?? 0) + 1;
    }
    return counts;
  }, [rows]);

  const shown = useMemo(
    () =>
      (rows ?? []).filter(
        (r) => r.status === tab && (platform === "all" || r.platform === platform),
      ),
    [rows, tab, platform],
  );

  const groups = useMemo(() => {
    const order: string[] = [...CONTENT_PLATFORMS];
    for (const r of shown) if (!order.includes(r.platform)) order.push(r.platform);
    return order
      .map((p) => ({ platform: p, briefs: shown.filter((r) => r.platform === p) }))
      .filter((g) => g.briefs.length > 0);
  }, [shown]);

  const chipCls = (active: boolean) =>
    `rounded-md border px-3 py-1 text-[12.5px] font-medium transition-colors ${
      active
        ? "border-content/50 bg-content/10 text-content"
        : "border-line text-muted hover:border-muted hover:text-ink"
    }`;

  return (
    <div className="space-y-4">
      {/* ── ready counts + top-up ──────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="micro">ready to post</span>
        {CONTENT_PLATFORMS.map((p) => (
          <StatInline key={p} label={platformLabel(p)} value={readyCounts[p] ?? 0} />
        ))}
        <div className="ml-auto flex items-center gap-3">
          {msg && <span className="text-[12px] text-warn">{msg}</span>}
          <button className={subtleBtn} onClick={topUp} disabled={topping}>
            {topping ? "Topping up…" : "Top up now"}
          </button>
        </div>
      </div>

      {/* ── status tabs ────────────────────────────────────────────────── */}
      <div className="flex gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
              tab === t.key
                ? "border-content text-ink"
                : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── platform filter ────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-1.5">
        <button className={chipCls(platform === "all")} onClick={() => setPlatform("all")}>
          All
        </button>
        {CONTENT_PLATFORMS.map((p) => (
          <button key={p} className={chipCls(platform === p)} onClick={() => setPlatform(p)}>
            {platformLabel(p)}
          </button>
        ))}
      </div>

      {/* ── grouped cards ──────────────────────────────────────────────── */}
      {loading || rows === null ? (
        <EmptyState
          title={loading ? "Loading content queue" : "Content queue unavailable"}
          body={
            loading
              ? "Fetching ready-to-post briefs."
              : "The read-API did not answer — check the backend banner."
          }
        />
      ) : shown.length === 0 ? (
        <EmptyState
          title={tab === "draft" ? "Nothing ready right now" : "Nothing here yet"}
          body={
            tab === "draft"
              ? "Queue is stocked hourly — check back or press Top up now."
              : "Briefs land here once someone marks them from the Ready tab. Queue is stocked hourly — check back or press Top up now."
          }
        />
      ) : (
        groups.map((g) => (
          <div key={g.platform}>
            <div className="micro mb-2">
              {platformLabel(g.platform)} · {g.briefs.length}
            </div>
            <div className="space-y-4">
              {g.briefs.map((b) => (
                <BriefCard
                  key={b.id}
                  brief={b}
                  readOnly={tab !== "draft"}
                  onTransition={transition}
                />
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
