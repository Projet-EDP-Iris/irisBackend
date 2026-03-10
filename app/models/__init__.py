# Import all models here to ensure they're registered with SQLAlchemy Base
from app.models.base import Base
from app.models.feedback import DetectionFeedback
from app.models.user import User

__all__ = ["Base", "DetectionFeedback", "User"]
