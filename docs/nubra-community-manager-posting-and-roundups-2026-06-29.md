# Nubra Community Manager — Recommendations, Voices & Roundups

> **STALE AS OF 2026-07-08 — kept for design rationale only.** The build
> deviated in load-bearing ways (React UI, restructured packages, vendored
> scraper transport, calibrations, Docker deploy). Current truth:
> `nubra-community-manager-status-2026-07-05.md` (what is built) +
> `nubra-beacon-tech-backlog-2026-07-08.md` (what remains). Where this file
> disagrees with those, those win.

_Design · 2026-06-29 · companion: `nubra-community-manager-architecture-2026-06-29.md`_

The architecture doc covers _listen → understand_. This covers **_recommend_**: which
conversations to engage, what to say (brand + rep), **when to post**, what to make, and how
the team gets a **daily + weekly roundup** on Slack + email. The hard part isn't generating
ideas — it's making them *usable, grounded, and compliant* for a regulated broker.

**Scope:** recommend only — including **when to post** (in scope). The system does **not**
post; there is **no approval-to-post workflow** here (that's a
[future addition](#8-future-additions)). A human reads the roundup and acts.

---

## 1. From insight to recommendation

```
   insights (trends · issues · features · voices) + conversations
        │
        ▼
   opportunity detector  ── score conversations; keep the few worth engaging (§2)
        │
        ▼
   reply generator  ── GROUNDED on nubra_features table (§3)
        ├─ 🏢 BRAND draft (official, USP-led)
        └─ 🧑 REP draft  (human, organic)
        │
        ▼
   compliance gate (defense-in-depth, §4)  ──fail──▶ regenerate / drop (logged)
        │ pass
        ▼
   when-to-post timing (§5)  +  content proposals top-3 (§6)
        │
        ▼
   Daily / Weekly roundup → Slack + Email (read-only)  →  human acts
```

An **opportunity** = a `conversation` (root + activity) worth engaging, with: `thread_id`,
priority, the matched insight (trend/issue/feature), both drafts, `recommended_timing`, and
`status` (suggested → acted | dismissed — set by the team from the dashboard, which both
closes the "did we already engage this?" loop and captures the training signal the future
feedback loop needs). De-duped across runs by `thread_id` so we never re-surface the same one.

**Nubra watch — a separate segment (never an opportunity).** If the mentioned broker is
**Nubra itself**, the conversation is diverted into its own segment and **flagged in the
next hourly heads-up** (support/grievance — it never waits for the morning roundup) — we
do **not** generate brand/rep drafts for it. Keeps us out
of doing grievance-handling on social (SEBI SCORES is the right channel).

**SEO keywords refine, never filter.** SEO keywords live **inside `nubra_features`**
(a versioned `seo_keywords[]` attribute on each USP/upcoming-feature row). They **expand**
each source's search (more recall on what we care about) and add a **relevance boost** to
the priority score — they never drop an item. Full blast radius stays.

---

## 2. Opportunity prioritization — what to surface

Can't chase every thread; a **priority score (0–100)** decides what reaches the team.

```
   freshness · velocity · reach · relevance · opportunity-type · author-quality
                          │
                          ▼  weighted sum
        already-surfaced this thread? ──yes──▶ downweight
                          │ no
                          ▼
                 priority 0–100  →  ≥70 top of roundup · 40–69 secondary · <40 omit
```

Scoring runs **hourly** (no LLM involved) and feeds an **hourly heads-up on Slack + email,
08:00–20:00 IST**, in two parts. The **actions** part highlights what is *new* since the
last one (fresh priority-≥70 opportunities, new Nubra mentions, newly-rising topics) —
plus **recurring momentum**: a topic already highlighted today that keeps gaining
traction in a *different thread* re-enters with a **recurrence boost** (it's more
relevant, not stale), and items are sorted by that boosted weight. The **ops summary**
part reports what the system did in the last hour (fetched, deduped, noise-filtered,
enriched, scored). When there are no new actions, a compact ops-only digest posts
(configurable down to full silence). Draft generation stays on the daily build.

| Signal | High when… |
|---|---|
| Freshness / velocity | thread is hours old and accelerating |
| Reach | author followers / views |
| Relevance | maps to a Nubra USP or a pain we solve |
| **Opportunity type** | competitor complaint · feature we satisfy · genuine question |
| Author quality | real trader / rising voice, not bot/tip-spam |

---

## 3. Grounded reply generation (no hallucinated claims)

For a broker, an invented feature or wrong price is a compliance incident. So reply
generation is grounded on **one vetted, version-controlled table: `nubra_features`**
(current + upcoming features, provided by marketing/product; LLM always reads
`is_current=true`).

```
   nubra_features  (versioned; status = live | upcoming)
     · what Nubra offers now   · what's coming soon   · category + description
        │
        ▼  passed to the reply LLM as context (the catalog is small — no RAG/embeddings)
   generate BRAND + REP draft  ── may only assert features present in the table
        │  (upcoming features → phrase as "coming soon", never a promise)
        ▼  → compliance gate
```

If `nubra_features` can't support a claim, the draft must not make it. This single rule
kills most compliance and trust risk before the gate even runs. When a user complains
about *another* broker's gap, the matching Nubra capability is pulled from this table and
that's what the reply highlights.

---

## 4. Compliance — defense-in-depth (SEBI + ASCI)

One LLM check is not enough. Three layers, every draft, fully logged:

```
   draft ─▶ [L1] deterministic denylist  ─▶ [L2] LLM compliance review (Claude)
                                                      │
                                                      ▼
                                          [L3] human reads it in the roundup (final backstop)
   any layer fails → regenerate or drop, with reason logged to compliance_audit
```

- **L1 rules (hard):** block tips/calls, "guaranteed/assured/X% returns", price targets,
  "sure shot", SL/target patterns, PII, naming-and-shaming a competitor.
- **L2 LLM:** classify against the SEBI rule list → pass/fail + reason.
- **L3 human:** since we don't auto-post, the person reading the roundup is the last gate.
- **ASCI disclosure:** any **representative** reply must disclose Nubra affiliation
  (India ASCI influencer/affiliate norms) — baked into the rep template.
- **Audit:** `compliance_audit(draft, layer, verdict, reason, ts)` for every draft.

**Must:** stay educational/factual/conversational; disclaimers where relevant.

---

## 5. When-to-post — timing intelligence (in scope)

Knowing *what* to say is half the value; *when* is the other half. Each opportunity and
content proposal carries a `recommended_timing`. v1 is rule-based (no own post-history yet):

```
   inputs:  thread urgency (live & rising? age?)  +  audience active-window (platform)
                          │
                          ▼
   if conversation live & rising (thread accelerating or its topic rising, age < ~12h):
        → "ENGAGE NOW (thread is hot)"
   elif evergreen/educational topic:
        → "SCHEDULE for next best window"
   else:
        → "by EOD / next pre-open"
```

**Indian-trader active windows (configurable):**

| Window (IST) | Why | Best for |
|---|---|---|
| 08:30–09:15 (pre-open) | planning, high intent | brand explainers, content drops |
| 09:15–10:00 (open) | volatility chatter | live market takes |
| 15:30–17:00 (post-close) | wrap-up | recaps, issue responses |
| 20:00–22:30 (evening) | retail leisure scroll | reels/shorts, engagement posts |

Output field example: `recommended_timing = {action: "now", window: "live", why: "thread +40%/hr"}`
or `{action: "schedule", window: "08:45–09:15 IST", why: "pre-open reach"}`.
_(Learning windows from our own post outcomes is a future addition — needs posting first.)_

Timing only works if it arrives in time: the hourly heads-up (§2) surfaces hot
opportunities within the hour — an "ENGAGE NOW" that first appears in the next-morning
roundup would already be cold.

---

## 6. Brand vs Representative — two voices, one thread is never both

Both drafted per opportunity; the roundup recommends which fits the thread.

```
              opportunity
              /          \
        🏢 BRAND        🧑 REP
        official        human persona (discloses affiliation — ASCI)
        USP-led         organic, curious, helpful, soft pull
```

| | 🏢 Brand | 🧑 Representative |
|---|---|---|
| Goal | authority, USPs | engage organically, pull *softly* |
| Tone | crisp, factual | curious, peer-to-peer |
| Best for | feature-request we satisfy, market moments | competitor complaints, "how do I…" questions |
| Never | spam, argue | hard pitch, hide affiliation |

USP/feature facts come from the grounded KB (§3) so brand copy stays consistent & true.

---

## 7. Content proposals — the 6th output (top 3, always on)

What our *own channels* should make from today's signal. The POC listed *every* format for
*every* trend (unusable). Production **forces a ranked, doable top-3**.

```
   day's signal → LLM drafts many candidates
        → score each: impact × reach-fit × effort × timeliness × on-brand
        → RANK → keep TOP 3 (must justify why these 3, not "everything")
   each proposal: format · hook · which trend it rides · why it lands · recommended window
```

| Rule | Why |
|---|---|
| Hard cap = 3, ranked | a team can execute 3; "everything" gets ignored |
| Each tied to a real signal | no generic ideas |
| Mixed formats | e.g. 1 infographic + 1 reel + 1 short |
| Carries a timing window (§5) | tells the team *when* to publish too |
| **Passes the compliance gate (§4)** | content is public-facing too — even non-advice copy can slip an unsubstantiated claim |

Always produced every run (like the POC's Actions tab) — but disciplined. Not
buy/sell content — the goal is relevant presence + engagement around trending topics.

---

## 8. Daily + weekly roundups → Slack + email (read-only)

```
 EventBridge ─▶ Orchestrator ─▶ read L3 rollups + opportunities/content_proposals (Postgres)
                     │            └▶ Sonnet: synthesize digest
                     ├▶ save roundups(period, payload)
                     ├▶ Slack channel  (digest, read-only)
                     └▶ Email (SMTP)   (readable archive)
```

**Daily:** top rising topics · new/worsening broker issues · feature requests gaining steam
· top rising voices · top opportunities (brand+rep drafts + **when-to-post**) · **top-3
content proposals**.

**Weekly (Sat ~10:00 IST, Sat→Sat window):** the highlights of the week — what trended,
which issues *persisted*, which features were *consistently* requested, voices to build
relationships with — ranked with a **last-week persistence weighting**: anything that
also appeared in the previous week's roundup weighs more (`weeks_running` shown per
item), plus a weekly recap of actions (heads-ups sent, opportunities surfaced,
acted/dismissed).

Read-only: the roundup informs; the team executes. (Approve→post buttons = future.)

---

## 9. Future additions

| Future | Adds |
|---|---|
| **Posting with human approval** | Slack `Approve/Edit/Skip` → `post_executor` posts the chosen reply at its `recommended_timing`; approval queue + `post_log`. |
| **Feedback loop** | track engagement on *our* posts → learn which voices/topics/timing work → tune priority & timing. |
| **Learned timing** | replace the rule-based windows (§5) with windows learned from our outcomes. |
| **Semi-auto posting** | after feedback earns trust, auto-post vetted low-risk **brand** replies only. |

---

## 10. Summary — the answers, concretely

| Question | Answer |
|---|---|
| Multiple sources, same downstream? | adapters → `SocialItem` → invariant pipeline (arch §2–4) |
| The six outputs? | trends · broker issues · feature requests · rep · brand · **content proposals (top 3)** |
| When to post? | **in scope** — rule-based timing per opportunity/proposal: live→now, else best Indian-market window (§5) |
| Replies won't hallucinate? | grounded on the versioned `nubra_features` table (§3) |
| Compliant? | defense-in-depth (rules + LLM + human backstop) + ASCI disclosure + audit log (§4) |
| Keep saving data? | append-only Postgres + dedup; daily snapshots → velocity & weekly deltas |
| Daily + weekly roundup? | synthesized digest → **Slack + email**, read-only, on EventBridge cron |
| Posting? | out of scope now (recommend only); posting + approval is a future addition |
