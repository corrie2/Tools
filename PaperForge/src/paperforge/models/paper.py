"""Paper data model."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def generate_slug(title: str, max_len: int = 60) -> str:
    """Convert title to a URL-safe slug.

    Rules:
    - lowercase
    - remove special characters (keep alphanumeric, spaces, hyphens)
    - collapse whitespace to hyphens
    - truncate to max_len characters
    """
    slug = title.lower().strip()
    # Remove anything that's not alphanumeric, space, or hyphen
    slug = re.sub(r"[^\w\s-]", "", slug)
    # Collapse whitespace/underscores to single hyphen
    slug = re.sub(r"[\s_]+", "-", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    # Truncate
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug


def normalize_title(title: str) -> str:
    """Normalize title for deduplication matching.

    Rules:
    - lowercase
    - strip all punctuation
    - normalize whitespace
    """
    normalized = title.lower().strip()
    # Remove all punctuation
    normalized = re.sub(r"[^\w\s]", "", normalized)
    # Collapse whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


class Paper(BaseModel):
    """Paper data model matching SQLite schema."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    slug: str = ""
    title: str = ""
    normalized_title: str = ""
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    doi: Optional[str] = None
    language: str = "unknown"
    pdf_path: Optional[str] = None
    pdf_sha256: Optional[str] = None
    vault_path: Optional[str] = None  # papers/{year}/{slug}/index.md
    paper_dir: Optional[str] = None   # papers/{year}/{slug}/
    parser: str = "docling"
    parse_quality: str = "medium"
    fallback_used: bool = False
    external_id: Optional[str] = None
    processed_at: Optional[str] = None
    updated_at: Optional[str] = None
    status: str = "completed"

    def model_post_init(self, __context) -> None:
        if not self.slug and self.title:
            self.slug = generate_slug(self.title)
        if not self.normalized_title and self.title:
            self.normalized_title = normalize_title(self.title)
        now = datetime.now(timezone.utc).isoformat()
        if not self.processed_at:
            self.processed_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_db_dict(self) -> dict:
        """Convert to dictionary for SQLite insertion."""
        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "normalized_title": self.normalized_title,
            "authors": str(self.authors),  # JSON-serialized in store
            "year": self.year,
            "venue": self.venue,
            "doi": self.doi,
            "language": self.language,
            "pdf_path": self.pdf_path,
            "pdf_sha256": self.pdf_sha256,
            "vault_path": self.vault_path,
            "paper_dir": self.paper_dir,
            "parser": self.parser,
            "parse_quality": self.parse_quality,
            "fallback_used": 1 if self.fallback_used else 0,
            "external_id": self.external_id,
            "processed_at": self.processed_at,
            "updated_at": self.updated_at,
            "status": self.status,
        }
