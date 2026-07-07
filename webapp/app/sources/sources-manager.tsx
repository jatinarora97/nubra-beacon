"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, EmptyState, SectionCard } from "@/components/ui";
import { apiBase } from "@/lib/api";

type Source = {
  id: number;
  kind: "subreddit" | "x_hashtag" | "x_handle" | "x_query" | "keyword";
  value: string;
  category: string | null;
  active: boolean;
  added_by: string;
  note: string | null;
  config?: { x?: boolean; reddit?: boolean } | null;
};

const KIND_META: Record<Source["kind"], { label: string; prefix: string; hint: string }> = {
  subreddit: { label: "Subreddits", prefix: "r/", hint: "e.g. IndianStreetBets" },
  x_hashtag: { label: "X hashtags", prefix: "#", hint: "e.g. BankNifty" },
  x_handle: { label: "X handles", prefix: "@", hint: "e.g. zerodhaonline" },
  x_query: { label: "X search queries", prefix: "", hint: "full advanced-search query" },
  keyword: { label: "Keywords", prefix: "", hint: "topic to watch, e.g. basket orders" },
};

export function SourcesManager() {
  const [sources, setSources] = useState<Source[]>([]);
  const [kind, setKind] = useState<Source["kind"]>("subreddit");
  const [value, setValue] = useState("");
  const [category, setCategory] = useState("custom");
  const [kwX, setKwX] = useState(true);
  const [kwReddit, setKwReddit] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase()}/sources`, { cache: "no-store" });
      if (res.ok) setSources(await res.json());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function add() {
    if (!value.trim()) return;
    const body: Record<string, unknown> = { kind, value, category };
    if (kind === "keyword") body.config = { x: kwX, reddit: kwReddit };
    const res = await fetch(`${apiBase()}/sources`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      setValue("");
      setMsg(`Added — picked up on the next scrape run.`);
      refresh();
    } else {
      const d = await res.json().catch(() => ({}));
      setMsg(d.detail ?? "Could not add that source.");
    }
    setTimeout(() => setMsg(null), 4000);
  }

  async function toggle(id: number) {
    await fetch(`${apiBase()}/sources/${id}/toggle`, { method: "POST" });
    refresh();
  }

  async function remove(id: number) {
    await fetch(`${apiBase()}/sources/${id}`, { method: "DELETE" });
    refresh();
  }

  const inputCls =
    "rounded-[10px] border border-line bg-surface2 px-3 py-2 text-[13px] text-ink outline-none focus:border-trends";

  return (
    <div className="space-y-6">
      <SectionCard>
        <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wider text-muted">Add a source</h2>
        <div className="flex flex-wrap items-center gap-3">
          <select value={kind} onChange={(e) => setKind(e.target.value as Source["kind"])} className={inputCls}>
            {Object.entries(KIND_META).map(([k, m]) => (
              <option key={k} value={k}>
                {m.label.replace(/s$/, "")}
              </option>
            ))}
          </select>
          <div className="flex items-center gap-1">
            <span className="text-[13px] text-muted">{KIND_META[kind].prefix}</span>
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && add()}
              placeholder={KIND_META[kind].hint}
              className={`${inputCls} w-72`}
            />
          </div>
          <select value={category} onChange={(e) => setCategory(e.target.value)} className={inputCls}>
            {["custom", "brokers", "market_trading", "investing_pf", "fno_algo"].map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
          {kind === "keyword" && (
            <span className="flex items-center gap-3 text-[12.5px] text-muted">
              watch on:
              <label className="flex cursor-pointer items-center gap-1.5">
                <input type="checkbox" checked={kwX} onChange={(e) => setKwX(e.target.checked)} />
                X search
              </label>
              <label className="flex cursor-pointer items-center gap-1.5">
                <input type="checkbox" checked={kwReddit} onChange={(e) => setKwReddit(e.target.checked)} />
                Reddit lens
              </label>
            </span>
          )}
          <button
            onClick={add}
            className="rounded-[10px] border border-line bg-surface2 px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:border-trends"
          >
            Add source
          </button>
          {msg && <span className="text-[12.5px] text-muted">{msg}</span>}
        </div>
      </SectionCard>

      {loading ? (
        <EmptyState title="Loading sources" body="Fetching the current collection config." />
      ) : (
        (Object.keys(KIND_META) as Source["kind"][]).map((k) => {
          const rows = sources.filter((s) => s.kind === k);
          return (
            <SectionCard key={k}>
              <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wider text-muted">
                {KIND_META[k].label} ({rows.filter((r) => r.active).length} active)
              </h2>
              {rows.length === 0 ? (
                <p className="text-[12.5px] text-muted">None yet — add one above.</p>
              ) : (
                <div className="divide-y divide-line">
                  {rows.map((s) => (
                    <div key={s.id} className="flex items-center gap-3 py-2">
                      <span className={`text-[13px] ${s.active ? "text-ink" : "text-muted line-through"}`}>
                        {KIND_META[s.kind].prefix}
                        {s.value}
                      </span>
                      {s.category && <Badge>{s.category}</Badge>}
                      {s.kind === "keyword" && s.config?.x && <Badge tone="trends">X search</Badge>}
                      {s.kind === "keyword" && s.config?.reddit && <Badge tone="voices">Reddit lens</Badge>}
                      {s.kind === "keyword" && (
                        <a
                          href={`/explore?q=${encodeURIComponent(s.value)}`}
                          className="rounded-md border border-line px-2 py-0.5 text-[11px] text-muted transition-colors hover:border-trends hover:text-ink"
                          title="Open Explore filtered to items matching this keyword"
                        >
                          see matches
                        </a>
                      )}
                      {s.added_by === "discovery" && <Badge tone="warn">suggested</Badge>}
                      {s.note && <span className="text-[11.5px] text-muted">{s.note}</span>}
                      <div className="ml-auto flex items-center gap-2">
                        <button
                          onClick={() => toggle(s.id)}
                          className="rounded-md border border-line px-2.5 py-1 text-[11.5px] text-muted transition-colors hover:border-trends hover:text-ink"
                        >
                          {s.active ? "Pause" : "Activate"}
                        </button>
                        <button
                          onClick={() => remove(s.id)}
                          className="rounded-md border border-line px-2.5 py-1 text-[11.5px] text-muted transition-colors hover:border-danger hover:text-danger"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </SectionCard>
          );
        })
      )}
    </div>
  );
}
