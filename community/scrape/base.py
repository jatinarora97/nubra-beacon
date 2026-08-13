"""SocialItem contract + adapter base (LLD-02 §1). The ONLY shape adapters emit."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterator, Literal

from pydantic import BaseModel, Field


class Engagement(BaseModel):
    score: float = 0.0                  # unified: log1p(likes + 2*shares + 3*replies)
    native: dict[str, int] = Field(default_factory=dict)


class AuthorMeta(BaseModel):
    followers: int | None = None
    verified: bool | None = None
    karma: int | None = None
    account_created_at: datetime | None = None


class SocialItem(BaseModel):
    source: Literal[
        "twitter",
        "reddit",
        "youtube",
        "github",
        "community_forum",
        "app_review",
        "instagram",
    ]
    source_type: Literal["post", "comment", "tweet", "reply", "message", "review", "issue",
                         "reel", "sidecar"]
    external_id: str
    parent_id: str | None = None
    thread_id: str
    author: str                         # handle, no '@'/'u/' prefix
    author_meta: AuthorMeta = Field(default_factory=AuthorMeta)
    text: str
    lang: str | None = None
    url: str
    created_at: datetime                # SOURCE time, tz-aware UTC
    engagement: Engagement = Field(default_factory=Engagement)
    raw: dict = Field(default_factory=dict)


def unified_score(likes: int = 0, shares: int = 0, replies: int = 0) -> float:
    import math
    # platforms report -1 for hidden counts (e.g. Instagram hidden likes) —
    # clamp: log1p is undefined below 0 (live crash 2026-08-13)
    return math.log1p(max(0, likes) + 2 * max(0, shares) + 3 * max(0, replies))


class SourceAdapter(ABC):
    name: str

    @abstractmethod
    def fetch(self, cursor: dict | None) -> Iterator[SocialItem]:
        """Yield items; resumable from cursor; log+skip single bad items;
        raise AdapterError only on total failure."""

    def fetch_items(self, external_ids: list[str]) -> list[SocialItem]:
        """Point lookups for the engagement refresh; optional per adapter."""
        return []


class AdapterError(RuntimeError):
    pass
