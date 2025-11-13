from __future__ import annotations

import os
from pydantic import BaseModel


class Settings(BaseModel):
    db_url: str = os.getenv("ORFILTER_DB_URL", "sqlite:///./orfilter.db")
    # OpenReview base API (public)
    openreview_base: str = os.getenv("ORFILTER_OPENREVIEW_BASE", "https://api.openreview.net")
    openreview_username: Optional[str] = os.getenv("OPENREVIEW_USERNAME")
    openreview_password: Optional[str] = os.getenv("OPENREVIEW_PASSWORD")
    # arXiv API endpoint (public)
    arxiv_base: str = os.getenv("ORFILTER_ARXIV_BASE", "http://export.arxiv.org/api/query")
    # OpenAlex API base for proceedings search
    openalex_base: str = os.getenv("ORFILTER_OPENALEX_BASE", "https://api.openalex.org")
    # Cache TTL for arXiv matches in seconds (default 14 days)
    arxiv_ttl: int = int(os.getenv("ORFILTER_ARXIV_TTL", str(14 * 24 * 3600)))
    # Server listen port
    port: int = int(os.getenv("PORT", "14727"))


settings = Settings()
