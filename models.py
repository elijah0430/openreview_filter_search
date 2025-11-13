from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[str] = mapped_column(String(255), index=True)  # e.g., "ICLR.cc/2024/Conference"
    name: Mapped[str] = mapped_column(String(255), index=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    papers: Mapped[list[Paper]] = relationship(back_populates="venue", cascade="all, delete-orphan")  # type: ignore[name-defined]


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    openreview_forum: Mapped[str] = mapped_column(String(128), index=True)
    openreview_note: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(1024), index=True)
    abstract: Mapped[Optional[str]] = mapped_column(Text)
    authors: Mapped[Optional[str]] = mapped_column(Text)  # joined by "; "
    keywords: Mapped[Optional[str]] = mapped_column(Text)
    decision: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    avg_rating: Mapped[Optional[float]] = mapped_column(Float, index=True)
    num_reviews: Mapped[int] = mapped_column(Integer, default=0)
    last_refreshed: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    venue: Mapped[Venue] = relationship(back_populates="papers")
    arxiv_matches: Mapped[list[ArxivMatch]] = relationship(back_populates="paper", cascade="all, delete-orphan")  # type: ignore[name-defined]


class ArxivMatch(Base):
    __tablename__ = "arxiv_matches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)
    arxiv_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(1024))
    exact: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    matched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    paper: Mapped[Paper] = relationship(back_populates="arxiv_matches")


