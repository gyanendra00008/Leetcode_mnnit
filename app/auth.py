import os
import hmac
import hashlib
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from config import settings
from app.database import get_db, get_db_session
from app.models import AdminSession, AdminAuditLog

logger = logging.getLogger("leetcode_collector")

def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Hash a password using PBKDF2 with SHA-256 and a random salt."""
    if salt is None:
        salt = os.urandom(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return f"{salt.hex()}${pwd_hash.hex()}"

def verify_password(plain_password: str, stored_hash_or_plain: str) -> bool:
    """
    Verifies a plain password against a stored PBKDF2 hash or configured plaintext.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not plain_password or not stored_hash_or_plain:
        return False

    if "$" in stored_hash_or_plain:
        try:
            salt_hex, hash_hex = stored_hash_or_plain.split("$", 1)
            salt = bytes.fromhex(salt_hex)
            expected_hash = bytes.fromhex(hash_hex)
            computed = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 100000)
            return hmac.compare_digest(computed, expected_hash)
        except Exception:
            return False

    # Plain text comparison using constant-time digest
    return hmac.compare_digest(plain_password.encode("utf-8"), stored_hash_or_plain.encode("utf-8"))

def create_admin_session(db: Session, username: str) -> str:
    """Create a persistent admin session token with expiration."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.SESSION_EXPIRE_HOURS)

    admin_session = AdminSession(
        token=token,
        username=username,
        expires_at=expires_at
    )
    db.add(admin_session)
    db.commit()
    return token

def validate_admin_session(db: Session, token: str) -> Optional[AdminSession]:
    """Validate a session token. Deletes token if expired."""
    if not token:
        return None

    session = db.query(AdminSession).filter(AdminSession.token == token).first()
    if not session:
        return None

    # Handle timezone comparison safely
    now = datetime.now(timezone.utc)
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if now > expires:
        # Expired: clean up
        db.delete(session)
        db.commit()
        return None

    return session

def destroy_admin_session(db: Session, token: str) -> bool:
    """Invalidate and remove an admin session token."""
    if not token:
        return False
    session = db.query(AdminSession).filter(AdminSession.token == token).first()
    if session:
        db.delete(session)
        db.commit()
        return True
    return False

def get_session_token_from_request(request: Request) -> Optional[str]:
    """Extract session token from HttpOnly cookie or Authorization Bearer header."""
    # 1. Check cookie
    cookie_token = request.cookies.get("admin_session")
    if cookie_token:
        return cookie_token

    # 2. Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    # 3. Check X-Admin-Token custom header
    custom_token = request.headers.get("X-Admin-Token")
    if custom_token:
        return custom_token.strip()

    return None

def get_current_admin(request: Request, db: Session = Depends(get_db)) -> str:
    """
    Strict FastAPI dependency for Admin-Only protected routes.
    Rejects unauthenticated requests with HTTP 401 Unauthorized.
    """
    token = get_session_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    session = validate_admin_session(db, token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired admin session. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return session.username

def get_optional_admin(request: Request, db: Session = Depends(get_db)) -> Optional[str]:
    """Non-blocking check for admin session, returns username or None."""
    token = get_session_token_from_request(request)
    if not token:
        return None
    session = validate_admin_session(db, token)
    return session.username if session else None

def log_audit_event(
    action: str,
    target: Optional[str] = None,
    status: str = "SUCCESS",
    details: Optional[str] = None,
    admin_username: str = "admin"
):
    """Logs an administrative operation to SQLite and Python logger without exposing secrets."""
    logger.info(f"[AUDIT] {admin_username} | {action} | target={target or 'N/A'} | status={status} | {details or ''}")
    try:
        with get_db_session() as session:
            entry = AdminAuditLog(
                admin_username=admin_username,
                action=action,
                target=target,
                status=status,
                details=details
            )
            session.add(entry)
    except Exception as e:
        logger.error(f"[AUDIT] Failed to persist audit log: {e}")
