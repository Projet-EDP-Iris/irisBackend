# Import all models here to ensure they're registered with SQLAlchemy Base
from app.models.base import Base
from app.models.email import Email
from app.models.feedback import DetectionFeedback
from app.models.user import User

__all__ = ["Base", "Email", "DetectionFeedback", "User"]
