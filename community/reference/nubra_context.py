"""Editable Nubra context loader.

The source of truth lives in:
    data/nubra_context/nubra_context.yaml

Only a subset of that rich context is currently published into the existing
`nubra_features` table. The rest is intentionally kept in YAML so product,
marketing and design teams can review and update it without changing code.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTEXT_PATH = REPO_ROOT / "data" / "nubra_context" / "nubra_context.yaml"


def load_context(path: str | Path | None = None) -> dict[str, Any]:
    context_path = Path(path) if path else DEFAULT_CONTEXT_PATH
    if not context_path.exists():
        raise FileNotFoundError(f"Nubra context file not found: {context_path}")
    with context_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Nubra context must be a YAML object: {context_path}")
    return data


def feature_rows(path: str | Path | None = None) -> tuple[str, list[tuple[str, str, str, str, list[str]]]]:
    """Return rows compatible with `nubra_features`.

    Shape:
        (version, [(feature, description, status, category, seo_keywords), ...])
    """
    data = load_context(path)
    version = str(data.get("version") or "nubra-context-v1")
    features = data.get("features") or []
    if not isinstance(features, list) or not features:
        raise ValueError("Nubra context must contain a non-empty `features` list")

    rows: list[tuple[str, str, str, str, list[str]]] = []
    seen: set[str] = set()
    for idx, item in enumerate(features, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Feature #{idx} must be an object")
        name = str(item.get("name") or "").strip()
        description = str(item.get("description") or "").strip()
        status = str(item.get("status") or "").strip().lower()
        category = str(item.get("category") or "").strip()
        keywords_raw = item.get("seo_keywords") or []
        if not name or not description:
            raise ValueError(f"Feature #{idx} needs name and description")
        if status not in {"live", "upcoming"}:
            raise ValueError(f"Feature `{name}` has invalid status `{status}`")
        if name.lower() in seen:
            raise ValueError(f"Duplicate feature name in Nubra context: {name}")
        seen.add(name.lower())
        if not isinstance(keywords_raw, list):
            raise ValueError(f"Feature `{name}` seo_keywords must be a list")
        keywords = [str(k).strip() for k in keywords_raw if str(k).strip()]
        rows.append((name, description, status, category, keywords))
    return version, rows


def summary(path: str | Path | None = None) -> dict[str, Any]:
    data = load_context(path)
    version, rows = feature_rows(path)
    by_status: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for _, _, status, category, _ in rows:
        by_status[status] = by_status.get(status, 0) + 1
        by_category[category or "uncategorized"] = by_category.get(category or "uncategorized", 0) + 1
    return {
        "version": version,
        "features": len(rows),
        "by_status": by_status,
        "by_category": dict(sorted(by_category.items())),
        "personas": [p.get("name") for p in data.get("personas", []) if isinstance(p, dict)],
        "surfaces": data.get("brand", {}).get("product_surfaces", []),
    }

