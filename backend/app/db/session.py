
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def create_engine_for_settings(settings: Settings) -> Engine:
    return create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
    )

@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine_for_settings(get_settings())

SessionLocal = sessionmaker(
    bind=get_engine(),
    autoflush=False,
    expire_on_commit=False,
)

def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
