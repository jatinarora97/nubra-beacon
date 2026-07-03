"""Canonical item + SQLite store. Self-contained, no external repo deps."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "pulse.db"

_WS = re.compile(r"\s+")


def _norm_text(text: str) -> str:
    return _WS.sub(" ", (text or "").strip().lower())


def content_hash(text: str) -> str:
    return hashlib.sha256(_norm_text(text).encode("utf-8")).hexdigest()


@dataclass
class RawItem:
    source: str                 # 'reddit' | 'telegram' | 'discourse:zerodha' | ...
    source_type: str            # 'post' | 'comment' | 'message' | ...
    external_id: str
    text: str
    created_at: datetime
    author: str = "anon"
    url: str | None = None
    engagement: dict = field(default_factory=lambda: {"score": 0, "replies": 0})
    raw: dict = field(default_factory=dict)

    @property
    def hash(self) -> str:
        return content_hash(self.text)

    def to_row(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.astimezone(timezone.utc).isoformat()
        d["engagement"] = json.dumps(self.engagement)
        d["raw"] = json.dumps(self.raw, default=str)
        d["content_hash"] = self.hash
        return d


SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  content_hash TEXT,
  source       TEXT,
  source_type  TEXT,
  external_id  TEXT,
  author       TEXT,
  text         TEXT,
  url          TEXT,
  created_at   TEXT,
  engagement   TEXT,
  raw          TEXT,
  -- enrichment (filled by classify stage)
  audience     TEXT,
  topic        TEXT,
  sentiment    TEXT,
  is_noise     INTEGER,
  ingested_at  TEXT,
  PRIMARY KEY (source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_items_hash ON items(content_hash);
CREATE INDEX IF NOT EXISTS idx_items_created ON items(created_at);

CREATE TABLE IF NOT EXISTS briefs (
  brief_date TEXT PRIMARY KEY,
  payload    TEXT,
  created_at TEXT
);
"""


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def upsert_items(con: sqlite3.Connection, items: list[RawItem]) -> int:
    """Append newly-fetched items to the persistent store.

    De-duplication happens at two levels so we never save the same data twice:
      1. (source, external_id) — re-fetching the same post/comment is a no-op (PK).
      2. content_hash — identical text already on disk (even cross-posted) is skipped.
    Returns the count of genuinely new rows written.
    """
    now = datetime.now(timezone.utc).isoformat()
    # Pull every hash already on disk once; track within-batch dupes too.
    seen = {r[0] for r in con.execute("SELECT content_hash FROM items")}
    inserted = 0
    for it in items:
        h = it.hash
        if h in seen:
            continue
        row = {**it.to_row(), "ingested_at": now}
        cur = con.execute(
            """INSERT OR IGNORE INTO items
               (content_hash, source, source_type, external_id, author, text, url,
                created_at, engagement, raw, ingested_at)
               VALUES (:content_hash, :source, :source_type, :external_id, :author,
                       :text, :url, :created_at, :engagement, :raw, :ingested_at)""",
            row,
        )
        if cur.rowcount:
            inserted += 1
            seen.add(h)
    con.commit()
    return inserted


def _row_to_item(row: sqlite3.Row) -> RawItem:
    try:
        created = datetime.fromisoformat(row["created_at"])
    except Exception:
        created = datetime.now(timezone.utc)
    try:
        engagement = json.loads(row["engagement"]) if row["engagement"] else {}
    except Exception:
        engagement = {}
    try:
        raw = json.loads(row["raw"]) if row["raw"] else {}
    except Exception:
        raw = {}
    return RawItem(
        source=row["source"], source_type=row["source_type"],
        external_id=row["external_id"], text=row["text"] or "",
        author=row["author"] or "anon", url=row["url"],
        created_at=created, engagement=engagement, raw=raw,
    )


def load_items(con: sqlite3.Connection, days: int | None = None,
               sources: list[str] | None = None) -> list[RawItem]:
    """Read the accumulated store back into RawItems.

    This is the working set the pipeline runs on — so each run sees freshly-scraped
    data plus everything stored on previous runs (within the last-N-days window).
    """
    clauses, params = [], []
    if days and days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        clauses.append("created_at >= ?")
        params.append(cutoff)
    if sources:
        clauses.append(f"source IN ({','.join('?' * len(sources))})")
        params.extend(sources)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = con.execute(
        f"SELECT * FROM items{where} ORDER BY created_at DESC", params
    ).fetchall()
    return [_row_to_item(r) for r in rows]


def store_counts(con: sqlite3.Connection) -> dict:
    """Totals for the persistent store (for the dashboard header)."""
    total = con.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    by_src = {r[0]: r[1] for r in con.execute(
        "SELECT source, COUNT(*) FROM items GROUP BY source")}
    return {"total": total, "by_source": by_src}
