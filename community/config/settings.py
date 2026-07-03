"""Runtime settings: .env + community/config/registry.yaml.

MODE=local (default here) vs prod — local mode:
  - delivery writes markdown files to OUT_DIR instead of Slack/email
  - X live fetch capped at registry x_live_cap (10); CSV backfill is the main X source
  - enrichment runs sync (no Batch API); embeddings skipped (slug feature keys)
"""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field

import yaml
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")


def _registry() -> dict:
    p = pathlib.Path(__file__).parent / "registry.yaml"
    return yaml.safe_load(p.read_text()) if p.exists() else {}


@dataclass(frozen=True)
class Settings:
    mode: str = os.getenv("MODE", "local")
    db_url: str = os.getenv(
        "DB_URL", "postgresql://community:community@localhost:5544/nubra_community"
    )
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    twitterapi_key: str = os.getenv("TWITTERAPI_IO_KEY", "")
    out_dir: pathlib.Path = ROOT / os.getenv("OUT_DIR", "out/messages")
    enrich_model: str = os.getenv("ENRICH_MODEL", "claude-haiku-4-5")
    draft_model: str = os.getenv("DRAFT_MODEL", "claude-sonnet-4-6")
    registry: dict = field(default_factory=_registry)

    @property
    def is_local(self) -> bool:
        return self.mode == "local"


settings = Settings()
