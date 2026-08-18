"""Publish the canonical grounding catalog (data/grounding_context_v2.json —
the 31 features synthesized from the real product doc, 2026-07-17) as the
current nubra_features version. Idempotent-safe: skips if the live catalog
already matches; otherwise publishes the next version and flips is_current.

    docker compose exec api python scripts/publish_grounding.py

Background: prod went live on assumed-v0 (July go-live decision); the
context-v2 swap was applied locally but never on prod — found 2026-08-18 via
the beacon-API validator (/grounding showed assumed-v0, 10 features).
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.api.read_api import features_catalog, publish_features_catalog

CANON = pathlib.Path(__file__).resolve().parent.parent / "data" / "grounding_context_v2.json"


def main() -> None:
    features = json.loads(CANON.read_text())
    current = features_catalog()
    have = {(f["feature"], f["description"], f["status"]) for f in current["features"]}
    want = {(f["feature"], f["description"], f["status"]) for f in features}
    print(f"current: {current['version']} ({len(current['features'])} features)")
    if have == want:
        print("already matches the canonical catalog — nothing to publish")
        return
    out = publish_features_catalog({"features": features},
                                   x_auth_request_email="publish_grounding.py")
    print(f"published: {out.get('version')} ({len(features)} features)")


if __name__ == "__main__":
    main()
