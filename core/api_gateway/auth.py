"""
Insight Monitoring System - Authentication Module
JWT-based authentication for dashboard access.
Uses bcrypt directly (passlib has compatibility issues with bcrypt v5+).
"""

import os
import time

import bcrypt
import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "insight-jwt-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

DEFAULT_ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "insight2024")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: str, username: str, role: str = "admin") -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY_HOURS * 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict | None:
    """Verify JWT token and return payload or None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def ensure_default_admin():
    """Create default admin user if no users exist."""
    from shared.database.db import get_user_by_username, create_user
    
    existing = get_user_by_username(DEFAULT_ADMIN_USER)
    if not existing:
        pw_hash = hash_password(DEFAULT_ADMIN_PASS)
        create_user(DEFAULT_ADMIN_USER, pw_hash, "admin")
        print(f"[AUTH] Default admin user created: {DEFAULT_ADMIN_USER}")
    else:
        print(f"[AUTH] Admin user exists: {DEFAULT_ADMIN_USER}")
