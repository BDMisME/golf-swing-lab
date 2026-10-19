from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from apps.api.config import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy 2 宣告式基底類別。"""


def build_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(
        url,
        pool_pre_ping=True,
        future=True,
        connect_args=connect_args,
    )


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 資料庫 Session 依賴注入。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
