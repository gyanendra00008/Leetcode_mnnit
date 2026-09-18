from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class LeetCodeUser(Base):
    __tablename__ = "leetcode_users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    actual_name = Column(String(150), default="N/A", index=True)
    profile_url = Column(String(255), nullable=False)
    rating = Column(Float, nullable=True, index=True)
    total_questions = Column(Integer, default=0, index=True)
    easy_questions = Column(Integer, default=0)
    medium_questions = Column(Integer, default=0)
    hard_questions = Column(Integer, default=0)
    college_relevance = Column(String(50), default="unknown", index=True)
    source_user = Column(String(100), nullable=True)
    discovered_via = Column(String(50), default="seed")
    crawl_status = Column(String(20), default="pending", index=True)
    stats_status = Column(String(20), default="pending", index=True)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "actual_name": self.actual_name or "N/A",
            "profile_url": self.profile_url,
            "rating": round(self.rating, 1) if self.rating is not None else None,
            "total_questions": self.total_questions,
            "easy_questions": self.easy_questions,
            "medium_questions": self.medium_questions,
            "hard_questions": self.hard_questions,
            "college_relevance": self.college_relevance,
            "source_user": self.source_user,
            "discovered_via": self.discovered_via,
            "crawl_status": self.crawl_status,
            "stats_status": self.stats_status,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    token = Column(String(128), unique=True, index=True, nullable=False)
    username = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=utc_now)
    expires_at = Column(DateTime, nullable=False)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, default=utc_now, index=True)
    admin_username = Column(String(100), default="admin", nullable=False)
    action = Column(String(50), nullable=False, index=True)  # LOGIN, LOGOUT, UPDATE_USER, UPDATE_ALL, DISCOVER, STOP
    target = Column(String(255), nullable=True)             # username or parameter
    status = Column(String(20), default="SUCCESS")          # SUCCESS, FAILED
    details = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "admin_username": self.admin_username,
            "action": self.action,
            "target": self.target,
            "status": self.status,
            "details": self.details,
        }

