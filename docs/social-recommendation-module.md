# Social Recommendation Module

## Purpose

The social recommendation module turns Beacon data into practical social media
post recommendations for Nubra.

It is not an auto-posting system. Every recommendation starts in `suggested`
status and requires human review before publishing.

---

## Inputs

- Reddit discussions
- YouTube videos/comments
- GitHub API/algo signals
- Broker communities
- App/Play Store signals
- Existing Beacon enrichment
- Nubra context layer

---

## Outputs

Each recommendation contains:

- title
- summary
- target persona
- suggested platform
- format family
- mapped Nubra feature
- source evidence
- reason
- post angle
- deterministic draft copy
- designer creative brief
- approval status

---

## Backend Files

```text
community/social_recommend/models.py
community/social_recommend/engine.py
community/social_recommend/generate.py
community/social_recommend/prompts/
```

Migration:

```text
migrations/0011_social_recommendations.sql
```

No-DB test:

```text
scripts/test_social_recommendations.py
```

---

## Run Without Docker

```powershell
python scripts\test_social_recommendations.py
```

This uses sample signals and the editable Nubra context file.

---

## Run With Docker/Postgres

After Docker/Postgres is installed:

```powershell
python runner.py migrate
python scripts\seed_features.py
python runner.py stage scrape
python runner.py stage clean
python runner.py stage enrich
python runner.py stage aggregate
python runner.py stage social
```

---

## Approval Statuses

```text
suggested
shortlisted
needs_design
draft_ready
approved
published
rejected
```

---

## Product Rule

Social recommendations must start from real user/community signals.

Nubra claims must be grounded in the active Nubra context. Upcoming features
should be framed as upcoming/planned and never as already launched.

