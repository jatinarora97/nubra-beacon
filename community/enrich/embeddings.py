"""Embeddings (LLD-02 §7) — intfloat/multilingual-e5-small, CPU, 384-d, cosine.

The chatter is heavily Hinglish; an English-only model degrades near-dup and
feature clustering, hence the multilingual model. e5 convention: "query: " prefix.
Scope: canonical (duplicate_of IS NULL), non-noise items. Model lazy-loads once
per process (~470MB download on first ever use).
"""
from __future__ import annotations

import math

from community.clean.normalize import norm
from community.store import db

MODEL_NAME = "intfloat/multilingual-e5-small"
_model = None


def model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME, device="cpu")
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Normalized 384-d unit vectors for arbitrary texts (e5 'query: ' prefix).
    SentenceTransformer truncates to the model's 512-token window itself; the
    char cap just avoids tokenizing megabyte pastes."""
    prepped = ["query: " + norm(t)[:2000] for t in texts]
    vecs = model().encode(prepped, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vecs]


def to_vec(v: list[float]) -> str:
    """pgvector literal (cast with ::vector in SQL)."""
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


def from_vec(s: str) -> list[float]:
    return [float(x) for x in s.strip("[]").split(",")]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def embed_pending(limit: int = 5000, chunk: int = 64) -> int:
    """Embed canonical non-noise enriched items that lack an embedding row.
    Idempotent + self-healing: whatever enrichment landed and wasn't embedded
    yet (any prior run, any transport) gets picked up here."""
    rows = db.query(
        """
        SELECT ie.item_id, ie.ingested_at, si.text
        FROM item_enrichment ie
        JOIN social_items si ON si.item_id = ie.item_id
        LEFT JOIN item_embeddings emb ON emb.item_id = ie.item_id
        WHERE NOT ie.is_noise AND si.duplicate_of IS NULL AND emb.item_id IS NULL
        ORDER BY ie.ingested_at
        LIMIT %s
        """,
        (limit,),
    )
    done = 0
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        vecs = embed_texts([r["text"] for r in part])
        db.executemany(
            "INSERT INTO item_embeddings (item_id, ingested_at, embedding, model) "
            "VALUES (%s, %s, %s::vector, %s) ON CONFLICT (item_id, ingested_at) DO NOTHING",
            [(r["item_id"], r["ingested_at"], to_vec(v), MODEL_NAME)
             for r, v in zip(part, vecs)],
        )
        done += len(part)
    return done
