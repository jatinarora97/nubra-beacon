"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, SectionCard } from "@/components/ui";
import { apiBase, post } from "@/lib/api";

type FeedbackRow = {
  id: number;
  object_ref: { context?: string } | null;
  category: string;
  free_text: string | null;
  submitted_by: string;
  ts: string;
};

/** Manual feature-request intake — writes to the feedback table (category
 *  feature_request). Community-sourced asks above are measured; these are
 *  team-logged inputs (support calls, DMs, meetings) kept alongside them. */
export function RequestIntake() {
  const [rows, setRows] = useState<FeedbackRow[]>([]);
  const [text, setText] = useState("");
  const [context, setContext] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase()}/feedback?category=feature_request`, {
        cache: "no-store",
      });
      if (res.ok) setRows(await res.json());
    } catch {
      /* soft-fail like the rest of the app */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function submit() {
    if (!text.trim() || busy) return;
    setBusy(true);
    const r = await post("/feedback", {
      object_ref: { type: "manual", via: "features_page", context: context.trim() || undefined },
      category: "feature_request",
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
    "rounded-[10px] border border-line bg-surface2 px-3 py-2 text-[13px] text-ink outline-none focus:border-warn";

  return (
    <SectionCard className="mb-6">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-[13px] font-semibold uppercase tracking-wider text-muted">
          Log a request heard elsewhere
        </h2>
        <span className="text-[11.5px] text-muted">
          support calls, DMs, meetings — anything not on X/Reddit
        </span>
      </div>
      <div className="mt-3 flex flex-wrap items-start gap-3">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="The ask, in the user's words if possible"
          rows={2}
          className={`${inputCls} min-w-64 flex-1 resize-y`}
        />
        <input
          value={context}
          onChange={(e) => setContext(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Where it came from (optional)"
          className={`${inputCls} w-64`}
        />
        <button
          onClick={submit}
          disabled={busy || !text.trim()}
          className="rounded-[10px] border border-line bg-surface2 px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:border-warn disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? "Logging…" : "Log request"}
        </button>
        {msg && <span className="self-center text-[12.5px] text-muted">{msg}</span>}
      </div>

      {rows.length > 0 && (
        <div className="mt-4 divide-y divide-line border-t border-line">
          {rows.map((r) => (
            <div key={r.id} className="flex items-baseline gap-3 py-2">
              <p className="min-w-0 flex-1 text-[13px] leading-relaxed">{r.free_text}</p>
              {r.object_ref?.context && <Badge>{r.object_ref.context}</Badge>}
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
      )}
    </SectionCard>
  );
}
