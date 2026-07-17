"""Fresh-database smoke test for the optional social recommendation module.

Run only against a disposable database:
    DB_URL=postgresql://... python scripts/smoke_social_recommendations.py
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from community.api.read_api import app
from community.social_recommend import service
from community.store import db, repositories as repo


def _sample(source: str, source_type: str, external_id: str, text: str, score: int) -> int:
    author = repo.upsert_author(source, f"smoke_{source}")
    item_id = repo.insert_item_if_absent({
        "source": source,
        "source_type": source_type,
        "external_id": external_id,
        "parent_id": None,
        "thread_id": external_id,
        "author_id": author,
        "text": text,
        "lang": "en",
        "url": f"https://example.invalid/{external_id}",
        "content_hash": hashlib.sha256(text.lower().encode()).hexdigest(),
        "engagement": {"score": score},
        "raw": {"smoke": True},
        "created_at": datetime.now(timezone.utc),
    })
    assert item_id is not None
    row = db.one("SELECT ingested_at FROM social_items WHERE item_id=%s", (item_id,))
    topic = "api_experience" if source == "github" or "API" in text else "options_analytics"
    db.execute(
        """
        INSERT INTO item_enrichment
            (item_id, ingested_at, audience, intent, topic_key, sentiment, model)
        VALUES (%s,%s,'active_trader','feature_request',%s,0,'smoke-test')
        """,
        (item_id, row["ingested_at"], topic),
    )
    return item_id


def main() -> None:
    if "localhost" not in os.environ.get("DB_URL", ""):
        raise SystemExit("Refusing to run: DB_URL must point to a disposable localhost database")
    retail_id = _sample(
        "reddit", "post", "smoke-retail",
        "Need OI percentile, IV change and bid ask filters in the option chain", 42,
    )
    _sample(
        "app_review", "review", "smoke-brokerage",
        "Brokerage is confusing for option traders who trade several lots", 18,
    )
    api_id = _sample(
        "github", "issue", "smoke-api",
        "Websocket reconnect and historical candle API date range need clearer documentation", 35,
    )
    _sample(
        "youtube", "comment", "smoke-uat",
        "Is there a sandbox or UAT where I can test order APIs before going live", 12,
    )

    ready = service.preview(30)
    assert ready["items"] == 4
    assert ready["retail_items"] >= 1
    assert ready["api_items"] >= 1

    # With no key this must become a local skipped run, never an exception.
    result = service.run(30, force=True)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        assert result["status"] == "skipped"

    # Exercise the complete path without spending tokens or requiring a key.
    fake_response = {
        "recommendations": [
            {
                "recommendation_key": "option-chain-filters",
                "segment": "retail",
                "platform": "instagram",
                "format": "carousel",
                "title": "Filter the option-chain noise",
                "hook": "An option chain should help you narrow the market, not add more noise.",
                "body": "A useful options workflow starts by choosing the data that matters to your setup. Nubra is developing saved option-chain modes with filters for OI, IV, volume, Greeks and bid-ask spread.",
                "cta": "Which option-chain filter do you use first?",
                "hashtags": ["#OptionsTrading", "#ProductEducation"],
                "feature_ids": ["option_chain_filters"],
                "evidence_item_ids": [retail_id],
                "rationale": "Retail evidence asks for OI, IV and spread filters.",
                "visual_brief": "Five-frame carousel showing the problem, filter families and saved mode.",
                "recommended_timing": "Weekday after market hours",
                "priority_score": 86,
            },
            {
                "recommendation_key": "api-uat",
                "segment": "api",
                "platform": "linkedin",
                "format": "product_demo",
                "title": "Test before going live",
                "hook": "Trading integrations need a safe place to fail before production.",
                "body": "Nubra UAT gives API developers an environment to test integration and order workflows before production use. Pair it with clear websocket and historical-data documentation for a safer path from first request to live automation.",
                "cta": "What is the first workflow you test in a broker sandbox?",
                "hashtags": ["#TradingAPI", "#DeveloperExperience"],
                "feature_ids": ["nubra_uat", "reliable_websocket"],
                "evidence_item_ids": [api_id],
                "rationale": "Developer evidence asks for sandbox and API reliability clarity.",
                "visual_brief": "Product demo flow: connect, test an order workflow, inspect response, move to live.",
                "recommended_timing": "Tuesday or Wednesday morning",
                "priority_score": 90,
            },
        ]
    }
    old_settings, old_complete, old_compliance = (
        service.settings, service.complete, service.compliance_check
    )
    service.settings = SimpleNamespace(
        draft_model="claude-smoke-test", anthropic_api_key="smoke-key"
    )
    service.complete = lambda *_args, **_kwargs: (json.dumps(fake_response), {"calls": 1})
    service.compliance_check = lambda *_args, **_kwargs: (True, [])
    try:
        generated = service.run(30, strict=True, force=True)
    finally:
        service.settings, service.complete, service.compliance_check = (
            old_settings, old_complete, old_compliance
        )
    assert generated["status"] == "succeeded"
    assert generated["recommendations"] == 2

    client = TestClient(app)
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/social-recommendations/status").status_code == 200
    assert client.get("/api/v1/social-recommendations/preview").status_code == 200
    listed = client.get("/api/v1/social-recommendations")
    assert listed.status_code == 200
    assert len(listed.json()) == 2
    print({
        "preview": ready,
        "missing_key_generation": result,
        "mocked_generation": generated,
        "api": "ok",
    })


if __name__ == "__main__":
    main()
