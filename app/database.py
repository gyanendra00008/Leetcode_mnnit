from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def init_db():
    """Create all database tables and perform lightweight migrations."""
    import app.models  # Ensure models are imported
    Base.metadata.create_all(bind=engine)

    # Lightweight schema migration for SQLite
    if "sqlite" in settings.DATABASE_URL:
        with engine.connect() as conn:
            try:
                result = conn.execute(text("PRAGMA table_info(leetcode_users)"))
                cols = [row[1] for row in result.fetchall()]
                if cols and "actual_name" not in cols:
                    conn.execute(text("ALTER TABLE leetcode_users ADD COLUMN actual_name VARCHAR(150) DEFAULT 'N/A'"))
                    conn.commit()
            except Exception:
                pass

def get_db():
    """FastAPI dependency for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def get_db_session():
    """Context manager for background tasks and scripts."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
