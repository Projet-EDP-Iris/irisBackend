from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Import Base and all models to ensure they're registered with Base.metadata
# This MUST be done before calling Base.metadata.create_all()
from app.models import (  # noqa: F401
    AuthToken,
    Base,
    DetectionFeedback,
    ProcessingState,
    RefreshToken,
    SyncState,
    User,
)

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
    engine = create_engine(_db_url, future=True, pool_pre_ping=True, pool_recycle=300)

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

    # Lightweight migration for existing deployments that predate these columns.
    with engine.begin() as connection:
        user_columns = {col["name"] for col in inspect(connection).get_columns("users")}
        if "profile_icon" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN profile_icon VARCHAR(50)"))
        if "gmail_oauth_token" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN gmail_oauth_token TEXT"))
        if "gmail_email" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN gmail_email VARCHAR(255)"))
        if "outlook_oauth_token" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN outlook_oauth_token TEXT"))
        if "outlook_email" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN outlook_email VARCHAR(255)"))
        if "is_email_verified" not in user_columns:
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN is_email_verified BOOLEAN NOT NULL DEFAULT FALSE"
            ))

        # Email table columns (added in v2) — keep try/except in case emails
        # table doesn't exist yet on a brand-new deployment (create_all handles it).
        try:
            email_columns = {col["name"] for col in inspect(connection).get_columns("emails")}
            if "category" not in email_columns:
                connection.execute(text("ALTER TABLE emails ADD COLUMN category VARCHAR(20)"))
            if "email_date" not in email_columns:
                connection.execute(text("ALTER TABLE emails ADD COLUMN email_date VARCHAR(100)"))
            if "provider" not in email_columns:
                connection.execute(text("ALTER TABLE emails ADD COLUMN provider VARCHAR(20)"))
            if "sender" not in email_columns:
                connection.execute(text("ALTER TABLE emails ADD COLUMN sender VARCHAR(255)"))
            if "is_done" not in email_columns:
                connection.execute(text(
                    "ALTER TABLE emails ADD COLUMN is_done BOOLEAN NOT NULL DEFAULT FALSE"
                ))
            if "is_read" not in email_columns:
                connection.execute(text(
                    "ALTER TABLE emails ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT FALSE"
                ))

            # Migrate from global unique on message_id → composite unique per (message_id, user_id).
            # Drop the old single-column index (may or may not exist depending on deployment age).
            if "rfc_message_id" not in email_columns:
                connection.execute(text("ALTER TABLE emails ADD COLUMN rfc_message_id VARCHAR(998)"))

            connection.execute(text("DROP INDEX IF EXISTS ix_emails_message_id"))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_emails_message_id_user "
                "ON emails (message_id, user_id)"
            ))
        except Exception:
            pass

    # Add ON DELETE CASCADE to user_id foreign keys that predate it (emails,
    # processing_state, sync_state) — without this, deleting a user with any
    # associated row in these tables fails with a foreign-key violation on
    # Postgres, silently breaking account deletion (GDPR right to erasure).
    # SQLite can't alter constraints in place, but a fresh SQLite DB already
    # gets the correct constraint from create_all() above, so skip there.
    if not _db_url.startswith("sqlite"):
        with engine.begin() as connection:
            inspector = inspect(connection)
            for table, column in (
                ("emails", "user_id"),
                ("processing_state", "user_id"),
                ("sync_state", "user_id"),
            ):
                try:
                    foreign_keys = inspector.get_foreign_keys(table)
                except Exception:
                    continue
                for fk in foreign_keys:
                    if column not in fk.get("constrained_columns", []):
                        continue
                    if (fk.get("options") or {}).get("ondelete") == "CASCADE":
                        break
                    name = fk.get("name")
                    if not name:
                        break
                    referred_table = fk["referred_table"]
                    referred_column = fk["referred_columns"][0]
                    connection.execute(text(f'ALTER TABLE {table} DROP CONSTRAINT "{name}"'))
                    connection.execute(text(
                        f'ALTER TABLE {table} ADD CONSTRAINT "{name}" '
                        f'FOREIGN KEY ({column}) REFERENCES {referred_table} ({referred_column}) '
                        f'ON DELETE CASCADE'
                    ))
                    break
