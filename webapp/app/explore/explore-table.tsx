"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { get } from "@/lib/api";
import type { Item } from "@/lib/types";
import { Badge, EmptyState } from "@/components/ui";
import { pickWindow, windowQuery } from "@/lib/window";

const PAGE = 50;

const INTENTS = ["", "complaint", "feature_request", "question", "praise",
  "comparison", "how_to", "news_opinion", "spam"];

function interactions(it: Item): number {
  const n = it.engagement?.native ?? {};
  return (n.likes ?? 0) + (n.upvotes ?? 0) + (n.replies ?? 0) +
    (n.comments ?? 0) + (n.retweets ?? 0) + (n.quotes ?? 0);
}

export function ExploreTable() {
  // ?q= deep-links (e.g. keyword chips on the Sources page) seed the search box;
  // window/from_ts/to_ts come from the TimeFilter above the table.
  const sp = useSearchParams();
  const initialQ = sp.get("q") ?? "";
  const windowQS = windowQuery(
    pickWindow({
      window: sp.get("window") ?? undefined,
      from_ts: sp.get("from_ts") ?? undefined,
      to_ts: sp.get("to_ts") ?? undefined,
    }),
  );
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [source, setSource] = useState("");
  const [intent, setIntent] = useState("");
  const [q, setQ] = useState(initialQ);
  const [qLive, setQLive] = useState(initialQ);
  const [detail, setDetail] = useState<Item | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setQ(qLive), 350);
    return () => clearTimeout(t);
  }, [qLive]);

  function pageUrl(off: number): string {
    const params = new URLSearchParams({
      sort: "engagement",
      limit: String(PAGE),
      offset: String(off),
    });
    if (source) params.set("source", source);
    if (intent) params.set("intent", intent);
    if (q) params.set("q", q);
    return `/items?${params}&${windowQS}`;
  }

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setOffset(0);
    get<Item[]>(pageUrl(0), []).then((rows) => {
      if (alive) {
        setItems(rows);
        setHasMore(rows.length === PAGE);
        setLoading(false);
      }
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, intent, q, windowQS]);

  async function loadMore() {
    if (loadingMore) return;
    setLoadingMore(true);
    const next = offset + PAGE;
    const rows = await get<Item[]>(pageUrl(next), []);
    setItems((prev) => [...prev, ...rows]);
    setOffset(next);
    setHasMore(rows.length === PAGE);
    setLoadingMore(false);
  }

  const sorted = useMemo(
    () => [...items].sort((a, b) => interactions(b) - interactions(a)),
    [items],
  );

  // Server-side export honouring the active filters + window (full text).
  function exportUrl(format: "csv" | "xlsx"): string {
    const params = new URLSearchParams({ sort: "engagement", limit: "2000", format });
    if (source) params.set("source", source);
    if (intent) params.set("intent", intent);
    if (q) params.set("q", q);
    return `/api/v1/items/export?${params}&${windowQS}`;
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-[12.5px]"
        >
          <option value="">all sources</option>
          <option value="twitter">twitter / X</option>
          <option value="reddit">reddit</option>
        </select>
        <select
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-[12.5px]"
        >
          {INTENTS.map((i) => (
            <option key={i} value={i}>
              {i === "" ? "all intents" : i.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <input
          value={qLive}
          onChange={(e) => setQLive(e.target.value)}
          placeholder="search text…"
          className="min-w-56 flex-1 rounded-md border border-line bg-surface px-3 py-1.5 text-[12.5px] placeholder:text-muted/60"
        />
        <span className="text-[11.5px] text-muted">
          sorted by engagement · snapshot at fetch
        </span>
        <div className="ml-auto flex items-center gap-2">
          {(["csv", "xlsx"] as const).map((fmt) => (
            <a
              key={fmt}
              href={exportUrl(fmt)}
              download
              title={`Download the current filter result (up to 2,000 rows, full text) as ${fmt === "csv" ? "CSV" : "Excel"}`}
              className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-[12px] font-medium text-muted transition-colors hover:border-muted hover:text-ink"
            >
              Export {fmt === "csv" ? "CSV" : "Excel"}
            </a>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="py-16 text-center text-[13px] text-muted">loading…</div>
      ) : sorted.length === 0 ? (
        <EmptyState
          title="No items match in this window"
          body="Loosen the filters or widen the time window above — or Beacon genuinely hasn't seen matching items yet."
        />
      ) : (
        <div className="overflow-hidden rounded-[10px] border border-line">
          <table className="w-full">
            <thead className="bg-surface2/70">
              <tr className="text-left">
                {["what was said", "source", "intent", "engagement", "fetched"].map((h) => (
                  <th key={h} className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-surface">
              {sorted.map((it) => (
                <tr
                  key={`${it.source}-${it.external_id}`}
                  onClick={() => setDetail(it)}
                  className="cursor-pointer transition-colors hover:bg-surface2/50"
                >
                  <td className="max-w-md truncate px-3 py-2.5 text-[12.5px]">
                    {it.text}
                  </td>
                  <td className="px-3 py-2.5">
                    <Badge>{it.source}</Badge>
                  </td>
                  <td className="px-3 py-2.5 text-[12px] text-muted">
                    {it.intent?.replace(/_/g, " ") ?? "–"}
                  </td>
                  <td className="px-3 py-2.5 text-[12.5px] tabular-nums">
                    {interactions(it)}
                  </td>
                  <td className="px-3 py-2.5 text-[11.5px] tabular-nums text-muted">
                    {it.ingested_at
                      ? new Date(it.ingested_at).toLocaleString("en-IN", {
                          day: "2-digit",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                          timeZone: "Asia/Kolkata",
                        })
                      : "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && hasMore && (
        <div className="mt-4 text-center">
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="rounded-[10px] border border-line bg-surface px-4 py-2 text-[12.5px] font-medium text-muted transition-colors hover:border-muted hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loadingMore ? "Loading…" : `Load ${PAGE} more`}
          </button>
        </div>
      )}

      {detail && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/50"
          onClick={() => setDetail(null)}
        >
          <div
            className="h-full w-full max-w-lg overflow-y-auto border-l border-line bg-surface p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <div className="micro">item detail</div>
              <button
                onClick={() => setDetail(null)}
                className="rounded-md border border-line px-2.5 py-1 text-[12px] text-muted hover:text-ink"
              >
                close
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge>{detail.source}</Badge>
              {detail.intent && <Badge>{detail.intent.replace(/_/g, " ")}</Badge>}
              {detail.topic_key && <Badge tone="trends">{detail.topic_key}</Badge>}
              {(detail.duplicate_count ?? 0) > 0 && (
                <Badge tone="warn">{detail.duplicate_count} duplicates linked</Badge>
              )}
            </div>
            <p className="mt-4 whitespace-pre-wrap text-[13.5px] leading-relaxed">
              {detail.text}
            </p>
            <div className="mt-4 space-y-1.5 border-t border-line pt-4 text-[12.5px] text-muted">
              {detail.author && <div>author: {detail.author}</div>}
              <div>engagement (at fetch): {interactions(detail)} interactions</div>
              {detail.created_at && (
                <div>
                  posted: {new Date(detail.created_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}
                </div>
              )}
              {detail.ingested_at && (
                <div>
                  fetched: {new Date(detail.ingested_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}
                </div>
              )}
              {detail.url && (
                <a href={detail.url} target="_blank" className="block text-trends hover:underline">
                  open original thread
                </a>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
