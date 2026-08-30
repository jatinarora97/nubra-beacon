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

## 4. Taxonomy check (the §4 hypothesis) — confirmed, with two surprises

| Predicted source type | Showed up? | Counter-move |
|---|---|---|
| Third-party listicles | Yes — algotest, groww blog, chittorgarh, fintegrationfs, sahi, liquide, tradejini | Play C outreach — **list updated below** |
| Forum/Reddit threads | Yes — reddit in 7/10 questions, tradingqna | Play D — disclosed answers |
| Brokers' own crawlable pages | **Yes, strongest single pattern** — Zerodha's support articles + kite.trade docs = 15 citations | Plays A/B validated: our docs/numbers/support pages CAN be cited directly — if crawlable and question-shaped |
| multibagg pair | **No — didn't appear at all**, even Q10 | Deprioritize fixing it; it doesn't rank where it matters |
| **Surprise 1** | Claude's Brave tail: tradejini/liquide/sahi/ashlarindia — low-authority blogs winning citations | New outreach targets + confirms Brave is undefended |
| **Surprise 2** | Pocketful (younger than Nubra's API) already in Claude's answer set 5/10 | Existence proof: a new broker can enter the candidate set — likely via crawlable free-API positioning picked up by these blogs |

## 5. Action deltas (changes to the standing plan, from this data)

1. **Zerodha's 15 citations are support articles** ("what are the charges for Kite APIs", "how do I sign up") — question-titled, crawlable pages. Our equivalent: ship the numbers page + FAQ-style crawlable pages titled with the literal panel questions (fixes 3+5), highest confidence play after this experiment.
2. **Updated outreach queue (play C), by observed citation power**: algotest.in blog (7 questions!) > groww blog is competitor-owned (skip) > tradejini blog, blog.liquide.life, sahi.com, fintegrationfs.com, chittorgarh, indianbrokertest > multibagg (demoted — never appeared).
3. **Claude/Brave is the beachhead**: submit to Brave's index, make comparison pages crawlable, and expect Claude to pick Nubra up first — it already names 8+ brands per answer and cites tiny blogs.
4. **Reddit appears in 7/10 questions** across Top-sites and AI Overview — play D unchanged, priority up.
5. **Gemini is the slow engine**: memory-based, stale pricing. Don't measure early progress on it; measure on Claude first, AI Overview second, ChatGPT third.
6. Re-run this identical panel ~6 weeks after fixes 1–4 ship. Success metric v1: Nubra named in ≥1 engine on Q2/Q3/Q4; cited ≥1 time. (Today: 0 and 0.)
