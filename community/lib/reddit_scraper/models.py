# VENDORED from github.com/zanshash/reddit_scraper @ f926fc7
# (+ nested-replies patch — see this script's docstring)
# Do not edit here; update the source repo, then run scripts/sync_reddit_scraper.py
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Comment:
    author: str
    score: Optional[int]
    body: str
    replies: List[dict] = field(default_factory=list)  # PATCH: one nested level


@dataclass
class Post:
    id: str
    subreddit: str
    sort_type: str
    title: str
    author: str
    score: Optional[int]
    num_comments: Optional[int]
    permalink: str
    url: str
    post_type: str          # self | image | gallery | video | link
    selftext: Optional[str]
    flair: Optional[str]
    image_urls: List[str] = field(default_factory=list)
    local_images: List[str] = field(default_factory=list)
    comments: List[Comment] = field(default_factory=list)
    timestamp: Optional[int] = None   # Unix seconds (UTC) post was created

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subreddit": self.subreddit,
            "sort_type": self.sort_type,
            "title": self.title,
            "author": self.author,
            "score": self.score,
            "num_comments": self.num_comments,
            "permalink": f"https://reddit.com{self.permalink}",
            "url": self.url,
            "post_type": self.post_type,
            "flair": self.flair,
            "selftext": self.selftext,
            "image_urls": self.image_urls,
            "local_images": self.local_images,
            "timestamp": self.timestamp,
            "comments": [
                {"author": c.author, "score": c.score, "body": c.body,
                 "replies": c.replies}
                for c in self.comments
            ],
        }
