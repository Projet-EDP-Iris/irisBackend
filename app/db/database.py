from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Import Base and all models to ensure they're registered with Base.metadata
# This MUST be done before calling Base.metadata.create_all()
from app.models import Base, DetectionFeedback, User  # noqa: F401

_db_url = settings.DATABASE_URL
# Render (and some other hosts) provide "postgres://" but SQLAlchemy 2.0
# only accepts "postgresql://".
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

if _db_url.startswith("sqlite"):
    engine = create_engine(
        _db_url,
        connect_args={"check_same_thread": False},
        future=True
    )
else:
    engine = create_engine(_db_url, future=True, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

def get_db():
    """
    Database session dependency for FastAPI routes.
    Yields a database session and ensures it's closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """
    Initialize database by creating all tables.
    Called on application startup.
    """
    Base.metadata.create_all(bind=engine)
