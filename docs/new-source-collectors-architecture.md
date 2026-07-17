# New Source Collectors Architecture

## Purpose

This change extends Beacon with four source families while preserving the
existing Reddit and X pipeline:

- YouTube videos and comments
- GitHub public issues
- Public broker communities
- Apple App Store and Google Play reviews

The collectors are additive. They use Beacon's existing storage, enrichment,
aggregation, recommendation, API, and dashboard layers.

## Data Flow

```text
community/config/registry.yaml
        |
community/scrape/extra_sources.py
        |
source-specific collector
        |
SocialItem validation
        |
existing authors + social_items tables
        |
existing clean -> enrich -> aggregate -> score -> recommend pipeline
        |
existing dashboard views + Explore source filters + Source health
```

## Compatibility Contract

The current Reddit and X collectors are not replaced or rewritten.

Each add-on collector is:

- controlled by its own `enabled` setting;
- run behind an independent exception boundary;
- converted to the existing `SocialItem` contract;
- inserted idempotently on `(source, external_id)`;
- recorded in the existing `pipeline_state` table;
- allowed to fail without failing Reddit, X, or another add-on source.

Migration `0010_extra_source_types.sql` only widens existing database check
constraints. It does not remove or rename tables, columns, or current values.

## Source Modules

| Source | Module | Stored content |
|---|---|---|
| YouTube | `community/scrape/youtube.py` | Video title, description, view/like/comment counts, and public top-level comments |
| GitHub | `community/scrape/github_public.py` | Public issues matching trading API, market data, automation, SDK, and broker queries |
| Broker communities | `community/scrape/broker_communities.py` | Public Discourse/NodeBB topics and replies; selected public broker-site pages discovered from sitemaps |
| App reviews | `community/scrape/app_reviews.py` | Apple public RSS reviews when an app ID is configured and Google Play public reviews when a package is configured |
| Orchestrator | `community/scrape/extra_sources.py` | Isolation, storage, counters, and pipeline-state updates |

## Configuration and Credentials

All source settings are in `community/config/registry.yaml`. A source can be
turned off independently by setting `enabled: false`.

| Source | Credential |
|---|---|
| YouTube | `YOUTUBE_API_KEY` is required |
| GitHub | `GITHUB_TOKEN` is optional but recommended for higher rate limits |
| Broker communities | No credential |
| App stores | No credential for the current public endpoints |

Secrets belong in `.env` or the deployment secret store and must never be added
to `registry.yaml` or committed.

The Google Play collector's zero-transitive-dependency package is isolated in
`requirements-extra-sources.txt`. The API image installs it after Beacon's
existing requirements so the large main dependency layer remains cacheable.

## Quality Controls

YouTube comments have minimum-length and deny-term filters. Results retain the
search partition (`retail`, `api_algo`, or `competitors`) in `raw.partition`.

GitHub applies an explicit allow/deny relevance gate. The matching terms,
minimum score, query, repository, labels, and relevance evidence are retained
in `raw`.

Community collectors preserve broker and platform metadata. Individual forum
failures are skipped so another community can still be collected.

App-review rows retain store, app, broker, rating, version, likes, and developer
reply metadata where the public store supplies it.

## Operational Visibility

`GET /api/v1/source-health` reports configuration, credential readiness,
last-run state, latest error, and stored row count for all six source families.
The dashboard exposes the same information at `/source-health`.

Explore supports source filters for YouTube, GitHub, broker communities, and
app reviews. All other existing views continue to consume the shared enriched
data without source-specific rewrites.

## Verification

Fetch-only smoke tests do not write to PostgreSQL:

```bash
python scripts/test_collectors_fetch_only.py
python scripts/test_collectors_fetch_only.py --source github
python scripts/test_collectors_fetch_only.py --source youtube
python scripts/test_collectors_fetch_only.py --source broker_communities
python scripts/test_collectors_fetch_only.py --source app_reviews
```

Runtime and credential diagnostics:

```bash
python scripts/source_health_check.py
```

The database-backed integration is exercised by the normal scrape stage:

```bash
./cm stage scrape
```

On Windows, use the project virtual-environment Python:

```powershell
.\.venv\Scripts\python.exe .\runner.py stage scrape
```
