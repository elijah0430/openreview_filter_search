from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from ..config import settings


DEFAULT_INVITATIONS = ["Blind_Submission", "Submission"]
FALLBACK_INVITATIONS = ["Submission"]


@dataclass
class SubmissionSummary:
    forum: str
    note: str
    title: str
    abstract: Optional[str]
    authors: str
    keywords: List[str]
    decision: Optional[str]
    avg_rating: Optional[float]
    num_reviews: int


def parse_rating(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value)
        buf = ""
        for ch in s:
            if ch.isdigit() or (ch == "." and "." not in buf):
                buf += ch
            elif buf:
                break
        return float(buf) if buf else None
    except Exception:
        return None


def extract_keywords(content: Dict[str, Any]) -> List[str]:
    keys = ["keywords", "Keywords", "key_areas", "Key Areas", "Key Area(s)"]
    for k in keys:
        if k in content:
            value = content[k]
            if isinstance(value, list):
                return [str(v).strip() for v in value]
            if isinstance(value, str):
                return [token.strip() for token in value.replace(";", ",").split(",") if token.strip()]
    return []


async def fetch_notes(invitation: str, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    base = settings.openreview_base.rstrip("/")
    offset = 0
    page_size = 200
    collected: List[Dict[str, Any]] = []
    while True:
        params = {
            "invitation": invitation,
            "details": "directReplies",
            "limit": page_size,
            "offset": offset,
        }
        resp = await client.get(f"{base}/notes", params=params)
        resp.raise_for_status()
        data = resp.json()
        notes = data.get("notes") or data.get("items") or []
        if not notes:
            break
        collected.extend(notes)
        offset += len(notes)
        if len(notes) < page_size:
            break
    return collected


def summarize(note: Dict[str, Any]) -> SubmissionSummary:
    content = note.get("content", {}) or {}
    title = content.get("title") or content.get("Title") or ""
    abstract = content.get("abstract") or content.get("Abstract")
    authors = content.get("authors") or content.get("Authors") or []
    if isinstance(authors, list):
        authors_str = "; ".join(str(a) for a in authors)
    else:
        authors_str = str(authors)
    keywords = extract_keywords(content)

    direct = note.get("details", {}).get("directReplies", []) or []
    ratings: List[float] = []
    decision: Optional[str] = None
    for reply in direct:
        rcontent = reply.get("content", {}) or {}
        invitation = reply.get("invitation", "")
        if "Decision" in invitation or any(k.lower() == "decision" for k in rcontent):
            dv = rcontent.get("decision") or rcontent.get("Decision") or rcontent.get("recommendation")
            if isinstance(dv, dict) and "value" in dv:
                dv = dv["value"]
            if dv:
                decision = str(dv)
        for key, val in rcontent.items():
            if "rating" in key.lower():
                pr = parse_rating(val)
                if pr is not None:
                    ratings.append(pr)

    avg_rating = sum(ratings) / len(ratings) if ratings else None
    return SubmissionSummary(
        forum=note.get("forum") or note.get("id"),
        note=note.get("id"),
        title=title,
        abstract=abstract,
        authors=authors_str,
        keywords=keywords,
        decision=decision,
        avg_rating=avg_rating,
        num_reviews=len(ratings),
    )


async def fetch_submissions_for_group(group_id: str) -> List[SubmissionSummary]:
    auth = None
    if settings.openreview_username and settings.openreview_password:
        auth = (settings.openreview_username, settings.openreview_password)
    async with httpx.AsyncClient(timeout=60, auth=auth) as client:
        notes: List[Dict[str, Any]] = []
        for invite in DEFAULT_INVITATIONS:
            notes.extend(await fetch_notes(f"{group_id}/-/{invite}", client))
        if not notes:
            for invite in FALLBACK_INVITATIONS:
                notes.extend(await fetch_notes(f"{group_id}/-/{invite}", client))
    if not notes:
        return []
    seen = {}
    for note in notes:
        sid = note.get("id")
        seen[sid] = note
    return [summarize(note) for note in seen.values()]


def fetch_submissions_for_group_sync(group_id: str) -> List[SubmissionSummary]:
    try:
        return asyncio.run(fetch_submissions_for_group(group_id))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(fetch_submissions_for_group(group_id))
        finally:
            loop.close()
