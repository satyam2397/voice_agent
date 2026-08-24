from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Session:
    """FastAPI dependency. Every query made with this session must still filter
    explicitly by distributor_id / conversation_id at the query level -- this
    session does not do that for you."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
