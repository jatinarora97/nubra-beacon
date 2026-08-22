# The API-Trader Segment — v0 evidence + the system that hunts them (2026-08-22)

Goal: get API traders onto Nubra. Method: treat API-trader chatter as its own
first-class segment inside Beacon — separate classification, separate storage,
separate dashboard lens — that continuously answers four questions: where is
each person in the journey, what is working for them (build parity), what is
failing them (build advantage), and where does Nubra pitch in.

This doc = what one month of EXISTING data already shows (v0 scan, capped
export) + the prod-grade system design + what we instrumented today.

## 1 · The five stages, with this month's evidence

v0 scan: 2,000-item export (Jul 23–Aug 22) → 93 keyword-gated + 900 wide-
screened → **130 candidate items**, high-confidence core ≈ 50-60 (v0
classifier is deliberately loose; the prod gate below fixes precision).

| Stage | n | What the chatter looks like (real specimens) |
|---|---|---|
| **exploring** | ~50 | "Bloomberg alternative" hunger: a dev asking for working guides to an open-source financial-data platform (Instagram, 18k interactions). Mixed with heavy finfluencer "start from zero" noise — the stage exists but our precision here is lowest. |
| **first_api** | 11 | The THINNEST stage in our data — the exact moment someone gets keys/auth/first order working is barely visible. This is Nubra's highest-value intercept and our biggest observation gap. |
| **building** | 45 | The richest stage. Flattrade + Quantman NIFTY algo showcase, +12% in 4 months (Reddit). "Claude AI + Dhan MCP" AI-powered trading workflow (YouTube, 15k). Monte-Carlo strategy sims in Colab (Instagram, 14k). Systematic backtest across 123 Indian ETFs (YouTube). Free NSE OI data turned into a build-up screener vs Rs 35k paid tools (Instagram, 42k). |
| **scaling** | 24 | Public algo traders posting DAILY P&L: "ALGO UPDATE · Aug ROI +0% · Capital Rs 5 Cr" (X) — a visible, followable cohort running real capital, complaining about premium action their algos can't counter. Position-sizing/scale discipline threads. |
| **churning** | 0 | ZERO friction/switch chatter captured — not because it doesn't exist, but because our sources were tuned for brand marketing, not builder pain. The pain lives in r/algorading, OpenAlgo GitHub issues, tool-specific threads — exactly what we added today. |

Kind split across the core set: 32 showcases · 12 guidance-seeking · 2
comparisons · 1 friction. **Success chatter dominates — and that is signal,
not noise** (user decision 2026-08-22): every showcase names the stack that
WORKED, i.e. the parity checklist for Nubra.

## 2 · What's working for them (the parity board, from showcases)

1. **Backtesting as proof-of-competence** — people flaunt backtests (123-ETF
   sweeps, Monte Carlo sims) the way chart traders flaunt P&L screenshots.
   The backtest IS the content format of this segment.
2. **AI as the new on-ramp** — Claude+Dhan MCP, LLM-assisted analysis tools,
   "AI quant" content pulls 10k+ engagement. The 2026 first_api moment
   increasingly runs through an AI assistant, not a Postman collection.
3. **Free/open data beats paid tools as a story** — NSE participant-OI
   screeners built free vs Rs 35k tools; OpenBB-as-Bloomberg. "Institutional
   data, retail price" is a proven resonance line.
4. **Public P&L accountability** — scaling-stage algo traders build
   audiences by posting daily algo P&L. They are identifiable, followable,
   and reachable (Voices page material).
5. **No-code as the bridge** — strategy builders + backtesters (AlgoTest-
   style) are how non-coders enter systematic trading before ever writing
   Python.

## 3 · Where Nubra pitches in (mapped to REAL grounding-v2 features)

| Chatter pattern | Nubra feature that answers it | Pitch angle |
|---|---|---|
| "Claude + broker MCP" AI workflows | Developer platform + Trading/portfolio APIs | Ship/document a Nubra MCP server — meet the AI-trader wave where Dhan is currently alone |
| Backtest-flaunting culture | Historical data APIs | Free, deep, clean historical data = the raw material of the segment's content format |
| Free-NSE-data screener builds | Realtime market-data APIs + 250-instrument watchlists | "Institutional data, retail price" — we already have the ingredients |
| first_api onboarding invisibility | Developer platform | The quickstart-to-first-order experience is an open field; nobody's chatter says any broker does this well |
| Scaling-stage daily-P&L cohort | Trading APIs with flexi orders | Direct relationship building — these are named, public voices |

## 4 · What to build (candidates surfaced by data, for leadership to rank)

1. **Nubra MCP / AI-assistant integration** — the single clearest 2026 gap
   with proof of demand (15k-engagement content for the Dhan equivalent).
2. **First-order-in-five-minutes developer onboarding** — attack the
   invisible-but-critical first_api stage.
3. **Backtest-ready historical data bundles** — package what the segment
   already flaunts.
4. **OpenAlgo integration** — distribution: being one of its 33+ brokers is
   presence in every middleware user's dropdown.
5. **TradingView webhook execution path** — the chart-to-API conversion
   moment, top of this funnel.

## 5 · The prod-grade system (what "own segment" means in Beacon)

1. **Candidate gate** (cheap, code): entity gazetteer from the landscape
   (7 core + layers) + automation vocabulary — runs in the pipeline after
   enrichment, flags candidates. High recall.
2. **Lens classifier** (Haiku, absence-based like enrichment): candidates →
   `api_trader_items` table: stage (5), layer (broker_api / no_code /
   backtesting / data_feed / charting_signal / community), kind (showcase /
   guidance_seeking / friction / comparison), tools[] (canonical names),
   working_well (bool + what), nubra_opening (nullable: which grounded
   feature answers it). High precision — the v0 looseness dies here.
3. **Own surfaces**: "API traders" dashboard section (stage funnel over
   time, tool leaderboard, working-well board, openings feed with receipts,
   the scaling-cohort voices list) + `/api/beacon/v1/api-traders/*`
   endpoints so the segment is queryable by other teams/agents.
4. **Own digest**: weekly API-trader segment summary (works even while
   general Slack digests stay off — separate knob).
5. **Sources feeding it** (added + seeded today, 2026-08-22): r/algorading,
   r/algotrading, keyword watch (kite connect / openalgo / algotest /
   tradetron / broker api on X+Reddit), 6 YouTube api_algo queries, 3 GitHub
   queries. Ships with the next release; known blind spots: Telegram/Discord
   (skipped per user), Marketcalls forum (needs an adapter look).

## 6 · Honest limits of this v0

- Export capped at 2,000 items; the full corpus (~10x) is unscanned until a
  prod dump or on-prod run.
- v0 classifier precision ~50% at the exploring stage (finfluencer noise);
  the two-stage prod gate is designed to fix exactly this.
- churning = 0 reflects source blindness, not reality — fixed by today's
  source expansion, visible after the next release + backfill.
- Two wide-screen chunks failed parsing (~50 items unscreened).

## 7 · Next steps

1. Release (ships new sources) + backfill pass + `make dump` → full-corpus
   v1 scan → this doc's numbers get real depth.
2. Build the segment pipeline (§5, ~2 days) after leadership nods on the
   shape.
3. Draft the leadership doc v1 from the v1 scan: journey map with receipts,
   parity board, openings ranked, build candidates with demand evidence.
