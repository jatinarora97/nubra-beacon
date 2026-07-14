# Nubra Context Layer Guide

## Purpose

The Nubra context layer is the product grounding source for Beacon.

It tells Beacon:

- what Nubra already has
- what is upcoming
- which personas each feature is for
- which product surface it belongs to
- which claims are safe
- which keywords should be used for matching, scraping and recommendations
- which UX/design rules should be checked in future design-review workflows

This prevents Beacon from giving generic or hallucinated recommendations.

---

## Source File

Editable source:

```text
data/nubra_context/nubra_context.yaml
```

This file should be treated as the human-readable product context file.

Product, marketing, design or developer teams can open and update it directly.

---

## Current Contents

The current context file contains:

- Brand positioning
- Product surfaces
- Audience/persona segments
- Claim guardrails
- Persona definitions
- Live and upcoming Nubra features
- SEO/search keywords
- Design review rules
- Social content categories

Current validated catalog:

```text
50 total features
13 live features
37 upcoming features
```

---

## How Beacon Uses It

### 1. Feature Grounding

The existing `nubra_features` database table is still the runtime grounding table used by the app.

The YAML file is the editable source.

The seed script publishes the feature subset from YAML into:

```text
nubra_features
```

### 2. Social Recommendations

Future social-posting intelligence should use the context file to decide:

- whether Nubra can talk about a topic
- whether the feature is live or upcoming
- which persona the post is for
- which SEO keywords fit naturally
- whether the output should be a post, webinar, lead magnet or help article

### 3. Figma / Design Review

Future design review should use the context file to check:

- whether the flow matches the intended feature
- whether the right persona behavior is present
- whether trading risks are shown clearly
- whether UI copy matches approved terminology
- whether missing states exist before development handoff

---

## Updating the Context

Edit:

```text
data/nubra_context/nubra_context.yaml
```

Then validate without writing to DB:

```powershell
.\.venv\Scripts\python.exe scripts\seed_features.py --dry-run
```

If validation passes and Postgres is running, publish it:

```powershell
.\.venv\Scripts\python.exe scripts\seed_features.py
```

This will:

1. Read the YAML file.
2. Validate feature names, descriptions, statuses and keywords.
3. Insert the feature rows into `nubra_features`.
4. Mark this version as the active/current catalog.

---

## Adding a New Feature

Add a new item under:

```yaml
features:
```

Required fields:

```yaml
- name: Example feature
  status: upcoming
  category: analytics
  surfaces: [Mobile app, Web trading platform]
  personas: [Option Buyer, Option Seller]
  description: Short product-approved explanation.
  seo_keywords: [keyword one, keyword two]
```

Supported status values:

```text
live
upcoming
```

If a feature is experimental, internal-only or not approved for public claims, keep it in the YAML with careful notes, but do not phrase it as live in social/draft outputs.

---

## Important Rule

Any generated claim about Nubra should be grounded in this context.

If a capability is not in this file, Beacon should treat it as:

- a possible opportunity
- an internal idea
- a market expectation
- or a recommendation

It should not claim Nubra already has it.

