"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { get } from "@/lib/api";
import { Badge, EmptyState } from "@/components/ui";
import {
  type LensItem,
  DAYS_PRESETS,
  FRICTION_THEME_LABELS,
  KIND_ORDER,
  LAYERS,
  SOURCE_LABELS,
  STAGE_META,
  STAGE_ORDER,
  WORKING_THEME_LABELS,
  themeLabel,
} from "../lens";

const PAGE = 50;

const selectCls =
  "rounded-md border border-line bg-surface px-2.5 py-1.5 text-[12.5px]";

function fmtDate(iso?: string | null): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    timeZone: "Asia/Kolkata",
  });
}

export function LensDataTable() {
  // ?theme= / ?days= etc. deep-links (Overview theme rows and candidate chips
  // land here prefiltered).
  const sp = useSearchParams();
  const [stage, setStage] = useState(sp.get("stage") ?? "");
  const [kind, setKind] = useState(sp.get("kind") ?? "");
  const [layer, setLayer] = useState(sp.get("layer") ?? "");
  const [theme, setTheme] = useState(sp.get("theme") ?? "");
  const [firstApiType, setFirstApiType] = useState(sp.get("first_api_type") ?? "");
  const [days, setDays] = useState(() => {
    const n = Number(sp.get("days"));
    return Number.isInteger(n) && n >= 1 && n <= 365 ? n : 90;
  });
  // free-text inputs are debounced: *Live is the keystroke state
  const [q, setQ] = useState(sp.get("q") ?? "");
  const [qLive, setQLive] = useState(sp.get("q") ?? "");
  const [tool, setTool] = useState(sp.get("tool") ?? "");
  const [toolLive, setToolLive] = useState(sp.get("tool") ?? "");

  const [items, setItems] = useState<LensItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setQ(qLive), 350);
    return () => clearTimeout(t);
  }, [qLive]);
  useEffect(() => {
    const t = setTimeout(() => setTool(toolLive), 350);
    return () => clearTimeout(t);
  }, [toolLive]);

  function pageUrl(off: number): string {
    const params = new URLSearchParams();
    if (stage) params.set("stage", stage);
    if (kind) params.set("kind", kind);
    if (layer) params.set("layer", layer);
    if (theme) params.set("theme", theme);
    if (firstApiType) params.set("first_api_type", firstApiType);
    if (q) params.set("q", q);
    if (tool) params.set("tool", tool);
    params.set("days", String(days));
    params.set("limit", String(PAGE));
    params.set("offset", String(off));
    return `/api-trading/items?${params}`;
  }

  // Monotonic id per filter-state: a Load-more response landing after the
  // filters changed is stale and must be dropped, not appended.
  const fetchGen = useRef(0);

  useEffect(() => {
    const gen = ++fetchGen.current;
    setLoading(true);
    setOffset(0);
    setExpanded(null);
    get<LensItem[]>(pageUrl(0), []).then((rows) => {
      if (fetchGen.current === gen) {
        setItems(rows);
        setHasMore(rows.length === PAGE);
        setLoading(false);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, kind, layer, theme, firstApiType, q, tool, days]);

  async function loadMore() {
    if (loadingMore) return;
    setLoadingMore(true);
    const gen = fetchGen.current;
    const next = offset + PAGE;
    const rows = await get<LensItem[]>(pageUrl(next), []);
    if (fetchGen.current === gen) {
      setItems((prev) => [...prev, ...rows]);
      setOffset(next);
      setHasMore(rows.length === PAGE);
    }
    setLoadingMore(false);
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select value={stage} onChange={(e) => setStage(e.target.value)} className={selectCls}>
          <option value="">all stages</option>
          {STAGE_ORDER.map((s) => (
            <option key={s} value={s}>
              {STAGE_META[s].label.toLowerCase()}
            </option>
          ))}
        </select>
        <select value={kind} onChange={(e) => setKind(e.target.value)} className={selectCls}>
          <option value="">all kinds</option>
          {KIND_ORDER.map((k) => (
            <option key={k} value={k}>
              {k.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <select value={layer} onChange={(e) => setLayer(e.target.value)} className={selectCls}>
          <option value="">all layers</option>
          {LAYERS.map((l) => (
            <option key={l} value={l}>
              {l.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <select value={theme} onChange={(e) => setTheme(e.target.value)} className={selectCls}>
          <option value="">all themes</option>
          <optgroup label="friction">
            {Object.keys(FRICTION_THEME_LABELS).map((t) => (
              <option key={t} value={t}>
                {themeLabel(t)}
              </option>
            ))}
          </optgroup>
          <optgroup label="working well">
            {Object.keys(WORKING_THEME_LABELS).map((t) => (
              <option key={t} value={t}>
                {themeLabel(t)}
              </option>
            ))}
          </optgroup>
        </select>
        <select
          value={firstApiType}
          onChange={(e) => setFirstApiType(e.target.value)}
          className={selectCls}
        >
          <option value="">any first-API type</option>
          <option value="broker">first broker API</option>
          <option value="any">first API ever</option>
          <option value="unclear">unclear</option>
        </select>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className={selectCls}
        >
          {DAYS_PRESETS.map((p) => (
            <option key={p.days} value={p.days}>
              last {p.label}
            </option>
          ))}
        </select>
        <input
          value={toolLive}
          onChange={(e) => setToolLive(e.target.value)}
          placeholder="tool, e.g. kite"
          className={`${selectCls} w-36 placeholder:text-muted/60`}
        />
        <input
          value={qLive}
          onChange={(e) => setQLive(e.target.value)}
          placeholder="search text…"
          className={`${selectCls} min-w-48 flex-1 placeholder:text-muted/60`}
        />
      </div>

      {loading ? (
        <div className="py-16 text-center text-[13px] text-muted">loading…</div>
      ) : items.length === 0 ? (
        <EmptyState
          title="No lens items match"
          body="Loosen the filters or widen the day window — or the classifier genuinely hasn't seen matching items yet."
        />
      ) : (
        <div className="overflow-x-auto rounded-[10px] border border-line">
          <table className="w-full min-w-[1180px]">
            <thead className="bg-surface2/70">
              <tr className="text-left">
                {["posted", "source", "stage", "kind", "layer", "theme", "tools", "gist", "eng", "link"].map((h) => (
                  <th key={h} className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-surface">
              {items.map((it) => {
                const itemTheme = it.friction_theme ?? it.working_theme;
                const open = expanded === it.item_id;
                return (
                  <tr
                    key={it.item_id}
                    onClick={() => setExpanded(open ? null : it.item_id)}
                    className="cursor-pointer align-top transition-colors hover:bg-surface2/50"
                    title={open ? undefined : "click to show the raw text"}
                  >
                    <td className="whitespace-nowrap px-3 py-2.5 text-[11.5px] tabular-nums text-muted">
                      {fmtDate(it.created_at)}
                    </td>
                    <td className="px-3 py-2.5">
                      <Badge>{SOURCE_LABELS[it.source] ?? it.source}</Badge>
                    </td>
                    <td className="px-3 py-2.5 text-[12px] text-muted">
                      {it.stage ? (STAGE_META[it.stage]?.label ?? it.stage) : "–"}
                      {it.stage === "first_api" && it.first_api_type && it.first_api_type !== "unclear" && (
                        <div className="text-[10.5px] text-muted/80">{it.first_api_type}</div>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-[12px] text-muted">
                      {it.kind?.replace(/_/g, " ") ?? "–"}
                    </td>
                    <td className="px-3 py-2.5 text-[12px] text-muted">
                      {it.layer?.replace(/_/g, " ") ?? "–"}
                    </td>
                    <td className="px-3 py-2.5 text-[12px] text-muted">
                      {itemTheme ? themeLabel(itemTheme) : "–"}
                    </td>
                    <td className="max-w-[9rem] px-3 py-2.5">
                      <div className="flex flex-wrap gap-1">
                        {(it.tools ?? []).slice(0, 4).map((t) => (
                          <Badge key={t}>{t}</Badge>
                        ))}
                        {(it.tools?.length ?? 0) > 4 && (
                          <span className="text-[11px] text-muted">+{it.tools!.length - 4}</span>
                        )}
                      </div>
                    </td>
                    <td className="max-w-xl px-3 py-2.5 text-[12.5px]">
                      <div className={open ? "" : "line-clamp-2"}>{it.gist ?? "–"}</div>
                      {open && (
                        <div className="mt-1.5 whitespace-pre-wrap text-[12px] leading-relaxed text-muted">
                          {it.text}
                          {it.author && (
                            <span className="mt-1 block text-[11px]">— {it.author}</span>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-[12px] tabular-nums text-muted">
                      {it.engagement.toFixed(1)}
                    </td>
                    <td className="px-3 py-2.5">
                      {it.url && (
                        <a
                          href={it.url}
                          target="_blank"
                          onClick={(e) => e.stopPropagation()}
                          className="text-[12px] text-trends hover:underline"
                        >
                          open
                        </a>
                      )}
                    </td>
                  </tr>
                );
              })}
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
    </div>
  );
}
