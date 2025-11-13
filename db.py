from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False} if settings.db_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    from . import models  # noqa: F401 ensure models are imported
    Base.metadata.create_all(bind=engine)

