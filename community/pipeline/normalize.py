"""Text normalization for hashing/minhash only — stored `text` stays raw (LLD-02 §5.1)."""
from __future__ import annotations

import re
import unicodedata

_URL = re.compile(r"https?://\S+|(?:t\.co|redd\.it)/\S+", re.I)
_MENTION = re.compile(r"(?:^|\s)(@\w+|u/\w+|/u/\w+)")
_WS = re.compile(r"\s+")


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = t.lower()
    t = _URL.sub(" ", t)
    t = _MENTION.sub(" ", t)
    t = _WS.sub(" ", t)
    return t.strip()
