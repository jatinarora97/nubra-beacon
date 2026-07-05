"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, EmptyState, SectionCard } from "@/components/ui";
import { apiBase, post } from "@/lib/api";

type FeedbackRow = {
  id: number;
  object_ref: { context?: string } | null;
  category: string;
  free_text: string | null;
  submitted_by: string;
  ts: string;
};

/** Beacon improvement requests — team asks for new sections/capabilities in
 *  THIS dashboard. Writes to the feedback table (category ui_feature_request);
 *  distinct from /features, which is measured community signal about Nubra. */
export function RequestIntake() {
  const [rows, setRows] = useState<FeedbackRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [text, setText] = useState("");
  const [context, setContext] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase()}/feedback?category=ui_feature_request`, {
        cache: "no-store",
      });
      if (res.ok) setRows(await res.json());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function submit() {
    if (!text.trim() || busy) return;
    setBusy(true);
    const r = await post("/feedback", {
      object_ref: { type: "manual", via: "requests_page", context: context.trim() || undefined },
      category: "ui_feature_request",
      free_text: text.trim(),
    });
    setBusy(false);
    if (r.ok) {
      setText("");
      setContext("");
      setMsg("Logged.");
      refresh();
    } else {
      setMsg(r.detail ?? "Could not log the request.");
    }
    setTimeout(() => setMsg(null), 4000);
  }

  const inputCls =
    "rounded-[10px] border border-line bg-surface2 px-3 py-2 text-[13px] text-ink outline-none focus:border-content";

  return (
    <div className="space-y-6">
      <SectionCard>
        <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wider text-muted">
          Request a Beacon feature
        </h2>
        <div className="flex flex-wrap items-start gap-3">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="The section, view or capability you want (e.g. a weekly roundup page, export to CSV, alerts on a topic)"
            rows={2}
            className={`${inputCls} min-w-72 flex-1 resize-y`}
          />
          <input
            value={context}
            onChange={(e) => setContext(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Why / what it unblocks (optional)"
            className={`${inputCls} w-64`}
          />
          <button
            onClick={submit}
            disabled={busy || !text.trim()}
            className="rounded-[10px] border border-line bg-surface2 px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:border-content disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Logging…" : "Log request"}
          </button>
          {msg && <span className="self-center text-[12.5px] text-muted">{msg}</span>}
        </div>
      </SectionCard>

      {loading ? (
        <EmptyState title="Loading requests" body="Fetching what the team has asked for so far." />
      ) : rows.length === 0 ? (
        <EmptyState
          title="Nothing logged yet"
          body="Anything you wish this dashboard did — a missing section, a view, an export — log it above and it lands on the build backlog."
        />
      ) : (
        <SectionCard>
          <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wider text-muted">
            Logged so far ({rows.length})
          </h2>
          <div className="divide-y divide-line">
            {rows.map((r) => (
              <div key={r.id} className="flex items-baseline gap-3 py-2.5">
                <p className="min-w-0 flex-1 text-[13px] leading-relaxed">{r.free_text}</p>
                {r.object_ref?.context && <Badge tone="content">{r.object_ref.context}</Badge>}
                <span className="shrink-0 text-[11.5px] text-muted">
                  {r.submitted_by} ·{" "}
                  {new Date(r.ts).toLocaleDateString("en-IN", {
                    day: "2-digit",
                    month: "short",
                    timeZone: "Asia/Kolkata",
                  })}
                </span>
              </div>
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  );
}
