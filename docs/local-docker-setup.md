# Local Docker/Postgres Setup

## Purpose

Beacon uses Postgres with pgvector for local storage, enrichment, aggregation and dashboard reads.

The new collectors can be fetch-tested without Docker, but full ingest requires Postgres.

---

## 1. Install Docker Desktop

Install Docker Desktop for Windows, then restart if prompted.

Verify:

```powershell
docker --version
docker compose version
```

---

## 2. Create `.env`

Copy:

```text
community/config/env.example
```

to:

```text
.env
```

Minimum local values:

```env
DB_URL=postgresql://community:community@localhost:5544/nubra_community
ANTHROPIC_API_KEY=
TWITTERAPI_IO_KEY=
YOUTUBE_API_KEY=
GITHUB_TOKEN=
```

Notes:

- `ANTHROPIC_API_KEY` is required for enrichment/draft stages.
- `YOUTUBE_API_KEY` is required only if YouTube source is enabled.
- `GITHUB_TOKEN` is optional but improves GitHub search rate limits.

---

## 3. Start Postgres

From repo root:

```powershell
docker compose up -d postgres
```

Check:

```powershell
docker ps
```

---

## 4. Run migrations and seed context

```powershell
python runner.py migrate
python scripts\seed_features.py
python scripts\seed_sources.py
```

Validate the Nubra context without DB writes:

```powershell
python scripts\seed_features.py --dry-run
```

---

## 5. Test collectors before DB ingest

These do not write to DB:

```powershell
python scripts\source_health_check.py
python scripts\test_collectors_fetch_only.py
```

Run a single source:

```powershell
python scripts\test_collectors_fetch_only.py --source github
python scripts\test_collectors_fetch_only.py --source broker_communities
python scripts\test_collectors_fetch_only.py --source youtube
python scripts\test_collectors_fetch_only.py --source app_reviews
```

---

## 6. Enable new sources carefully

New optional sources are disabled by default in:

```text
community/config/registry.yaml
```

Enable one source at a time:

```yaml
sources:
  github:
    enabled: true
```

Recommended order:

1. GitHub
2. Broker communities
3. App reviews/listing snapshots
4. YouTube

---

## 7. Run pipeline

After enabling a source:

```powershell
python runner.py stage scrape
python runner.py stage clean
python runner.py stage enrich
python runner.py stage aggregate
python runner.py stage recommend
python runner.py stage social
```

For all local stages:

```powershell
python runner.py run-local
```

Inspect generated social post recommendations through the API:

```text
GET http://127.0.0.1:8400/api/v1/social-recommendations
```

---

## 8. Run API and dashboard

API:

```powershell
python -m uvicorn community.api.main:app --host 127.0.0.1 --port 8400
```

Frontend:

```powershell
cd webapp
npm install
npm run dev -- -p 3001
```

Open:

```text
http://127.0.0.1:3001
```

---

## Troubleshooting

### Docker command not found

Docker Desktop is not installed or not in PATH.

### DB health says unavailable

Start Postgres:

```powershell
docker compose up -d postgres
```

### YouTube source skipped

Set:

```env
YOUTUBE_API_KEY=
```

### GitHub source rate limited

Set:

```env
GITHUB_TOKEN=
```
