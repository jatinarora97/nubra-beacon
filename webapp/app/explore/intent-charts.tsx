"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { get } from "@/lib/api";

/* ── Fixed intent → color map (module-level; NEVER derived from response
      order, so a filter that changes the series count never repaints the
      survivors). The --chart-* custom properties are themed per mode in
      globals.css. ─────────────────────────────────────────────────────── */
export const INTENT_ORDER = [
  "complaint",
  "feature_request",
  "question",
  "praise",
  "comparison",
  "how_to",
  "news_opinion",
  "spam",
  "unclassified",
] as const;

export const INTENT_COLOR: Record<string, string> = {
  complaint: "var(--chart-complaint)",
  feature_request: "var(--chart-feature-request)",
  question: "var(--chart-question)",
  praise: "var(--chart-praise)",
  comparison: "var(--chart-comparison)",
  how_to: "var(--chart-how-to)",
  news_opinion: "var(--chart-news-opinion)",
  spam: "var(--chart-spam)",
  unclassified: "var(--muted)",
};

type SeriesResponse = {
  bucket: "hour" | "day";
  from: string;
  to: string;
  points: { bucket: string; intent: string | null; n: number }[];
};

type Series = {
  bucket: "hour" | "day";
  buckets: number[]; // bucket timestamps (ms UTC), contiguous — zero buckets included
  counts: Record<string, number[]>; // intent → count per bucket (fixed order keys)
  intents: string[]; // intents present, in fixed INTENT_ORDER order
};

/** Contiguous bucket timestamps across the response window, so the x-axis is
 *  true time — buckets the backend omits (zero items) still take their slot. */
function bucketRange(resp: SeriesResponse): number[] {
  const stepMs = resp.bucket === "hour" ? 3_600_000 : 86_400_000;
  const from = new Date(resp.from);
  const t0 =
    resp.bucket === "hour"
      ? Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), from.getUTCDate(),
          from.getUTCHours())
      : Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), from.getUTCDate());
  const t1 = Date.parse(resp.to);
  const out: number[] = [];
  for (let t = t0; t <= t1 && out.length < 400; t += stepMs) out.push(t);
  if (out.length >= 400 || out.length === 0) {
    // Degenerate window — fall back to the buckets actually observed.
    return [...new Set(resp.points.map((p) => Date.parse(p.bucket)))].sort(
      (a, b) => a - b,
    );
  }
  return out;
}

function shape(resp: SeriesResponse): Series {
  const buckets = bucketRange(resp);
  const idx = new Map(buckets.map((b, i) => [b, i]));
  const counts: Record<string, number[]> = {};
  for (const p of resp.points) {
    const i = idx.get(Date.parse(p.bucket));
    if (i === undefined) continue;
    const key =
      p.intent && (INTENT_ORDER as readonly string[]).includes(p.intent)
        ? p.intent
        : "unclassified";
    if (!counts[key]) counts[key] = new Array(buckets.length).fill(0);
    counts[key][i] += p.n;
  }
  const intents = INTENT_ORDER.filter(
    (i) => counts[i] && counts[i].some((v) => v > 0),
  );
  return { bucket: resp.bucket, buckets, counts, intents };
}

/* ── Axis helpers ──────────────────────────────────────────────────────── */

function yScale(max: number): { top: number; ticks: number[] } {
  if (max <= 0) return { top: 1, ticks: [1] };
  // Smallest "nice" step giving at most 4 gridlines (2.5×10^k only where it
  // stays an integer) — keeps the recessive grid at 3-4 lines for real data.
  const steps: number[] = [];
  for (let k = 0; k < 10; k++)
    for (const m of [1, 2, 2.5, 5])
      if (!(m === 2.5 && k === 0)) steps.push(m * 10 ** k);
  steps.sort((a, b) => a - b);
  const step = steps.find((s) => Math.ceil(max / s) <= 4) ?? max;
  const top = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = step; v <= top; v += step) ticks.push(v);
  return { top, ticks };
}

const HOUR_FMT = new Intl.DateTimeFormat("en-IN", {
  hour: "2-digit",
  hour12: false,
  timeZone: "Asia/Kolkata",
});
const DAY_FMT = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit",
  month: "short",
  timeZone: "Asia/Kolkata",
});

function bucketLabel(t: number, bucket: "hour" | "day"): string {
  const d = new Date(t);
  return bucket === "hour" ? `${HOUR_FMT.format(d)}:00` : DAY_FMT.format(d);
}

/** Tooltip header: hour buckets also carry the date for orientation. */
function bucketTitle(t: number, bucket: "hour" | "day"): string {
  const d = new Date(t);
  return bucket === "hour"
    ? `${DAY_FMT.format(d)} ${HOUR_FMT.format(d)}:00`
    : DAY_FMT.format(d);
}

/** At most ~6 x labels, thinned evenly. */
function labelIndices(n: number): Set<number> {
  const step = Math.max(1, Math.ceil(n / 6));
  const out = new Set<number>();
  for (let i = 0; i < n; i += step) out.add(i);
  return out;
}

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) =>
      setW(entries[0].contentRect.width),
    );
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

const H = 300;
const PAD = { top: 10, right: 10, bottom: 24, left: 44 };

const intentLabel = (k: string) => k.replace(/_/g, " ");

/* ── Shared chart chrome ───────────────────────────────────────────────── */

function Grid({
  ticks,
  top,
  width,
  fmt = (t) => String(t),
}: {
  ticks: number[];
  top: number;
  width: number;
  fmt?: (t: number) => string;
}) {
  const plotH = H - PAD.top - PAD.bottom;
  return (
    <>
      {ticks.map((t) => {
        const y = PAD.top + plotH * (1 - t / top);
        return (
          <g key={t}>
            <line
              x1={PAD.left}
              x2={width - PAD.right}
              y1={y}
              y2={y}
              stroke="var(--line)"
              strokeWidth={1}
            />
            <text
              x={PAD.left - 6}
              y={y + 3}
              textAnchor="end"
              fontSize={12}
              fill="var(--muted)"
            >
              {fmt(t)}
            </text>
          </g>
        );
      })}
      {/* baseline */}
      <line
        x1={PAD.left}
        x2={width - PAD.right}
        y1={H - PAD.bottom}
        y2={H - PAD.bottom}
        stroke="var(--line)"
        strokeWidth={1}
      />
    </>
  );
}

function XLabels({
  buckets,
  bucket,
  xAt,
}: {
  buckets: number[];
  bucket: "hour" | "day";
  xAt: (i: number) => number;
}) {
  const show = labelIndices(buckets.length);
  return (
    <>
      {buckets.map((b, i) =>
        show.has(i) ? (
          <text
            key={b}
            x={xAt(i)}
            y={H - PAD.bottom + 16}
            textAnchor="middle"
            fontSize={12}
            fill="var(--muted)"
          >
            {bucketLabel(b, bucket)}
          </text>
        ) : null,
      )}
    </>
  );
}

function Legend({
  intents,
  selected,
  onSelect,
}: {
  intents: string[];
  selected: string | null;
  onSelect: (i: string) => void;
}) {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
      {intents.map((i) => (
        <button
          key={i}
          onClick={() => onSelect(i)}
          title={selected === i ? "show all intents" : "show only this intent"}
          className={`inline-flex items-center gap-1.5 text-[12.5px] text-muted transition-opacity hover:text-ink ${
            selected !== null && selected !== i ? "opacity-40" : ""
          }`}
        >
          <span
            className="h-2 w-2 rounded-[2px]"
            style={{ background: INTENT_COLOR[i] }}
          />
          {intentLabel(i)}
        </button>
      ))}
    </div>
  );
}

function Tooltip({
  x,
  y,
  width,
  children,
}: {
  x: number;
  y: number;
  width: number;
  children: React.ReactNode;
}) {
  const flip = x > width / 2;
  return (
    <div
      className="pointer-events-none absolute z-10 rounded-md border border-line bg-surface px-2.5 py-1.5 text-[12px] text-ink shadow-lg"
      style={{
        left: flip ? undefined : x + 12,
        right: flip ? width - x + 12 : undefined,
        top: Math.max(0, y - 10),
      }}
    >
      {children}
    </div>
  );
}

/* ── Line chart: one line per intent over time ─────────────────────────── */

function LineChart({
  series,
  selected,
}: {
  series: Series;
  selected: string | null;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hoverI, setHoverI] = useState<number | null>(null);
  const { buckets, counts, bucket } = series;
  const intents = selected
    ? series.intents.filter((i) => i === selected)
    : series.intents;

  const max = Math.max(
    1,
    ...intents.map((i) => Math.max(...counts[i])),
  );
  const { top, ticks } = yScale(max);
  const plotW = Math.max(0, width - PAD.left - PAD.right);
  const plotH = H - PAD.top - PAD.bottom;
  const n = buckets.length;
  const xAt = (i: number) =>
    PAD.left + (n === 1 ? plotW / 2 : (i * plotW) / (n - 1));
  const yAt = (v: number) => PAD.top + plotH * (1 - v / top);

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left;
    if (n === 0) return;
    const i =
      n === 1
        ? 0
        : Math.max(
            0,
            Math.min(n - 1, Math.round(((px - PAD.left) / plotW) * (n - 1))),
          );
    setHoverI(i);
  }

  const hoverRows =
    hoverI == null
      ? []
      : intents
          .map((i) => ({ intent: i, n: counts[i][hoverI] }))
          .filter((r) => r.n > 0)
          .sort((a, b) => b.n - a.n);

  return (
    <div ref={ref} className="relative">
      {width > 0 && (
        <svg
          width={width}
          height={H}
          onMouseMove={onMove}
          onMouseLeave={() => setHoverI(null)}
        >
          <Grid ticks={ticks} top={top} width={width} />
          <XLabels buckets={buckets} bucket={bucket} xAt={xAt} />
          {intents.map((it) =>
            n === 1 ? (
              <circle
                key={it}
                cx={xAt(0)}
                cy={yAt(counts[it][0])}
                r={3}
                fill={INTENT_COLOR[it]}
              />
            ) : (
              <path
                key={it}
                d={counts[it]
                  .map(
                    (v, i) =>
                      `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)} ${yAt(v).toFixed(1)}`,
                  )
                  .join(" ")}
                fill="none"
                stroke={INTENT_COLOR[it]}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            ),
          )}
          {hoverI != null && (
            <>
              <line
                x1={xAt(hoverI)}
                x2={xAt(hoverI)}
                y1={PAD.top}
                y2={H - PAD.bottom}
                stroke="var(--muted)"
                strokeWidth={1}
                opacity={0.45}
              />
              {hoverRows.map((r) => (
                <circle
                  key={r.intent}
                  cx={xAt(hoverI)}
                  cy={yAt(r.n)}
                  r={4}
                  fill={INTENT_COLOR[r.intent]}
                  stroke="var(--surface)"
                  strokeWidth={1.5}
                />
              ))}
            </>
          )}
        </svg>
      )}
      {hoverI != null && hoverRows.length > 0 && (
        <Tooltip x={xAt(hoverI)} y={PAD.top} width={width}>
          <div className="mb-0.5 text-[11px] text-muted">
            {bucketTitle(buckets[hoverI], bucket)}
          </div>
          {hoverRows.map((r) => (
            <div key={r.intent} className="flex items-center gap-1.5">
              <span
                className="h-2 w-2 rounded-[2px]"
                style={{ background: INTENT_COLOR[r.intent] }}
              />
              <span className="text-muted">{intentLabel(r.intent)}</span>
              <span className="ml-auto pl-3 font-medium tabular-nums">
                {r.n}
              </span>
            </div>
          ))}
        </Tooltip>
      )}
    </div>
  );
}

/* ── Stacked bar chart: intent mix per bucket, normalized to 100% ──────── */

type SegHover = {
  i: number;
  intent: string;
  n: number;
  pct: number;
  x: number;
  y: number;
};

function StackedBars({
  series,
  selected,
}: {
  series: Series;
  selected: string | null;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<SegHover | null>(null);
  const { buckets, counts, bucket } = series;
  const intents = selected
    ? series.intents.filter((i) => i === selected)
    : series.intents;

  // Denominator is always the bucket's FULL total (all intents), so an
  // isolated intent reads as its share of the mix — the bar then only
  // partially fills, which is the point.
  const totals = buckets.map((_, bi) =>
    series.intents.reduce((s, it) => s + counts[it][bi], 0),
  );
  const top = 100;
  const ticks = [0, 25, 50, 75, 100];
  const plotW = Math.max(0, width - PAD.left - PAD.right);
  const plotH = H - PAD.top - PAD.bottom;
  const n = buckets.length;
  const slot = n > 0 ? plotW / n : 0;
  const barW = Math.max(3, Math.min(36, slot - Math.max(2, slot * 0.3)));
  const xAt = (i: number) => PAD.left + i * slot + (slot - barW) / 2;

  function onSegMove(e: React.MouseEvent<SVGRectElement>, seg: SegHover) {
    const rect = e.currentTarget.ownerSVGElement!.getBoundingClientRect();
    setHover({ ...seg, x: e.clientX - rect.left, y: e.clientY - rect.top });
  }

  return (
    <div ref={ref} className="relative">
      {width > 0 && (
        <svg width={width} height={H} onMouseLeave={() => setHover(null)}>
          <Grid ticks={ticks} top={top} width={width} fmt={(t) => `${t}%`} />
          <XLabels
            buckets={buckets}
            bucket={bucket}
            xAt={(i) => xAt(i) + barW / 2}
          />
          {buckets.map((b, bi) => {
            if (totals[bi] <= 0) return null; // empty bucket — nothing to show
            let acc = 0;
            return intents.map((it) => {
              const v = counts[it][bi];
              if (v <= 0) return null;
              const pct = (v / totals[bi]) * 100;
              acc += pct;
              const yTop = PAD.top + plotH * (1 - acc / top);
              const h = (plotH * pct) / top;
              return (
                <rect
                  key={`${b}-${it}`}
                  x={xAt(bi)}
                  y={yTop}
                  width={barW}
                  height={h}
                  fill={INTENT_COLOR[it]}
                  stroke="var(--surface)"
                  strokeWidth={2}
                  onMouseMove={(e) =>
                    onSegMove(e, { i: bi, intent: it, n: v, pct, x: 0, y: 0 })
                  }
                  onMouseLeave={() => setHover(null)}
                />
              );
            });
          })}
        </svg>
      )}
      {hover && (
        <Tooltip x={hover.x} y={hover.y} width={width}>
          <div className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-[2px]"
              style={{ background: INTENT_COLOR[hover.intent] }}
            />
            <span className="text-muted">{intentLabel(hover.intent)}</span>
            <span className="pl-2 font-medium tabular-nums">
              {hover.pct.toFixed(1)}% ({hover.n})
            </span>
          </div>
          <div className="mt-0.5 text-[11px] text-muted">
            {bucketTitle(buckets[hover.i], bucket)}
          </div>
        </Tooltip>
      )}
    </div>
  );
}

/* ── Container: fetches the series, renders both charts side by side ───── */

export function IntentCharts({ query }: { query: string }) {
  const [resp, setResp] = useState<SeriesResponse | null>(null);
  const [loaded, setLoaded] = useState(false);
  // Selected intent (isolate mode) — null shows all. Shared by both charts.
  const [selected, setSelected] = useState<string | null>(null);

  // `query` already carries the debounced q — this re-runs on filter/window
  // changes only, never per keystroke.
  useEffect(() => {
    let live = true;
    get<SeriesResponse | null>(`/items/intent-series?${query}`, null).then(
      (r) => {
        if (live) {
          setResp(r);
          setLoaded(true);
        }
      },
    );
    return () => {
      live = false;
    };
  }, [query]);

  const series = useMemo(
    () => (resp && resp.points.length > 0 ? shape(resp) : null),
    [resp],
  );

  function select(i: string) {
    setSelected((prev) => (prev === i ? null : i));
  }

  const empty = (
    <div className="flex h-[300px] items-center justify-center text-[12.5px] text-muted">
      {loaded ? "No data in this window" : "loading…"}
    </div>
  );

  return (
    <div className="mb-5 grid gap-4 2xl:grid-cols-2">
      {(
        [
          ["Intent over time", LineChart],
          ["Intent mix (%)", StackedBars],
        ] as const
      ).map(([title, Chart]) => (
        <div
          key={title}
          className="rounded-[10px] border border-line bg-surface p-4"
        >
          <div className="micro mb-2">{title}</div>
          {series ? (
            <>
              <Chart series={series} selected={selected} />
              <Legend
                intents={series.intents}
                selected={selected}
                onSelect={select}
              />
            </>
          ) : (
            empty
          )}
        </div>
      ))}
    </div>
  );
}
