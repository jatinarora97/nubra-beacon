"""Stage ② DEDUP — link, never drop (LLD-02 §5).

Exact: content_hash match in trailing 14d. Near: MinHash(num_perm=128) over 3-word
shingles, LSH threshold 0.7, Jaccard confirm ≥ 0.8. Canonical = earliest ingested_at;
chains flattened one hop. Watermark on ingested_at (stage 'dedup').
"""
from __future__ import annotations

from datetime import timedelta

from datasketch import LeanMinHash, MinHash, MinHashLSH

from community.pipeline.normalize import norm
from community.store import db
from community.store import repositories as repo

NUM_PERM = 128
LSH_THRESHOLD = 0.7
JACCARD_CONFIRM = 0.8
WINDOW_DAYS = 14


def _minhash(text_norm: str) -> MinHash | None:
    tokens = text_norm.split()
    if len(tokens) < 3:
        return None  # too short for shingles; exact-hash only
    mh = MinHash(num_perm=NUM_PERM)
    for i in range(len(tokens) - 2):
        mh.update(" ".join(tokens[i:i + 3]).encode("utf-8"))
    return mh


def _serialize(mh: MinHash) -> bytes:
    lean = LeanMinHash(mh)
    buf = bytearray(lean.bytesize())
    lean.serialize(buf)
    return bytes(buf)


def run(**_) -> dict:
    state = repo.get_state("dedup") or {}
    wm = state.get("watermark")

    new_items = db.query(
        """
        SELECT item_id, text, content_hash, ingested_at
        FROM social_items
        WHERE (%(wm)s::timestamptz IS NULL OR ingested_at > %(wm)s)
        ORDER BY ingested_at, item_id
        """,
        {"wm": wm},
    )
    if not new_items:
        return {"checked": 0, "exact_dupes": 0, "near_dupes": 0}

    window_start = min(r["ingested_at"] for r in new_items) - timedelta(days=WINDOW_DAYS)
    # Only items strictly before the watermark are "existing"; on the first run
    # (wm NULL) there are none — new items index each other as they stream through.
    existing = db.query(
        """
        SELECT item_id, content_hash, minhash_sig, duplicate_of, ingested_at
        FROM social_items
        WHERE ingested_at >= %s AND %s::timestamptz IS NOT NULL AND ingested_at <= %s
        ORDER BY ingested_at, item_id
        """,
        (window_start, wm, wm),
    )

    # In-memory indexes over the window (a few thousand rows locally).
    by_hash: dict[str, int] = {}            # content_hash -> earliest canonical item_id
    canonical_of: dict[int, int] = {}       # item_id -> its canonical (flattening)
    lsh = MinHashLSH(threshold=LSH_THRESHOLD, num_perm=NUM_PERM)
    sigs: dict[int, LeanMinHash] = {}

    def canon(item_id: int) -> int:
        return canonical_of.get(item_id, item_id)

    for r in existing:
        if r["duplicate_of"]:
            canonical_of[r["item_id"]] = r["duplicate_of"]
        by_hash.setdefault(r["content_hash"], canon(r["item_id"]))
        if r["minhash_sig"]:
            lean = LeanMinHash.deserialize(bytes(r["minhash_sig"]))
            sigs[r["item_id"]] = lean
            lsh.insert(str(r["item_id"]), lean)

    stats = {"checked": 0, "exact_dupes": 0, "near_dupes": 0}
    updates: list[tuple] = []  # (minhash_sig, duplicate_of, item_id)
    max_ts = wm

    for r in new_items:
        stats["checked"] += 1
        max_ts = r["ingested_at"] if max_ts is None else max(max_ts, r["ingested_at"])
        text_norm = norm(r["text"])
        mh = _minhash(text_norm)
        sig_bytes = _serialize(mh) if mh else None
        duplicate_of = None

        kind = None
        if r["content_hash"] in by_hash and by_hash[r["content_hash"]] != r["item_id"]:
            duplicate_of = by_hash[r["content_hash"]]
            kind = "exact_dupes"
        elif mh is not None:
            lean = LeanMinHash(mh)
            best = None
            for key in lsh.query(lean):
                cand_id = int(key)
                if cand_id != r["item_id"] and lean.jaccard(sigs[cand_id]) >= JACCARD_CONFIRM:
                    cand = canon(cand_id)
                    if best is None or cand < best:
                        best = cand
            if best is not None and best != r["item_id"]:
                duplicate_of = best
                kind = "near_dupes"

        if kind:
            stats[kind] += 1
        if duplicate_of:
            canonical_of[r["item_id"]] = duplicate_of
        else:
            by_hash.setdefault(r["content_hash"], r["item_id"])
        if mh is not None:
            lean = LeanMinHash(mh)
            sigs[r["item_id"]] = lean
            lsh.insert(str(r["item_id"]), lean)

        updates.append((sig_bytes, duplicate_of, r["item_id"]))

    db.executemany(
        "UPDATE social_items SET minhash_sig=%s, duplicate_of=%s WHERE item_id=%s",
        updates,
    )
    repo.advance_state("dedup", "", watermark=max_ts, items=stats["checked"])
    return stats
