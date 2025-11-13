from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .models import Venue, Paper, ArxivMatch
from .services.openreview_client import fetch_submissions_for_group
from .services.arxiv_matcher import find_arxiv_match
from .config import settings


async def ingest_group(group_id: str, name: Optional[str] = None, year: Optional[int] = None, with_arxiv: bool = True) -> int:
    init_db()
    submissions = await fetch_submissions_for_group(group_id)
    count = 0
    with SessionLocal() as db:
        venue = db.scalar(select(Venue).where(Venue.group_id == group_id))
        if not venue:
            venue = Venue(group_id=group_id, name=name or group_id.split("/")[0], year=year)
            db.add(venue)
            db.flush()

        for summary in submissions:
            paper = db.scalar(select(Paper).where(Paper.openreview_forum == summary.forum))
            if not paper:
                paper = Paper(
                    venue_id=venue.id,
                    openreview_forum=summary.forum,
                    openreview_note=summary.note,
                    title=summary.title,
                    abstract=summary.abstract,
                    authors=summary.authors,
                    keywords=", ".join(summary.keywords or []),
                    decision=summary.decision,
                    avg_rating=summary.avg_rating,
                    num_reviews=summary.num_reviews or 0,
                    last_refreshed=datetime.utcnow(),
                )
                db.add(paper)
            else:
                paper.title = summary.title
                paper.abstract = summary.abstract
                paper.authors = summary.authors
                paper.keywords = ", ".join(summary.keywords or [])
                paper.decision = summary.decision
                paper.avg_rating = summary.avg_rating
                paper.num_reviews = summary.num_reviews or 0
                paper.last_refreshed = datetime.utcnow()
            count += 1

        db.commit()

        if with_arxiv:
            # match arXiv for papers missing recent matches
            deadline = datetime.utcnow() - timedelta(seconds=settings.arxiv_ttl)
            papers = db.scalars(select(Paper).where(Paper.venue_id == venue.id)).all()
            for p in papers:
                latest = db.scalar(
                    select(ArxivMatch).where(ArxivMatch.paper_id == p.id).order_by(ArxivMatch.matched_at.desc())
                )
                if latest and latest.matched_at > deadline:
                    continue
                aid, atitle, exact, score = await find_arxiv_match(p.title)
                if aid:
                    db.add(
                        ArxivMatch(
                            paper_id=p.id,
                            arxiv_id=aid,
                            title=atitle or p.title,
                            exact=bool(exact),
                            score=float(score),
                            matched_at=datetime.utcnow(),
                        )
                    )
            db.commit()

    return count


def ingest_group_sync(group_id: str, name: Optional[str] = None, year: Optional[int] = None, with_arxiv: bool = True) -> int:
    return asyncio.run(ingest_group(group_id, name=name, year=year, with_arxiv=with_arxiv))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest OpenReview group into local cache")
    parser.add_argument("group_id", help="OpenReview group id, e.g., ICLR.cc/2024/Conference")
    parser.add_argument("--name", help="Venue display name", default=None)
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--no-arxiv", action="store_true")
    args = parser.parse_args()

    n = ingest_group_sync(args.group_id, name=args.name, year=args.year, with_arxiv=(not args.no_arxiv))
    print(f"Ingested {n} submissions from {args.group_id}")
