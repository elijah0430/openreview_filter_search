from __future__ import annotations

from contextlib import contextmanager
from io import StringIO
from typing import List, Optional

import pandas as pd
import streamlit as st
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

if __package__:
    from .db import SessionLocal, init_db
    from .ingest import ingest_group_sync
    from .models import ArxivMatch, Paper, Venue
    from .services.proceedings_client import search_proceedings_sync
else:
    from app.db import SessionLocal, init_db
    from app.ingest import ingest_group_sync
    from app.models import ArxivMatch, Paper, Venue
    from app.services.proceedings_client import search_proceedings_sync


st.set_page_config(page_title="OpenReview Filter", layout="wide")
init_db()


@contextmanager
def get_session() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def list_venues() -> List[Venue]:
    with get_session() as db:
        return db.scalars(select(Venue).order_by(Venue.added_at.desc())).all()


def arxiv_status(matches: List[ArxivMatch]) -> tuple[str, str, str]:
    if not matches:
        return "", "", ""
    best = sorted(matches, key=lambda m: (m.exact, m.score), reverse=True)[0]
    match_type = "exact" if best.exact else "fuzzy"
    return best.arxiv_id or "", match_type, f"{best.score:.3f}"


def filter_papers(
    venue_id: Optional[int],
    decision_text: str,
    keywords_text: str,
    min_rating: Optional[float],
    arxiv_filter: str,
) -> List[dict]:
    with get_session() as db:
        query = select(Paper)
        if venue_id:
            query = query.where(Paper.venue_id == venue_id)
        if decision_text:
            query = query.where(func.lower(Paper.decision).like(f"%{decision_text.lower()}%"))
        if keywords_text:
            for kw in [k.strip() for k in keywords_text.replace(";", ",").split(",") if k.strip()]:
                query = query.where(func.lower(Paper.keywords).like(f"%{kw.lower()}%"))
        if min_rating is not None:
            query = query.where(Paper.avg_rating >= min_rating)

        papers = db.scalars(query.order_by(Paper.avg_rating.desc().nullslast(), Paper.title.asc())).all()
        rows: List[dict] = []
        for paper in papers:
            matches = sorted(paper.arxiv_matches, key=lambda m: (m.exact, m.score), reverse=True)
            if arxiv_filter == "exists" and not matches:
                continue
            if arxiv_filter == "none" and matches:
                continue
            if arxiv_filter == "exact" and not any(m.exact for m in matches):
                continue
            if arxiv_filter == "fuzzy" and not any((not m.exact) and m.score >= 0.85 for m in matches):
                continue

            arxiv_id, match_type, score = arxiv_status(matches)
            rows.append(
                {
                    "Venue": f"{paper.venue.name} {paper.venue.year or ''}",
                    "Title": paper.title,
                    "Authors": paper.authors or "",
                    "Decision": paper.decision or "",
                    "Avg Rating": round(paper.avg_rating, 2) if paper.avg_rating is not None else None,
                    "# Reviews": paper.num_reviews,
                    "Keywords": paper.keywords or "",
                    "Best arXiv": arxiv_id,
                    "Match": match_type,
                    "Score": score,
                }
            )
        return rows


def render_ingest_section() -> None:
    st.subheader("Ingest OpenReview Venue")
    with st.form("ingest_form", clear_on_submit=False):
        group_id = st.text_input("OpenReview Group ID", placeholder="ICLR.cc/2025/Conference")
        display_name = st.text_input("Display Name (optional)", placeholder="ICLR")
        year_text = st.text_input("Year (optional)", placeholder="2025")
        with_arxiv = st.checkbox("Fetch arXiv matches", value=True)
        submitted = st.form_submit_button("Ingest venue")

    if submitted:
        if not group_id.strip():
            st.error("Group ID is required")
            return

        year_value: Optional[int] = None
        if year_text.strip():
            try:
                year_value = int(year_text.strip())
            except ValueError:
                st.error("Year must be an integer")
                return

        with st.spinner("Fetching submissions from OpenReview..."):
            count = ingest_group_sync(
                group_id.strip(),
                name=display_name.strip() or None,
                year=year_value,
                with_arxiv=with_arxiv,
            )
        st.success(f"Ingested {count} submissions from {group_id.strip()}")


def render_search_section() -> None:
    st.subheader("Filter cached submissions")
    venues = list_venues()
    venue_labels = ["Any venue"] + [f"{v.name} {v.year or ''} ({v.group_id})" for v in venues]
    venue_ids = [None] + [v.id for v in venues]

    with st.form("search_form"):
        venue_idx = st.selectbox(
            "Venue",
            options=range(len(venue_labels)),
            format_func=lambda idx: venue_labels[idx],
        )
        venue_choice = venue_ids[venue_idx]
        decision = st.text_input("Decision contains", placeholder="Accept, Reject, etc.")
        keywords = st.text_input("Keywords (comma separated)", placeholder="LLM, reinforcement learning")
        min_rating = st.number_input("Minimum average rating", min_value=0.0, max_value=10.0, step=0.1, value=0.0)
        arxiv_filter = st.selectbox(
            "arXiv filter",
            options=["any", "exists", "exact", "fuzzy", "none"],
            format_func=lambda x: {
                "any": "Any",
                "exists": "Has arXiv",
                "exact": "Exact title",
                "fuzzy": "Fuzzy match (>=0.85)",
                "none": "No arXiv",
            }[x],
        )
        submitted = st.form_submit_button("Run search")

    if submitted:
        rows = filter_papers(
            venue_choice,
            decision.strip(),
            keywords.strip(),
            min_rating if min_rating > 0 else None,
            arxiv_filter,
        )
        if not rows:
            st.info("No submissions match these filters yet. Ingest a venue first or adjust the filters.")
            return

        df = pd.DataFrame(rows)
        st.metric("Matches", len(df))
        st.dataframe(df, use_container_width=True, hide_index=True)
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        st.download_button(
            label="Download CSV",
            data=csv_buffer.getvalue(),
            file_name="openreview_filter.csv",
            mime="text/csv",
        )


def render_proceedings_tab() -> None:
    st.subheader("Search NLP conference/journal proceedings (OpenAlex)")
    with st.form("proceedings_form"):
        query = st.text_input("Query", value="large language model")
        venue_type = st.selectbox("Venue type", ["any", "conference", "journal"], format_func=lambda x: x.capitalize())
        col1, col2 = st.columns(2)
        with col1:
            year_from = st.text_input("Year from", value="")
        with col2:
            year_to = st.text_input("Year to", value="")
        sort = st.selectbox("Sort by", ["relevance", "year", "citations"], format_func=lambda x: x.capitalize())
        page = st.number_input("Page", min_value=1, value=1, step=1)
        submitted = st.form_submit_button("Search OpenAlex")

    if submitted:
        yf = int(year_from) if year_from.strip().isdigit() else None
        yt = int(year_to) if year_to.strip().isdigit() else None
        with st.spinner("Querying OpenAlex"):
            try:
                data = search_proceedings_sync(
                    query=query.strip() or "natural language processing",
                    venue_type=venue_type,
                    year_from=yf,
                    year_to=yt,
                    sort=sort,
                    page=int(page),
                )
            except Exception as exc:  # pragma: no cover - network issues
                st.error(f"OpenAlex request failed: {exc}")
                return

        results = data.get("results", [])
        if not results:
            st.info("No OpenAlex results for this query.")
            return

        df = pd.DataFrame([
            {
                "Title": r.title,
                "Authors": r.authors,
                "Venue": r.venue,
                "Type": r.venue_type,
                "Year": r.year,
                "Citations": r.citations,
                "arXiv/DOI": r.doi or r.openalex_id,
                "URL": r.url,
            }
            for r in results
        ])
        st.metric("Results", len(df))
        st.dataframe(df, use_container_width=True, hide_index=True)


st.title("OpenReview Filter & NLP Proceedings Explorer")
tab1, tab2 = st.tabs(["OpenReview", "Proceedings"])

with tab1:
    render_ingest_section()
    st.divider()
    render_search_section()

with tab2:
    render_proceedings_tab()
