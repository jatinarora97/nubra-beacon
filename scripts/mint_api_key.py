"""Mint a beacon-API key from the shell (headless fallback; the dashboard's
API-access page is the normal route).

    docker compose exec api python scripts/mint_api_key.py "growth-team-mcp"

Prints the secret ONCE; only its sha256 is stored. Revoke via the dashboard
or: UPDATE api_keys SET revoked_at=now() WHERE key_id=<id>;
"""
from __future__ import annotations

import hashlib
import pathlib
import secrets
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.store import db


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        sys.exit("usage: mint_api_key.py <label — who is this key for?>")
    label = sys.argv[1].strip()
    secret = "nbk_" + secrets.token_urlsafe(32)
    row = db.one(
        "INSERT INTO api_keys (key_hash, label, created_by) "
        "VALUES (%s, %s, 'cli') RETURNING key_id",
        (hashlib.sha256(secret.encode()).hexdigest(), label))
    print(f"key_id {row['key_id']} — {label}")
    print(f"SECRET (shown once, store it now): {secret}")


if __name__ == "__main__":
    main()
