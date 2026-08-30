# AI-search experiment — baseline results (2026-08-30)

Input: the 10-query panel from `nubra-organic-ai-visibility-2026-08-29.md` §4, run manually by the user on Google (India), ChatGPT, Claude, Gemini + Google AI Overview + top organic results. Raw capture: `docs/experiment.rtfd`. This doc is the extraction: who gets named, who gets cited, what pattern wins, and the action deltas.

## Headline

- **Nubra: 0 mentions in 40 answer slots (4 AI engines × 10 questions), 0 citations in 155 URLs.** Predicted baseline confirmed — even the multibagg comparison article didn't surface on Q10.
- **Every AI engine recommends brokers by name, every time.** The candidate set is small and stable: Zerodha, Dhan, Fyers, Upstox, Angel One. Getting into that set is the whole game.

## 1. Who gets named (brand presence across the 40 AI-answer slots)

| Brand | Slots /40 | Strongest engine | Note |
|---|---|---|---|
| Zerodha/Kite | **32** | Claude 10/10 | Named in every Claude answer |
| Dhan | **28** | Claude 9, Gemini 8 | The default "free alternative" |
| Fyers | 25 | Claude 8 | Named despite its outage record |
| Upstox | 20 | Claude 8 | Sandbox praised in Q4 |
| Angel One | 20 | Gemini 7 | |
| Shoonya | 15 | Claude 6 | "free API" framing |
| AlgoTest | 11 | **AI Overview 6** | The AI Overview kingmaker |
| Kotak / Tradetron / TrueData | 7 each | mixed | |
| **Pocketful** | **5** | **Claude 5/10** | A young broker already inside Claude's set — proof of feasibility |
| **Nubra** | **0** | — | |

## 2. Who gets cited (155 URLs, by domain)

| Rank | Domain | Citations | In # questions | Type |
|---|---|---|---|---|
| 1 | support.zerodha.com + kite.trade | 9 + 6 = **15** | 6–7 | **Broker's own support/docs pages** |
| 2 | algotest.in | 9 | 7 | Tool blog/listicles |
| 3 | reddit.com | 7 | **7 of 10** | Forum threads |
| 4 | tradejini.com | 7 | 6 | Small broker's blog listicles (all via Claude) |
| 5 | nseindia.com | 7 | 3 | Official |
| 6 | groww.in | 6 | 6 | Broker blog |
| 7 | blog.liquide.life | 6 | 4 | Trading-app blog listicles (all via Claude) |
| 8 | dhanhq.co / dhan.co | 6 + 4 | 5 | Broker product + docs |
| 9 | fintegrationfs.com, sahi.com, ashlarindia.com, chittorgarh, tradingqna, marketcalls | 2–4 each | 2–3 | Long tail: listicles + forums |

## 3. Each engine's signature (matches the research predictions)

| Engine | Behavior observed | Implication for us |
|---|---|---|
| **Claude** | Cites the most URLs; its sources are **Brave-index long-tail blogs** (tradejini, liquide.life, sahi.com — pages nobody optimizes for). Names the widest broker set incl. Pocketful | **Cheapest engine to win.** Nobody competes for Brave. Crawlable comparison/numbers pages + presence on these small blogs gets us in fastest |
| **Google AI Overview** | Cites Google-top-organic: algotest.in (5), groww.in, reddit | Win = normal Google SEO + AlgoTest relationship + Reddit threads |
| **ChatGPT** | Few citations (6 total; nseindia, zerodha support, sebi) — answers mostly from model memory + light fetching | Two paths: Bing indexing for the fetch path, and UGC/Reddit for the memory path (slow) |
| **Gemini** | Least citations of all (2) — answers almost purely from **training memory**, and it's stale: quoted Kite at ₹2,000/mo (it's ₹500 since 2025) | Can't be won by site fixes alone — needs the long game (Reddit/UGC/press that lands in training data). Stale facts = opening: "current pricing" content wins corrections elsewhere |

## 4. Prediction vs reality — did the sources we bet on actually show up?

Context: before the experiment, the plan predicted that every source an AI engine cites would fall into **four types** — third-party listicles, forum/Reddit threads, brokers' own pages, and the one existing Nubra comparison article (multibagg). The point of predicting: each type has a prepared counter-move, so if the prediction holds, the plan needs no redesign — only prioritization. This section checks each prediction against the 155 citations actually collected, then lists what appeared that we did NOT predict (the surprises — the most valuable part).

**Verdict: 3 of 4 predictions confirmed, 1 failed, 2 surprises. The plan's plays survive; their order changes (see §5).**

| We predicted engines would cite… | What actually happened | So the plan's counter-move is… |
|---|---|---|
| Third-party "best of" lists | **Confirmed** — algotest, chittorgarh, fintegrationfs, sahi, liquide, tradejini all cited | Valid: outreach to get Nubra added to those lists (play C) — priority order updated in §5.2 |
| Forum/Reddit threads | **Confirmed** — reddit cited in 7 of 10 questions, plus tradingqna | Valid: answer those exact threads with a disclosed official account (play D) — priority raised |
| Brokers' own websites (docs/FAQ/support pages) | **Confirmed, and it's the STRONGEST source type** — Zerodha's support articles + kite.trade docs alone took 15 citations | Valid and upgraded to top priority: engines will cite Nubra's own pages directly, IF they are crawlable and titled as questions (plays A/B) |
| The multibagg Nubra-vs-Zerodha article (the one page online that compares Nubra) | **Failed — it never appeared**, not even on Q10 where it's most relevant | Drop it: fixing/promoting that article was in the plan; it doesn't rank where engines look, so the effort moves elsewhere |

**The two surprises (things no prediction covered):**

| Surprise | What we saw | Why it matters |
|---|---|---|
| 1. Claude cites tiny, low-authority blogs | tradejini.com, blog.liquide.life, sahi.com, ashlarindia — small sites with no SEO reputation — kept winning Claude citations | Claude reads the Brave search index, which almost nobody optimizes for. Low competition = Nubra's fastest entry point ("beachhead" in §5.3) |
| 2. Pocketful is already in the answers | A broker with a YOUNGER API than Nubra's appears in 5 of Claude's 10 answers | Existence proof that a new broker can break into the candidate set — the barrier is content and crawlability, not brand age or size |

## 5. Action deltas (changes to the standing plan, from this data)

1. **Zerodha's 15 citations are support articles** ("what are the charges for Kite APIs", "how do I sign up") — question-titled, crawlable pages. Our equivalent: ship the numbers page + FAQ-style crawlable pages titled with the literal panel questions (fixes 3+5), highest confidence play after this experiment.
2. **Updated outreach queue (play C), by observed citation power**: algotest.in blog (7 questions!) > groww blog is competitor-owned (skip) > tradejini blog, blog.liquide.life, sahi.com, fintegrationfs.com, chittorgarh, indianbrokertest > multibagg (demoted — never appeared).
3. **Claude/Brave is the beachhead**: submit to Brave's index, make comparison pages crawlable, and expect Claude to pick Nubra up first — it already names 8+ brands per answer and cites tiny blogs.
4. **Reddit appears in 7/10 questions** across Top-sites and AI Overview — play D unchanged, priority up.
5. **Gemini is the slow engine**: memory-based, stale pricing. Don't measure early progress on it; measure on Claude first, AI Overview second, ChatGPT third.
6. Re-run this identical panel ~6 weeks after fixes 1–4 ship. Success metric v1: Nubra named in ≥1 engine on Q2/Q3/Q4; cited ≥1 time. (Today: 0 and 0.)
