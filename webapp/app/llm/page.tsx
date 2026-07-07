import { get } from "@/lib/api";
import type { LlmUsageSummary } from "@/lib/types";
import { Badge, EmptyState, KpiCard, PageHeader, SectionCard } from "@/components/ui";

export const dynamic = "force-dynamic";

const fmtUsd = (v?: string | number | null) => {
  if (v == null) return "-";
  const n = Number(v);
  return `$${n.toFixed(n === 0 ? 2 : n < 0.01 ? 6 : n < 1 ? 4 : 2)}`;
};
const fmtTok = (v?: number | null) =>
  v == null ? "-" : v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : v >= 1_000 ? `${(v / 1_000).toFixed(1)}k` : String(v);
const fmtIst = (iso?: string) =>
  iso
    ? new Date(iso).toLocaleString("en-IN", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Kolkata",
      })
    : "-";

export default async function LlmPage() {
  const s = await get<LlmUsageSummary>("/llm-usage/summary", { window_days: 30 });
  const t = s.totals ?? {};
  const byDay = (s.by_day ?? []).slice(-14);
  const maxDayCost = Math.max(...byDay.map((d) => Number(d.cost_usd ?? 0)), 0.000001);
  const byStage = s.by_stage ?? [];
  const maxStageCost = Math.max(...byStage.map((d) => Number(d.cost_usd ?? 0)), 0.000001);
  const syncCost = Number(t.cost_usd ?? 0) - Number(t.batch_cost ?? 0);
  const batchSavings = Number(t.batch_cost ?? 0); // batch = 50% off → savings equal what was paid

  return (
    <div className="space-y-6">
      <PageHeader
        title="LLM usage"
        accent="bg-voices"
        blurb={`Every Claude call the pipeline makes, priced at call time and stored locally — the radar's own meter, not a Langfuse clone. Deep per-call traces stream to Langfuse when its keys are configured in .env. Window: last ${s.window_days} days.`}
      />

      {(t.calls ?? 0) === 0 ? (
        <EmptyState
          title="No LLM usage recorded yet"
          body="Rows appear as pipeline stages run (enrich, draft, compose). Kick off ./cm run-local or wait for the next scheduled run."
        />
      ) : (
        <>
          <section className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <KpiCard label={`Spend ${s.window_days}d`} value={fmtUsd(t.cost_usd)} />
            <KpiCard label="Calls" value={t.calls ?? "-"} hint={`${t.traced_calls ?? 0} traced to Langfuse`} />
            <KpiCard label="Tokens in" value={fmtTok(t.input_tokens)} />
            <KpiCard label="Tokens out" value={fmtTok(t.output_tokens)} />
            <KpiCard
              label="Batch savings"
              value={fmtUsd(batchSavings)}
              hint={`${t.batch_calls ?? 0} batch calls at half price`}
            />
          </section>

          <SectionCard>
            <div className="micro mb-3">spend per day — last 14 days</div>
            <div className="flex h-28 items-end gap-1.5">
              {byDay.map((d) => (
                <div
                  key={d.day}
                  className="group flex flex-1 flex-col items-center gap-1"
                  title={`${d.day}: ${fmtUsd(d.cost_usd)} · ${d.calls} calls · ${fmtTok((d.input_tokens ?? 0) + (d.output_tokens ?? 0))} tokens`}
                >
                  <div
                    className="w-full rounded-t bg-voices/70 transition-colors group-hover:bg-voices"
                    style={{
                      height: `${Math.max((Number(d.cost_usd ?? 0) / maxDayCost) * 88, 3)}px`,
                    }}
                  />
                  <span className="text-[10px] tabular-nums text-muted">
                    {d.day.slice(5).replace("-", "/")}
                  </span>
                </div>
              ))}
            </div>
          </SectionCard>

          <div className="grid gap-3 lg:grid-cols-2">
            <SectionCard>
              <div className="micro mb-3">by stage</div>
              <div className="space-y-2">
                {byStage.map((r) => (
                  <div key={r.stage} className="grid grid-cols-12 items-center gap-2">
                    <span className="col-span-3 truncate text-[12.5px]">{r.stage}</span>
                    <div className="col-span-6">
                      <div className="h-4 w-full rounded bg-surface2">
                        <div
                          className="h-4 rounded bg-voices/70"
                          style={{
                            width: `${Math.max((Number(r.cost_usd ?? 0) / maxStageCost) * 100, 4)}%`,
                          }}
                        />
                      </div>
                    </div>
                    <span className="col-span-3 text-right text-[11.5px] tabular-nums text-muted">
                      {fmtUsd(r.cost_usd)} · {r.calls} call{r.calls !== 1 ? "s" : ""}
                    </span>
                  </div>
                ))}
              </div>
            </SectionCard>

            <SectionCard>
              <div className="micro mb-3">by model</div>
              <div className="space-y-2.5">
                {(s.by_model ?? []).map((m) => (
                  <div
                    key={`${m.model}-${m.batch}`}
                    className="flex items-center justify-between gap-2 text-[12.5px]"
                  >
                    <span className="flex items-center gap-2 truncate">
                      {m.model}
                      {m.batch && <Badge tone="voices">batch −50%</Badge>}
                    </span>
                    <span className="shrink-0 tabular-nums text-muted">
                      {fmtUsd(m.cost_usd)} · {fmtTok(m.input_tokens)} in / {fmtTok(m.output_tokens)} out
                    </span>
                  </div>
                ))}
                <p className="border-t border-line pt-2 text-[11.5px] leading-relaxed text-muted">
                  Sync spend {fmtUsd(syncCost)} vs batch {fmtUsd(t.batch_cost)} — batch runs at
                  half price, so every batch dollar spent saved another dollar.
                  {(t.unpriced_calls ?? 0) > 0 &&
                    ` ${t.unpriced_calls} call(s) hit a model missing from the price table (cost shown excludes them).`}
                </p>
              </div>
            </SectionCard>
          </div>

          <SectionCard>
            <div className="micro mb-3">recent runs — one row per ./cm invocation</div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-left">
                    {["run", "when", "stages", "calls", "tokens", "cost"].map((h) => (
                      <th
                        key={h}
                        className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {(s.recent_runs ?? []).map((r) => (
                    <tr key={r.run_id}>
                      <td className="px-2 py-2 font-mono text-[11.5px] text-muted">
                        {r.run_id.slice(0, 8)}
                      </td>
                      <td className="px-2 py-2 text-[12px] tabular-nums">{fmtIst(r.ended)}</td>
                      <td className="px-2 py-2">
                        <span className="flex flex-wrap gap-1">
                          {(r.stage_list ?? []).map((st) => (
                            <Badge key={st}>{st}</Badge>
                          ))}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-[12.5px] tabular-nums">{r.calls}</td>
                      <td className="px-2 py-2 text-[12.5px] tabular-nums">{fmtTok(r.tokens)}</td>
                      <td className="px-2 py-2 text-[12.5px] font-medium tabular-nums">
                        {fmtUsd(r.cost_usd)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </>
      )}
    </div>
  );
}
