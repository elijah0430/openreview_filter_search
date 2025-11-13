from __future__ import annotations

import asyncio
import time
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..config import settings


def normalize_title(s: str) -> str:
    return " ".join("".join(ch.lower() for ch in s if ch.isalnum() or ch.isspace()).split())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


async def query_arxiv_by_title(title: str, max_results: int = 5) -> List[Tuple[str, str]]:
    # Returns list of (arxiv_id, title)
    base = settings.arxiv_base
    # Use exact title search
    q = f'ti:"{title}"'
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(base, params={"search_query": q, "max_results": max_results})
        r.raise_for_status()
        xml = r.text
    # Parse Atom
    root = ET.fromstring(xml)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    out: List[Tuple[str, str]] = []
    for entry in root.findall("atom:entry", ns):
        id_text = entry.findtext("atom:id", default="", namespaces=ns)
        title_text = entry.findtext("atom:title", default="", namespaces=ns)
        arxiv_id = id_text.split("/abs/")[-1].strip()
        out.append((arxiv_id, title_text.strip()))
    return out


async def find_arxiv_match(title: str) -> Tuple[Optional[str], Optional[str], bool, float]:
    """
    Returns (arxiv_id, arxiv_title, exact, score)
    """
    candidates = await query_arxiv_by_title(title)
    if not candidates:
        return None, None, False, 0.0
    norm_title = normalize_title(title)
    best = (None, None, False, 0.0)  # type: ignore
    for aid, atitle in candidates:
        if normalize_title(atitle) == norm_title:
            return aid, atitle, True, 1.0
        s = similarity(title, atitle)
        if s > best[3]:
            best = (aid, atitle, False, s)
    return best
