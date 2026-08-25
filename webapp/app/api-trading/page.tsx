import Link from "next/link";
import { get } from "@/lib/api";
import { Badge, EmptyState, PageHeader, SectionCard } from "@/components/ui";
import { DaysFilter } from "./days-filter";
import {
  type Candidate,
  type FunnelResp,
  type ThemeRow,
  type ThemesResp,
  FIRST_API_SPLIT_LABELS,
  KIND_FALLBACK_BAR,
  KIND_META,
  KIND_ORDER,
  SOURCE_LABELS,
  STAGE_META,
  pickDays,
  themeLabel,
} from "./lens";

const TREND_GLYPH: Record<Candidate["trend"], { char: string; cls: string }> = {
  up: { char: "↑", cls: "text-opps" },
  down: { char: "↓", cls: "text-danger" },
  flat: { char: "→", cls: "text-muted" },
};

function kindSegments(kinds: Record<string, number>) {
  const known: { kind: string; n: number; bar: string; label: string }[] = KIND_ORDER.map((k) => ({
    kind: k,
    n: kinds[k] ?? 0,
    bar: KIND_META[k].bar,
    label: KIND_META[k].label,
  }));
  const other = Object.entries(kinds)
    .filter(([k]) => !KIND_META[k])
    .reduce((s, [, n]) => s + n, 0);
  if (other > 0)
    known.push({
      kind: "other",
      n: other,
      bar: KIND_FALLBACK_BAR,
      label: "other",
    });
  return known.filter((s) => s.n > 0);
}

function ThemeBoard({
  title,
  blurb,
  themes,
  days,
  tone,
}: {
  title: string;
  blurb: string;
  themes: ThemeRow[];
  days: number;
  tone: "danger" | "opps";
}) {
  return (
    <SectionCard>
      <div className="mb-1 flex items-center gap-2">
        {/* full class names — Tailwind can't see constructed strings */}
        <span
          className={`h-1.5 w-1.5 rounded-full ${tone === "danger" ? "bg-danger" : "bg-opps"}`}
        />
        <div className="text-[13.5px] font-semibold">{title}</div>
      </div>
      <p className="mb-4 text-[12px] leading-relaxed text-muted">{blurb}</p>
      {themes.length === 0 ? (
        <EmptyState
          title="Nothing themed in this window"
          body="Widen the window above, or check back after the next classification run."
        />
      ) : (
        <div className="space-y-3">
          {themes.map((t) => (
            <div key={t.theme} className="rounded-[10px] border border-line bg-surface2/30 px-3.5 py-3">
              <div className="flex items-center justify-between gap-2">
                <Link
                  href={`/api-trading/data?theme=${t.theme}&days=${days}`}
                  className="text-[13px] font-medium hover:underline"
                >
                  {themeLabel(t.theme)}
                </Link>
                <span className="flex items-center gap-2">
                  <span className="text-[12.5px] font-semibold tabular-nums">{t.n}</span>
                  <Link
                    href={`/api-trading/data?theme=${t.theme}&days=${days}`}
                    className="text-[11.5px] text-muted hover:text-ink hover:underline"
                  >
                    all items
                  </Link>
                </span>
              </div>
              <div className="mt-2 space-y-1.5">
                {t.items.slice(0, 3).map((it) => (
                  <div key={it.item_id} className="text-[12px] leading-snug">
                    <span className="text-ink/90">{it.gist ?? it.text}</span>
                    <span className="ml-1.5 whitespace-nowrap text-[11px] text-muted">
                      {SOURCE_LABELS[it.source] ?? it.source} · eng {it.eng.toFixed(1)}
                      {it.url && (
                        <>
                          {" · "}
                          <a
                            href={it.url}
                            target="_blank"
                            className="text-trends hover:underline"
                          >
                            open
                          </a>
                        </>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

export default async function ApiTradingOverviewPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const days = pickDays(await searchParams);
  // Candidate trends compare the window vs the one before it — cap at 90d so
  // the previous window never reaches past the 180d retention horizon.
  const candDays = Math.min(days, 90);
  const [funnel, friction, working, cands] = await Promise.all([
    get<FunnelResp>(`/api-trading/funnel?days=${days}`, {
      days,
      stages: [],
      first_api_split: {},
    }),
    get<ThemesResp>(`/api-trading/themes?kind=friction&days=${days}&per_theme=5`, {
      days,
      kind: "friction",
      themes: [],
    }),
    get<ThemesResp>(`/api-trading/themes?kind=working&days=${days}&per_theme=5`, {
      days,
      kind: "working",
      themes: [],
    }),
    get<{ days: number; candidates: Candidate[] }>(
      `/api-trading/candidates?days=${candDays}`,
      { days: candDays, candidates: [] },
    ),
  ]);

  const grand = funnel.stages.reduce((s, x) => s + x.total, 0);
  const maxStage = Math.max(1, ...funnel.stages.map((s) => s.total));
  const splitTotal = Object.values(funnel.first_api_split).reduce((s, n) => s + n, 0);

  return (
    <div>
      <PageHeader
        title="API trading"
        accent="bg-trends"
        blurb="A lens on traders who trade via code and APIs, not charts: where they are in the journey, what blocks them, what already works for them, and what that says Nubra should build."
      />
      <DaysFilter days={days} />

      {/* ── journey funnel ─────────────────────────────────────────────── */}
      <SectionCard className="mb-5">
        <div className="mb-1 text-[13.5px] font-semibold">Journey funnel</div>
        <p className="mb-4 text-[12px] leading-relaxed text-muted">
          {grand.toLocaleString("en-IN")} classified items in the window, by journey
          stage. The thin bar under each stage is its kind mix.
        </p>
        {grand === 0 ? (
          <EmptyState
            title="No classified items in this window"
            body="The lens classifier runs with the hourly pipeline — widen the window above or check back later."
          />
        ) : (
          <div className="space-y-4">
            {funnel.stages.map((s) => {
              const meta = STAGE_META[s.stage] ?? { label: s.stage, meaning: "" };
              const pct = grand > 0 ? (s.total / grand) * 100 : 0;
              const segs = kindSegments(s.kinds);
              const segTotal = Math.max(1, segs.reduce((x, y) => x + y.n, 0));
              return (
                <div key={s.stage} className="grid grid-cols-12 items-center gap-3">
                  <div className="col-span-4 lg:col-span-3">
                    <div className="text-[13px] font-medium">{meta.label}</div>
                    <div className="text-[11.5px] leading-snug text-muted">{meta.meaning}</div>
                  </div>
                  <div className="col-span-6 lg:col-span-7">
                    <div className="h-5 w-full rounded bg-surface2">
                      <div
                        className="flex h-5 items-center rounded bg-trends/70 px-2 text-[11px] font-medium tabular-nums"
                        style={{ width: `${Math.max((s.total / maxStage) * 100, 6)}%` }}
                      >
                        {s.total}
                      </div>
                    </div>
                    {segs.length > 0 && (
                      <div
                        className="mt-1 flex h-1.5 w-full overflow-hidden rounded"
                        title={segs.map((x) => `${x.label} ${x.n}`).join(" · ")}
                      >
                        {segs.map((x) => (
                          <div
                            key={x.kind}
                            className={x.bar}
                            style={{ width: `${(x.n / segTotal) * 100}%` }}
                          />
                        ))}
                      </div>
                    )}
                    {s.stage === "first_api" && splitTotal > 0 && (
                      <div className="mt-1.5 text-[11.5px] text-muted">
                        {Object.entries(FIRST_API_SPLIT_LABELS)
                          .filter(([k]) => (funnel.first_api_split[k] ?? 0) > 0)
                          .map(
                            ([k, label]) =>
                              `${label}: ${funnel.first_api_split[k]}`,
                          )
                          .join(" · ")}
                        <span className="ml-1.5 text-muted/70">
                          — most historical rows are unclear; the split fills in as new
                          items are classified live.
                        </span>
                      </div>
                    )}
                  </div>
                  <div className="col-span-2 text-right text-[12px] tabular-nums text-muted">
                    {pct.toFixed(1)}%
                  </div>
                </div>
              );
            })}
            <div className="flex flex-wrap items-center gap-3 border-t border-line pt-3">
              <span className="micro">kind mix</span>
              {KIND_ORDER.map((k) => (
                <span key={k} className="flex items-center gap-1.5 text-[11.5px] text-muted">
                  <span className={`h-2 w-2 rounded-[2px] ${KIND_META[k].bar}`} />
                  {KIND_META[k].label}
                </span>
              ))}
              <span className="flex items-center gap-1.5 text-[11.5px] text-muted">
                <span className={`h-2 w-2 rounded-[2px] ${KIND_FALLBACK_BAR}`} />
                other
              </span>
            </div>
          </div>
        )}
      </SectionCard>

      {/* ── theme boards ───────────────────────────────────────────────── */}
      <div className="mb-5 grid gap-5 lg:grid-cols-2">
        <ThemeBoard
          title="Friction board"
          blurb="What blocks API traders right now, ranked by volume. Top items by engagement under each theme."
          themes={friction.themes}
          days={days}
          tone="danger"
        />
        <ThemeBoard
          title="Working-well board"
          blurb="What the community is showing off — proof of what already works for them."
          themes={working.themes}
          days={days}
          tone="opps"
        />
      </div>

      {/* ── build candidates ───────────────────────────────────────────── */}
      <div className="mb-2 flex items-baseline justify-between">
        <div className="text-[13.5px] font-semibold">Build candidates</div>
        <span className="text-[11.5px] text-muted">
          mentions: last {candDays}d vs the {candDays}d before
        </span>
      </div>
      {cands.candidates.length === 0 ? (
        <EmptyState
          title="No candidates defined"
          body="Candidate definitions live in the registry (api_trading.candidates)."
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {cands.candidates.map((c) => {
            const g = TREND_GLYPH[c.trend];
            return (
              <SectionCard key={c.key}>
                <div className="flex items-start justify-between gap-3">
                  <div className="text-[13px] font-semibold leading-snug">{c.title}</div>
                  <div className="flex shrink-0 items-baseline gap-1.5 tabular-nums">
                    <span className="text-lg font-semibold">{c.current}</span>
                    <span className={`text-[13px] font-semibold ${g.cls}`}>{g.char}</span>
                    <span className="text-[11.5px] text-muted">was {c.previous}</span>
                  </div>
                </div>
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {c.themes.map((t) => (
                    <Link key={t} href={`/api-trading/data?theme=${t}&days=${days}`}>
                      <Badge tone="trends">{themeLabel(t)}</Badge>
                    </Link>
                  ))}
                </div>
                {c.grounding.length > 0 && (
                  <div className="mt-3 border-t border-line pt-2.5">
                    <div className="micro mb-1">grounded on</div>
                    <ul className="space-y-0.5 text-[11.5px] text-muted">
                      {c.grounding.map((gl) => (
                        <li key={gl}>{gl}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </SectionCard>
            );
          })}
        </div>
      )}
    </div>
  );
}
