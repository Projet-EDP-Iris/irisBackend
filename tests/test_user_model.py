from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import all models to ensure they're registered with Base.metadata before create_all()
from app.models import Base, User

DATABASE_URL = "sqlite:///.test.db"

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def test_create_user():
    # Drop and recreate all tables to ensure schema is up-to-date
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session= SessionLocal()
    new_user = User(
            email="test@example.com",
            password_hash="hashedpassword123!",
            role="regular",
            has_subscription=True,
            bank_account_id="bank_abc123",
            oauth_provider=None,
            require_password_reset=False
            )
    session.add(new_user)
    session.commit()

    queried = session.query(User).filter_by(email="test@example.com").first()
    assert queried is not None
    assert queried.email == "test@example.com"
    assert queried.has_subscription is True

    session.close()
