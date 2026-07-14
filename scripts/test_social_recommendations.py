"""No-DB smoke test for social recommendation engine."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from community.reference.nubra_context import feature_rows
from community.social_recommend.engine import build_recommendations
from community.social_recommend.models import FeatureContext, SourceSignal


def _features() -> list[FeatureContext]:
    _, rows = feature_rows()
    return [
        FeatureContext(feature=name, description=desc, status=status, category=category, seo_keywords=kws)
        for name, desc, status, category, kws in rows
    ]


def _signals() -> list[SourceSignal]:
    samples = [
        ("youtube", "comment", "Need option chain filters for OI buildup, IV change, bid ask spread and volume spike. Current apps are too noisy.", 7.2),
        ("community_forum", "post", "Please bring strategy level stop loss and target. Managing legs separately is confusing for straddles.", 5.8),
        ("github", "issue", "Broker API websocket disconnects and no clear sandbox for paper trading before live execution.", 6.4),
        ("reddit", "post", "Scalping needs one click order, bid ask on chart, fast modify order and best fill visibility.", 4.9),
        ("app_review", "review", "Watchlist should auto refresh and allow more stocks. I track many stocks and F&O instruments.", 3.1),
    ]
    return [
        SourceSignal(source=source, source_type=stype, text=text, url=f"https://example.com/{idx}", engagement_score=score)
        for idx, (source, stype, text, score) in enumerate(samples, start=1)
    ]


def main() -> int:
    recs = build_recommendations(_signals(), _features(), max_count=10)
    print(f"generated={len(recs)}")
    for rec in recs:
        print("\n---")
        print(f"{rec.priority_score:.1f} | {rec.title}")
        print(f"persona={rec.target_persona} platform={rec.platform} format={rec.format_family}")
        print(rec.reason)
        print("mapped:", [m["feature"] for m in rec.mapped_features[:3]])
        print("draft:", rec.draft_copy.splitlines()[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

