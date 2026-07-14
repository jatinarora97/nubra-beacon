# Nubra Beacon: Social Posting and Design Review Intelligence Plan

## Purpose

This document captures two future intelligence modules that can be added on top of the existing Nubra Beacon data layer:

1. Social media posting recommendations and approval workflow
2. Figma-based product flow, UX and UI consistency review

The goal is to use the community, competitor, SEO, YouTube, GitHub, app-review and broker-community data already collected by Beacon to move from passive insight reporting to practical execution support.

---

## Nubra Context Layer

Both modules should use a shared Nubra context layer. This is important because the system should not only know what users are asking for; it should also know what Nubra already has, what is upcoming, what can be claimed publicly and what should be treated only as internal roadmap context.

### Existing Layer in Beacon

Beacon already has a versioned product-context table:

```text
nubra_features
```

This table currently stores:

| Field | Purpose |
|---|---|
| feature | Name of the Nubra capability |
| description | Product-approved explanation |
| status | live or upcoming |
| category | Trading, analytics, platform, pricing, onboarding, etc. |
| seo_keywords | Keywords used for search expansion and recommendation matching |
| version | Version of the catalog |
| is_current | Marks the active catalog |

This should remain the single grounding layer for Nubra product claims.

### What Should Be Added to the Context Layer

The current feature catalog should be expanded from a small assumed catalog into a richer product context layer.

Recommended context categories:

| Context Type | Examples |
|---|---|
| Live features | Current app, retail, API, trading and analytics capabilities |
| Upcoming features | New retail app features, option chain improvements, strategy tools |
| Feature status | live, upcoming, internal-only, experimental, deprecated |
| Personas | Investor, option buyer, option seller, OI trader, scalper, API user |
| Product surfaces | Mobile app, web, API, SDK, MCP, dashboard |
| Claims allowed | What marketing can safely say |
| Claims to avoid | Roadmap promises, unsupported claims, competitor attacks |
| SEO keywords | Marketing/SEO keywords mapped to product areas |
| Competitor mapping | Which competitor feature/pain point this relates to |
| Design rules | UX/UI rules, design system notes, trading-risk requirements |

### How Social Recommendations Should Use It

The social recommendation module should use Nubra context to decide:

- Whether a topic maps to a live Nubra capability
- Whether it maps to an upcoming capability
- Whether the topic is better suited for education, launch, webinar or lead magnet
- Whether Nubra can make a direct claim or should keep the message generic
- Which persona the post should target
- Which feature page, help article or product surface should be linked
- Which SEO keywords should be naturally included

Example:

```text
Community signal:
Users are asking for better option-chain filtering and OI-based scanning.

Nubra context match:
Option chain filters, OI trader mode, option buyer/seller modes, query-based AI scans.

Recommended output:
Educational post + launch teaser + webinar topic around reading OI and filtering option-chain noise.
```

### How Figma Review Should Use It

The Figma/design review module should use Nubra context to check:

- Whether the design matches the intended feature behavior
- Whether the selected persona flow is correct
- Whether trading-risk information is visible at the right moment
- Whether the design handles live/upcoming feature limitations honestly
- Whether labels and UI copy match approved product terminology
- Whether the flow supports the right product surface: mobile, web, API, etc.
- Whether developer handoff includes feature-specific states and edge cases

Example:

```text
Uploaded flow:
Option seller mode in option chain.

Nubra context needed:
Option seller persona, OI filters, bid-ask spread, max pain, PCR, margin/risk, strategy-level SL/TP.

Review output:
Check if filters are discoverable, risk is visible, reset states exist, selected mode persists, and order actions are not confused with analysis-only views.
```

### Context Grounding Rule

Any generated social copy, product recommendation or design review should follow this rule:

```text
If the claim is about Nubra, it must be grounded in the active Nubra context catalog.
```

If the context layer does not confirm a feature, the system should phrase it as:

- a possible opportunity
- an internal idea
- a recommended improvement
- a market expectation

It should not phrase it as an existing Nubra capability.

---

## 1. Social Media Posting Recommendations

### Problem

Beacon already collects useful market signals: user complaints, feature requests, competitor gaps, trending topics, SEO keywords, YouTube discussions and retail/API pain points. But today those insights still need to be manually converted into LinkedIn, Twitter/X, Instagram, YouTube Shorts or community posts.

The opportunity is to convert those signals into recommended posts that a PM, marketing person or founder can review, edit, approve and publish.

### Product Goal

Create a system that recommends what Nubra should post, why it should post it, which audience it is for, and what message angle should be used.

Initial version should not auto-post directly. It should generate post recommendations, drafts and creative briefs, then require human approval before publishing.

### Core Inputs

| Input | How it helps |
|---|---|
| Reddit discussions | Understand retail trader/API user pain points and repeated questions |
| YouTube comments | Capture questions, confusion, objections and content demand |
| Broker communities | Identify competitor complaints and feature gaps |
| App/Play Store reviews | Find recurring product expectations and UX pain points |
| GitHub issues/search | Identify developer/API/algo trading needs |
| SEO keyword list | Align posts with search demand and discoverability |
| Nubra feature context | Avoid recommending posts for things Nubra cannot support |
| Nubra upcoming feature list | Plan launch, teaser and education content |

### Output Types

The module should generate different social/posting assets:

| Output | Example |
|---|---|
| Daily post ideas | “Why option sellers need strategy-level SL/TP” |
| Weekly content calendar | 5-7 post themes based on recent community signals |
| Feature education posts | Explain option chain filters, OI trader mode, scalper mode |
| Competitor-gap posts | Position Nubra against pain points seen in other broker communities |
| Lead magnet ideas | Calculators, checklists, templates, guides |
| Webinar ideas | Topics with repeated demand and high educational value |
| Creative briefs | Designer-ready brief for carousel/static/reel assets |
| Final post drafts | LinkedIn/X/Instagram-ready copy with approval status |

### Suggested Workflow

```text
Data collected by Beacon
        ↓
Insight engine identifies topics, pain points and feature demand
        ↓
Post recommendation engine creates ranked content ideas
        ↓
PM/Marketing reviews and approves
        ↓
Designer gets creative brief if visual is needed
        ↓
Final post copy + asset reviewed
        ↓
Approved post is published manually or through connected social APIs
```

### Recommendation Logic

Each post idea should be scored using:

| Metric | Meaning |
|---|---|
| Topic frequency | How often this topic appears across sources |
| Engagement strength | Upvotes, comments, likes, views, replies or review volume |
| Pain intensity | Whether users are complaining, confused or actively asking for a solution |
| Nubra relevance | Whether Nubra already has, is building or can credibly talk about this |
| Competitor gap | Whether competitors are weak in this area |
| SEO value | Whether the topic matches high-value keywords |
| Content fit | Whether the topic is suitable for social, webinar, blog or product education |

### Approval States

| State | Meaning |
|---|---|
| Suggested | AI generated the idea |
| Shortlisted | PM/Marketing selected it |
| Needs design | Requires visual/carousel/video asset |
| Draft ready | Copy is ready |
| Approved | Ready to publish |
| Published | Posted externally |
| Rejected | Not useful or not aligned |

### Posting Automation Levels

| Level | Description | Recommended phase |
|---|---|---|
| Level 1 | AI recommends topics only | MVP |
| Level 2 | AI creates draft copy and creative brief | MVP |
| Level 3 | Human approves final post | MVP |
| Level 4 | System schedules post after approval | Later |
| Level 5 | System auto-posts without approval | Not recommended initially |

### MVP Scope

For the first version, build:

- Social recommendation page inside Beacon
- Daily/weekly post idea generation
- Source-backed reason for each recommendation
- Nubra feature mapping
- Suggested post format: LinkedIn, X, Instagram, YouTube Shorts, webinar, blog
- Draft copy generation
- Designer creative brief generation
- Approval status tracking
- Export to Markdown/CSV

### Later Scope

After MVP:

- Social calendar view
- Scheduled publishing
- LinkedIn/X API integration
- Asset upload and approval
- Performance tracking after posting
- “What should we post today?” assistant
- “Turn this insight into a carousel brief” action

---

## 2. Figma Product Flow Review Intelligence

### Problem

The current product flow in the organization is:

```text
PM defines feature
        ↓
Designer creates Figma flow
        ↓
PM reviews design
        ↓
Developer builds it
```

The review stage is still manual. PMs need to check if the Figma flow matches the product intent, whether the UX is clear, whether UI is consistent, whether edge cases are missed and whether the design is ready for development.

Beacon can become a product-design review assistant that reviews uploaded Figma flows before they go to development.

### Product Goal

When a Figma file or exported screen flow is uploaded into the dashboard, the system should analyze the full user journey and return:

- UX issues
- UI consistency problems
- Missing states
- Flow gaps
- Copy problems
- Developer handoff gaps
- Product risks
- Recommendations before development

### Core Inputs

| Input | How it helps |
|---|---|
| Figma file/screens | Primary design source |
| Consecutive screen flow | Understand user journey, not isolated screens |
| PM feature brief | Check whether design matches intended product behavior |
| Nubra design system rules | Validate UI consistency |
| Nubra product context | Understand brokerage/trading-specific flows |
| Community insights | Check whether design addresses real user pain points |
| Upcoming feature list | Understand whether design is for new retail/app features |

### Review Areas

| Area | What AI should check |
|---|---|
| Flow clarity | Can the user understand what to do next? |
| Screen sequence | Are steps missing or out of order? |
| CTA consistency | Are primary/secondary actions clear and consistent? |
| Navigation | Can the user go back, cancel, edit or recover? |
| Error states | Are validation, failure and empty states covered? |
| Loading states | Are async states shown where needed? |
| Data visibility | Are key trading metrics visible at the right moment? |
| Risk communication | Are risky trading actions clearly explained? |
| UI consistency | Typography, spacing, color, components, icons |
| Product logic | Does the UI match actual order/trading behavior? |
| Dev handoff | Are edge cases, states and component rules clear? |

### Trading-Specific Review Checks

Because Nubra is a trading platform, generic UX review is not enough. The reviewer should also check:

- Is risk visible before order placement?
- Are margin, brokerage, charges and P&L implications clear?
- Are SL/TP and risk-reward flows understandable?
- Is option buyer/seller/OI trader/scalper mode behavior clear?
- Are option chain filters easy to discover and reset?
- Are strategy-level actions separated from leg-level actions?
- Are destructive actions confirmed?
- Is live market data freshness communicated?
- Are disabled states explained?
- Are regulatory/compliance-sensitive claims avoided?

### Suggested Workflow

```text
PM uploads feature brief and Figma flow
        ↓
System extracts screens, order and visible text
        ↓
AI reviews flow against product intent, Nubra context and UX rules
        ↓
System generates structured issue report
        ↓
PM/designer fixes Figma
        ↓
System re-runs review and compares improvements
        ↓
Design is approved for development
```

### Output Report Structure

| Section | Purpose |
|---|---|
| Summary | Overall readiness and biggest risks |
| Flow understanding | What the system thinks the flow is trying to do |
| Critical issues | Must-fix before development |
| UX recommendations | Flow, navigation, clarity and user action improvements |
| UI consistency issues | Visual/design-system level inconsistencies |
| Missing states | Empty, error, loading, confirmation and edge cases |
| Trading/product risks | Risk, order behavior, charges, P&L, margin and compliance gaps |
| Developer handoff checklist | What needs to be clarified before engineering |
| Final recommendation | Ready / needs changes / not ready |

### Severity Levels

| Severity | Meaning |
|---|---|
| Critical | Can cause wrong trade, wrong action, broken flow or compliance risk |
| High | Major UX/product clarity issue |
| Medium | Important improvement before development |
| Low | Polish or consistency issue |

### MVP Scope

For the first version, build:

- Upload Figma screenshots or exported frames
- Upload PM feature brief
- Select feature type: order flow, option chain, portfolio, analytics, onboarding, settings
- AI-generated review report
- Issue severity tagging
- Developer handoff checklist
- Export report as Markdown/PDF

### Later Scope

After MVP:

- Direct Figma API integration
- Auto-detect frame sequence
- Compare two Figma versions
- Comment directly on Figma frames
- Component/design-system consistency checks
- Jira/Linear ticket creation
- “Ready for development” checklist automation

---

## How These Two Modules Connect

These two modules should share the same intelligence layer.

| Shared Layer | Usage |
|---|---|
| Nubra product context | Know what Nubra has, is building and should avoid claiming |
| Community insights | Identify what users actually care about |
| Competitor data | Understand gaps and positioning |
| Feature catalog | Map social posts and Figma reviews to product areas |
| SEO keywords | Improve post discoverability and topic choice |
| Approval workflow | Human review before external publishing or development handoff |

The same data that tells us what users are asking for can also help validate whether new designs and social content are solving the right problems.

---

## Suggested Beacon Modules

### New Backend Areas

```text
community/social_recommend/
community/design_review/
community/approvals/
community/assets/
```

### New Dashboard Pages

```text
/social-recommendations
/content-calendar
/design-review
/design-review/:id
/approvals
```

### Possible Database Tables

```text
social_post_recommendations
social_post_drafts
social_post_approvals
design_review_projects
design_review_screens
design_review_findings
design_review_versions
approval_events
```

---

## Implementation Priority

### Phase 1: Planning and Data Mapping

- Define Nubra social content categories
- Define Figma/design review checklist
- Map existing Beacon data to post recommendation logic
- Create database schema draft

### Phase 2: Social Recommendation MVP

- Generate post ideas from existing Beacon insights
- Add social recommendation dashboard page
- Add approval statuses
- Generate copy and creative briefs

### Phase 3: Figma Review MVP

- Allow screenshot/flow upload
- Allow PM brief upload
- Generate UX/UI/product review report
- Add readiness score and handoff checklist

### Phase 4: Automation

- Add scheduling/export
- Add Figma API integration
- Add version comparison
- Add optional social posting APIs after approval

---

## Product Principle

Beacon should not become only a dashboard that shows what happened.

It should become a product and marketing intelligence system that helps the team decide:

- What should we build?
- What should we explain better?
- What should we post?
- What should we fix before development?
- What should we launch next?

The first version should keep humans in control, especially for social posting and product design approval. Automation should assist the team, not bypass review.
