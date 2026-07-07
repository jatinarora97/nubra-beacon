"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, SectionCard } from "@/components/ui";
import { apiBase } from "@/lib/api";

type Suggestion = {
  topic_key: string;
  label: string;
  why: string | null;
  item_count: number | null;
};

/** Emergent themes HDBSCAN found in `other:*` chatter — suggested taxonomy
 *  rows awaiting a human decision. Renders nothing until suggestions exist
 *  (and soft-fails to hidden if the endpoint is absent). */
export function TopicSuggestions() {
  const [rows, setRows] = useState<Suggestion[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase()}/topic-suggestions`, { cache: "no-store" });
      if (res.ok) setRows(await res.json());
    } catch {
      /* hidden until the API serves it */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function decide(key: string, action: "activate" | "reject") {
    const res = await fetch(`${apiBase()}/topic-suggestions/${key}/${action}`, {
      method: "POST",
    });
    if (res.ok) {
      setMsg(
        action === "activate"
          ? "Activated — the topic joins the taxonomy on the next enrichment run."
          : "Dismissed — this cluster will not be re-suggested.",
      );
      refresh();
    } else {
      setMsg("Could not update the suggestion.");
    }
    setTimeout(() => setMsg(null), 4000);
  }

  if (rows.length === 0 && !msg) return null;
  return (
    <SectionCard className="mt-5">
      <div className="mb-3 flex items-baseline gap-2">
        <span className="micro">Emerging themes Beacon noticed</span>
        <span className="text-[11.5px] text-muted">
          — clustered from unclassified chatter; they start tracking only after you activate them
        </span>
      </div>
      {msg && <p className="mb-3 text-[12.5px] text-muted">{msg}</p>}
      <div className="space-y-2.5">
        {rows.map((s) => (
          <div key={s.topic_key} className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[13.5px] font-medium">{s.label}</span>
                {s.item_count != null && (
                  <Badge tone="trends">{s.item_count} items</Badge>
                )}
              </div>
              {s.why && (
                <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted">{s.why}</p>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                onClick={() => decide(s.topic_key, "activate")}
                className="rounded-md border border-line px-2.5 py-1 text-[11.5px] text-muted transition-colors hover:border-opps hover:text-opps"
              >
                Activate
              </button>
              <button
                onClick={() => decide(s.topic_key, "reject")}
                className="rounded-md border border-line px-2.5 py-1 text-[11.5px] text-muted transition-colors hover:border-danger hover:text-danger"
              >
                Dismiss
              </button>
            </div>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}
