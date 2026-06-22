from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from src.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    interactions = relationship("UserInteraction", back_populates="user", cascade="all, delete-orphan")


class UserInteraction(Base):
    __tablename__ = "user_interactions"
    __table_args__ = (
        UniqueConstraint("user_id", "attraction_name", "event_type", name="uq_user_attraction_event"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    attraction_name = Column(String(512), nullable=False, index=True)
    event_type = Column(String(32), nullable=False)  # view | favorite
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="interactions")
