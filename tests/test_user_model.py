from app.models.base import Base
from app.models.user import User
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///.test.db"

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def test_create_user():
    Base.metadata.create_all(bind=engine)

    session= SessionLocal()
    new_user = User(
            email="test@example.com",
            password_hash="hashedpassword123!",
            role="regular",
            has_subscription=True,
            bank_account_id="bank_abc123",
            oauth_provider=None
            )
    session.add(new_user)
    session.commit()

    queried = session.query(User).filter_by(email="test@example.com").first()
    assert queried is not None
    assert queried.email == "test@example.com"
    assert queried.has_subscription is True

    session.close()
