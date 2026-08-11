# Instagram ingestion: Apify vs official Meta Graph API (2026-08-11)

_Decision document. The Apify side is LIVE-TESTED with our account (46 results,
$0.12, samples in `out/instagram-test/`); the Meta side is from official docs —
no Meta business app exists yet, and this comparison concludes we may never
need one. Companion to the tier design in `docs/HANDOVER.md` §Instagram._

## 1 · Head-to-head

| | **Apify (`apify/instagram-scraper`)** | **Official Meta Graph API** |
|---|---|---|
| What it is | Managed scraping actor (360k users, 174M runs) | Instagram's sanctioned API (Business Discovery + Hashtag Search are capabilities INSIDE it, not separate APIs) |
| Setup | Apify account + token — **worked in minutes** | Nubra business IG account + Meta app + app review incl. Public Content Access (days–weeks lead time; brand-attached) |
| Watch accounts | ✅ any public account — live-verified on 8/8 finfluencers + Zerodha | ⚠ only business/creator accounts, metadata only |
| Hashtag discovery | ❌ **live test came back empty** (hashtag pages gated) — unreliable | ✅ but hard cap 30 unique hashtags per rolling week |
| Comments on others' posts | ✅ ~10 sampled per post, with authors | ❌ not available |
| Media files (video/image URLs) | ✅ direct CDN URLs (expire in hours — download at fetch time) | ❌ never |
| Engagement depth | likes, comments, **plays vs views** (reach signal) | likes + comments counts only |
| Transcripts | ❌ not included — see §3 | ❌ not included |
| Cost | $0.0027/post (free tier: ~1,850/mo free; $29 Starter: ~12,600/mo) | free |
| Risk | medium: public-data scraping vs Meta ToS; isolated (no Nubra credential/account involved); kill-switch = one registry line | zero |
| Reliability owner | Apify (paid SLA-ish) | Meta (rate-limited, reviewed) |

**Verdict:** account-watching via Apify is the only route that delivers what the
tiers need (comments + media), at pocket cost, without brand attachment. The
official API's two real advantages (zero risk, hashtag search) are undermined by
its two hard walls (no media, no others' comments) and the 30-hashtag cap.
Official API = optional later add-on, NOT the foundation. Instagram no longer
blocks on Meta app review.

## 2 · What extraction actually returns

### Apify — real post, extracted 2026-08-11 (`out/instagram-test/stockswithmanveer.json`)

```json
{
  "shortCode": "Db3XvPyyRZS",                 → external_id (dedup key)
  "type": "Video",                             → source_type='reel'
  "url": "https://www.instagram.com/p/Db3XvPyyRZS/",
  "caption": "How to successfully get an IPO allotment? ...",   → tier-0 enrichment text
  "hashtags": ["ipo","sharemarket","investing","stockmarketindia",...],
  "timestamp": "2026-08-10T15:49:21.000Z",     → created_at
  "ownerUsername": "stockswithmanveer",        → author (Voices)
  "ownerFullName": "Manveer Singh | Finance",
  "likesCount": 3086, "commentsCount": 247,    → unified engagement score
  "videoViewCount": 71197, "videoPlayCount": 160182,   → reach signal Reddit can't give
  "videoDuration": 75.5,
  "videoUrl": "https://instagram.f...fbcdn.net/...", ← SIGNED, EXPIRES IN HOURS
  "displayUrl": "https://...jpg",              → keyframe/thumbnail
  "musicInfo": {"uses_original_audio": true},  → worth transcribing (vs meme audio)
  "paidPartnership": false,                    → disclosure flag (compliance)
  "latestComments": [
    {"text": "Ipo", "ownerUsername": "garvitparganiha"},   → each = child SocialItem
    {"text": "IPO", "ownerUsername": "saravana_47"}
  ]
}
```

One post yields: 1 parent item + ~10 comment items + 1 Voices author update +
media pointers for the AV tiers. Maps onto the SocialItem contract with zero
new pipeline machinery.

### Meta Graph API — documented response shape (business_discovery, not live-tested)

```json
{ "business_discovery": {
    "username": "stockswithmanveer",
    "followers_count": 1250000,
    "media": { "data": [ {
        "id": "17895695668004550",
        "caption": "How to successfully get an IPO allotment? ...",
        "media_type": "VIDEO",
        "media_url": null,            ← NOT returned for other accounts' media
        "permalink": "https://www.instagram.com/p/Db3XvPyyRZS/",
        "timestamp": "2026-08-10T15:49:21+0000",
        "like_count": 3086,
        "comments_count": 247
} ] } } }
```

Same caption/counts — but no comment texts, no media URLs, no play counts, no
music/disclosure metadata. Tier 0 only, forever.

## 3 · Transcripts and image text are SEPARATE extractions — always

Neither route returns what a reel says or what an infographic shows. That is a
second extraction step in both worlds, and it's where the real intelligence is
(most finfluencer content is: talking-head audio + annotated chart images).

```
                    ┌──────────────────────────────────────────────────────┐
   Apify scraper →  │ caption + comments + engagement      TIER 0 (all)    │ ~$0.0027/post
                    ├──────────────────────────────────────────────────────┤
   videoUrl ──────→ │ TRANSCRIPT — one of:                 TIER 1 (gated)  │
   (expires! fetch  │  a) Apify transcript actor            ~$0.01/reel    │ zero setup — START HERE
    at collect time)│     (crawlerbros/…, ~1k users)                       │
                    │  b) own faster-whisper `small` CPU    $0/reel        │ ~1 day setup (ffmpeg+model
                    │     in the morning build                             │ in image); scale-up path
                    ├──────────────────────────────────────────────────────┤
   displayUrl /  ─→ │ IMAGE/CHART READING — Haiku vision    TIER 2 (top    │ ~$0.004/post
   carousel images  │  (interprets charts/claims, not       slice only)    │ no actor can do this;
                    │   just OCR)                                          │ it's ours either way
                    └──────────────────────────────────────────────────────┘
   Everything appends to the item's text (CAPTION|TRANSCRIPT|ON-SCREEN) →
   existing absence-based enrichment re-processes — no new pipeline machinery.
```

Gating rule (from the live sample): engagement varies 4 orders of magnitude
across accounts (27 → 181k likes), so tier gates must be **relative to each
account's own baseline**, not one absolute bar.

## 4 · Cost at plan scale (8–15 accounts, ~40–80 posts/day)

| Component | Monthly |
|---|---|
| Apify collection (~1,200–2,400 results) | $0 (free credits) → $5.50 |
| Transcript actor (~15 gated reels/day) | ~$4.50 |
| Haiku vision (~5 gated image posts/day) | ~$0.60 |
| Tier-0 enrichment (Haiku batch) | ~$1 |
| **Total** | **≈ $6–12, mostly inside free credits at start** |

Upgrade triggers: Apify Starter ($29 → ~12,600 results at $0.0023) when
accounts exceed ~15–20 or comment harvesting turns on; own whisper when
transcript volume 10×es or the actor proves unreliable on Hinglish.

## 5 · Open items before build

Rotate the Apify PAT (pasted in chat 2026-08-11, same list as YouTube/GitHub
keys) · curate the account list (drop sjosephburns; decide US-content accounts)
· `instagram_account` watch-kind + collector (known-shape build) · per-account
relative tier gates · download-at-fetch for media (URL expiry).
