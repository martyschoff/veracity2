# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Data models for veracity2 — predictions vs reality tracker."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime


@dataclass
class Individual:
    """A tracked individual who makes predictions."""

    name: str
    handle: str
    sources: list[str]
    categories: list[str]
    correct_count: int = 0
    wrong_count: int = 0

    @property
    def primary_category(self) -> str:
        """First category in the list is the individual's primary category."""
        return self.categories[0] if self.categories else "other"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Prediction:
    """A single prediction extracted from a transcript or article."""

    id: str
    individual_name: str
    date: date
    category: str
    claim: str
    source_url: str
    transcript_excerpt: str
    verdict: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Serialize date/datetime to ISO strings for JSON
        if isinstance(d["date"], date):
            d["date"] = d["date"].isoformat()
        if isinstance(d["created_at"], datetime):
            d["created_at"] = d["created_at"].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Prediction":
        d = dict(d)
        if isinstance(d.get("date"), str):
            d["date"] = date.fromisoformat(d["date"])
        if isinstance(d.get("created_at"), str):
            d["created_at"] = datetime.fromisoformat(d["created_at"])
        return cls(**d)
