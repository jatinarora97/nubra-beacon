# Ads compliance & ops reference — API-trader campaigns (2026-08-29)

Reference companion to `api-trader-ads-strategy-2026-08-29.md`. Nothing here is strategy — it's the verification chains, ad-code rules, data-law grounds, budget/measurement wiring, and open blockers, for whoever operates the campaigns. All policy pages fetched live 2026-08-29.

## 1. Verification chains (one-time, ~3–4 weeks total, run in parallel)

| Step | What | Timeline | Source |
|---|---|---|---|
| 1 | SEBI SI Portal: email + mobile on Nubra's record must match what Google Ads and Meta Business register with — both verify against it | prerequisite | [SEBI advisory PR 14/2025](https://www.sebi.gov.in/media-and-notifications/press-releases/mar-2025/advisory-to-sebi-registered-intermediaries-uploading-advertisements-on-social-media-platforms-smps-_92866.html) |
| 2 | Google financial-services verification (mandatory for India since Jan 2023): G2RS third-party verification of SEBI authorization → Google advertiser verification → [FSV form](https://support.google.com/google-ads/contact/google_ads_financial_services_verification). Business name must exactly match the SEBI registry entry | ≤5 days (G2RS) + ~5 business days (Google) | [G2RS portal](https://g2risksolutions.com/financial-services) · [regulators policy](https://support.google.com/adspolicy/answer/12390454) |
| 3 | Meta SEBI verification (mandatory for India securities ads since Jul 31, 2025); SEBI-registered entities clear near-instantly | ~days | [coverage](https://inc42.com/buzz/meta-mandates-sebi-verification-for-investment-ads-in-india/) — canonical doc is login-gated, confirm in Business Manager |
| 4 | Exchange pre-approval for EVERY creative (incl. landing pages, influencer videos, app promos): NSE ENIT-COMPLIANCE, max 5 creatives/application, **≥7 working days before release**; approved creatives reusable 180 days; penalty ₹1 lakh/instance escalating to new-client bans | per creative batch | [NSE Code of Advertisement](https://www.nseindia.com/static/trade/members-code-of-advertisement) (NSE/COMP/55482) |

## 2. Creative rules that bind every asset (NSE/BSE ad code + SEBI Master Circular)

1. Standard warning, verbatim, ≥10-pt: *"investments in securities market are subject to market risks, read all the related documents carefully before investing."* Video: on-screen AND voice-over, **≥5 seconds**. Space-constrained formats (search ads, SMS): a hyperlink to the site carrying full details is mandatory.
2. Must carry: SEBI-registered name, complete address, registration number(s), Member ID, own logo — more prominently than any group brand.
3. **§5.7 — the binding constraint for this audience**: no reference, direct or indirect, to **past performance or expected returns of algo strategies**, in any advertisement or publicly accessible business communication; no association with platforms displaying strategy returns. Kills backtest screenshots, P&L creatives, "X% CAGR" hooks. ⚠️ legal review on reach into docs/organic/marketplace listings.
4. No superlatives ("best/#1") unless independently conferred, unpaid. No competitor discrediting (facts about ourselves only). No specific scrip/contract recommendations. No celebrities — anyone >10 lakh followers per handle counts; vet every creator. No referral incentives/cashback/prizes for account opening or app installs. Brokerage-rate mentions need "Brokerage will not exceed the SEBI prescribed limit". Statistics need cited, verifiable sources. NSE's name/logo may not appear.
5. "9 out of 10 individual F&O traders incurred net losses" ([SEBI circular May 2023](https://www.sebi.gov.in/legal/circulars/may-2023/risk-disclosure-with-respect-to-trading-by-individual-traders-in-equity-futures-and-options-segment_71426.html)) is a **website/login-popup mandate, not an ad mandate** — but F&O landing pages are approval-scoped; the exchange approver decides in practice.
6. Exemptions from pre-approval: purely educational content, market commentary, existing-client communications via registered channels tagged "for consumption by the client, do not redistribute".

## 3. Email/data law — why scraping is out, what consent must say

**Scraping emails from Reddit/forums/GitHub for targeting: prohibited on five independent grounds**, each sufficient: (1) [GitHub AUP](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies) bans using scraped info for unsolicited contact; (2) Reddit UA bans automated collection/commercial use; (3) [Google Customer Match](https://support.google.com/adspolicy/answer/6299717) requires first-party data "collected directly from customers", auditable; (4) [Meta CA terms](https://www.facebook.com/legal/terms/customaudience) require warranted consent; (5) DPDP Act (penalties to ₹250 crore) requires specific informed consent — the "publicly available" exemption should be assumed not to apply (⚠️ counsel).

**Uploading OUR customer emails to ad platforms**: allowed mechanically (Customer Match min 100 users, 540-day membership; Meta CA/lookalikes min 100/country; India has NO Meta special-ad-category finance restrictions — [Meta API docs](https://developers.facebook.com/docs/marketing-api/special-ad-category/)) — but advertising is a **new processing purpose** under DPDP: KYC/onboarding consent does not cover it. Consent notice + privacy policy must specifically name marketing/ad-platform sharing; hashed emails remain personal data (⚠️ counsel confirms). Meta CA extra rule: audience names/criteria must not be based on financial attributes — name lists neutrally. DPDP Rules 2025 notified 13 Nov 2025, full compliance by 13 May 2027.

**Lead follow-up** (calls/WhatsApp to Meta lead-ad leads): TRAI DND + SEBI communications rules apply — separate compliance surface (⚠️).

## 4. Budget shape + measurement wiring

No India CPC data was verifiable — shares, not rupees; recalibrate after 4 weeks of real CPCs.

| Slice | Share | KPI that matters |
|---|---|---|
| Google Search (core intent + conquest) | 40% | API-signup CPA, UAT-activation rate — not clicks |
| YouTube (placements + keywords + Shorts/Hindi test cells) | 25% | view-through signups, branded-search lift |
| Meta (lead ads + lookalikes once seed ≥100 activated API users) | 20% | verified-lead CPA, lead→activation % |
| Non-ad (newsletter sponsorships, creator integrations, GEO content) | 15% | listicle inclusions, LLM prompt-panel mention rate |

Wiring: Enhanced Conversions (Google) + CAPI (Meta) with DPDP-reviewed consent before scaling · conversion = API signup and UAT activation, not page views · weekly LLM prompt panel (15–20 prompts across ChatGPT/Gemini/Perplexity/Claude/Grok; can run as a Beacon cron — Gemini grounding and Perplexity Sonar expose citations via API) · server logs: OAI-SearchBot/ClaudeBot/PerplexityBot hits on nubra.io as leading GEO indicator · watch [AlgoTest Broker Speedtest](https://algotest.in/blog/broker-speedtest-algotest/) — a top-3 latency rank is a free, §5.7-safe, third-party proof asset.

## 5. Blockers and legal-review flags

**Blockers (in order):**
1. **Publish API pricing** — "transparent pricing" hooks, comparison pages, and conquest copy all reference it; a blank own-column loses every comparison.
2. SI-portal contact sync (gates both platform verifications).
3. DPDP consent wording for list uploads (gates Customer Match / Meta CA).
4. §5.7 legal read (gates creative range and marketplace associations).

**Legal-review flags:** G2RS signatory + legal-entity name match · Meta pre-verification "education/brand" exemption (get written confirmation) · hashed-emails-as-personal-data position · dual NSE+BSE approval practice (no single-approval provision found) · voluntary F&O loss-stat in creatives (approver discretion) · influencer follower-count edge cases · TRAI DND on lead follow-up.

**Couldn't be verified this session (do manually in a browser):** Google Ads Transparency Center + Meta Ad Library passes for Dhan/Upstox/Angel One/AlgoTest (both require JS) · Google Trends IN curves for the keyword families · India-specific CPCs.
