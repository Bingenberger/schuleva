from __future__ import annotations
import time
import secrets
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import bcrypt

from fastapi import Request, HTTPException, status

from app.db import get_db
from app.models import User

# Brute-force tracking: {ip: [(timestamp, ...), ...]}
_failed_attempts: dict[str, list[float]] = defaultdict(list)
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60  # 15 minutes


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _clean_attempts(ip: str) -> None:
    cutoff = time.time() - LOCKOUT_SECONDS
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if t > cutoff]


def is_locked_out(ip: str) -> bool:
    _clean_attempts(ip)
    return len(_failed_attempts[ip]) >= MAX_ATTEMPTS


def record_failed(ip: str) -> None:
    _failed_attempts[ip].append(time.time())


def clear_attempts(ip: str) -> None:
    _failed_attempts.pop(ip, None)


def authenticate_user(username: str, password: str) -> Optional[User]:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, role, must_change_password FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return User(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        must_change_password=bool(row["must_change_password"]),
    )


def get_current_user(request: Request) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, username, role, must_change_password FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return User(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        must_change_password=bool(row["must_change_password"]),
    )


def require_login(request: Request) -> User:
    user = get_current_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/admin/login"},
        )
    return user


def require_admin(request: Request) -> User:
    user = require_login(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Nur für Schulleitung zugänglich")
    return user


def create_user(username: str, password: str, role: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, must_change_password, created_at)"
            " VALUES (?, ?, ?, 1, ?)",
            (username, hash_password(password), role, now),
        )
        conn.commit()
    finally:
        conn.close()


def delete_user(user_id: int) -> None:
    conn = get_db()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def generate_csrf_token(request: Request) -> str:
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_hex(32)
    return request.session["csrf_token"]


def validate_csrf(request: Request, token: str) -> None:
    expected = request.session.get("csrf_token")
    if not expected or not secrets.compare_digest(expected, token):
        raise HTTPException(status_code=403, detail="Ungültiges CSRF-Token")


def create_admin_user(username: str, password: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, must_change_password, created_at) VALUES (?, ?, 'schulleitung', 1, ?)",
            (username, hash_password(password), now),
        )
        conn.commit()
    finally:
        conn.close()


def change_password(user_id: int, new_password: str) -> None:
    conn = get_db()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
            (hash_password(new_password), user_id),
        )
        conn.commit()
    finally:
        conn.close()
