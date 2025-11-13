from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import asyncio

import httpx

from ..config import settings


NLP_CONCEPT_ID = "https://openalex.org/C41008148"  # Natural language processing


@dataclass
class ProceedingsResult:
    openalex_id: str
    title: str
    authors: str
    venue: str
    venue_type: str
    year: Optional[int]
    doi: Optional[str]
    url: Optional[str]
    citations: int


def _format_authors(authorships: List[Dict[str, Any]]) -> str:
    names = []
    for auth in authorships or []:
        author = auth.get("author", {}) or {}
        name = author.get("display_name") or auth.get("raw_author_name")
        if name:
            names.append(name)
    return "; ".join(names[:8]) + (" et al." if len(names) > 8 else "")


async def search_proceedings(
    query: str,
    venue_type: str = "any",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    sort: str = "relevance",
    per_page: int = 25,
    page: int = 1,
) -> Dict[str, Any]:
    filters = [f"concepts.id:{NLP_CONCEPT_ID}"]
    if venue_type in {"conference", "journal"}:
        filters.append(f"primary_location.source.type:{venue_type}")
    if year_from:
        filters.append(f"from_publication_date:{year_from}-01-01")
    if year_to:
        filters.append(f"to_publication_date:{year_to}-12-31")

    sort_map = {
        "relevance": "relevance_score:desc",
        "year": "publication_year:desc",
        "citations": "cited_by_count:desc",
    }
    sort_param = sort_map.get(sort, sort_map["relevance"])

    params = {
        "search": query or "natural language processing",
        "filter": ",".join(filters),
        "per-page": per_page,
        "page": max(page, 1),
        "sort": sort_param,
    }

    base = settings.openalex_base.rstrip("/")

    timeout = httpx.Timeout(15.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{base}/works", params=params)
        resp.raise_for_status()
        data = resp.json()

    results: List[ProceedingsResult] = []
    for item in data.get("results", []):
        loc = item.get("primary_location", {}) or {}
        source = loc.get("source", {}) or {}
        venue_type_val = source.get("type") or loc.get("type") or "unknown"
        url = loc.get("landing_page_url") or item.get("open_access", {}).get("oa_url") or item.get("id")
        result = ProceedingsResult(
            openalex_id=item.get("id"),
            title=item.get("display_name") or item.get("title") or "(untitled)",
            authors=_format_authors(item.get("authorships") or []),
            venue=source.get("display_name") or source.get("publisher") or "",
            venue_type=venue_type_val,
            year=item.get("publication_year"),
            doi=item.get("doi"),
            url=url,
            citations=item.get("cited_by_count") or 0,
        )
        results.append(result)

    return {
        "results": results,
        "meta": {
            "count": len(results),
            "total": data.get("meta", {}).get("count"),
            "page": params["page"],
            "per_page": per_page,
        },
    }


def search_proceedings_sync(**kwargs) -> Dict[str, Any]:
    try:
        return asyncio.run(search_proceedings(**kwargs))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(search_proceedings(**kwargs))
        finally:
            loop.close()
