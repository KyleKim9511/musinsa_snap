from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Snap:
    """Represents a single snap entry from Musinsa."""

    id: Optional[str]
    url: str
    title: Optional[str] = None
    author: Optional[str] = None
    image_url: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    taken_at: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "author": self.author,
            "image_url": self.image_url,
            "tags": self.tags,
            "taken_at": self.taken_at,
            "description": self.description,
        }
