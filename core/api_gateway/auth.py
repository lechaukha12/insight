"""
Insight Monitoring System - Authentication Module v5.0.0
JWT auth with RBAC (admin/operator/viewer).
"""

import os
import time
from functools import wraps

import bcrypt
import jwt
from fastapi import HTTPException, Request

JWT_SECRET = os.getenv("JWT_SECRET", "insight-jwt-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

DEFAULT_ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "insight2024")

# Role hierarchy: admin > operator > viewer
ROLE_PERMISSIONS = {
    "admin": ["admin", "operator", "viewer"],
    "operator": ["operator", "viewer"],
    "viewer": ["viewer"],
}


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
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


async def get_current_user(request: Request) -> dict | None:
    """Extract user from JWT token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    payload = verify_token(auth_header[7:])
    if not payload:
        return None
    return {"id": payload["sub"], "username": payload["username"], "role": payload.get("role", "viewer")}


async def require_auth(request: Request) -> dict:
    """Require valid JWT token."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_role(allowed_roles: list[str]):
    """Factory: create dependency that requires specific roles."""
    async def _check(request: Request) -> dict:
        user = await require_auth(request)
        user_role = user.get("role", "viewer")
        # Check if user's role grants access to any allowed role
        user_perms = ROLE_PERMISSIONS.get(user_role, [])
        if not any(r in user_perms for r in allowed_roles):
            raise HTTPException(status_code=403, detail=f"Role '{user_role}' not authorized. Required: {allowed_roles}")
        return user
    return _check


def ensure_default_admin():
    """Create default admin user if no users exist."""
    from shared.database.db import get_user_by_username, create_user
    existing = get_user_by_username(DEFAULT_ADMIN_USER)
    if not existing:
        pw_hash = hash_password(DEFAULT_ADMIN_PASS)
        create_user(DEFAULT_ADMIN_USER, pw_hash, "admin")
        print(f"[AUTH] Default admin created: {DEFAULT_ADMIN_USER}")
    else:
        print(f"[AUTH] Admin exists: {DEFAULT_ADMIN_USER}")
