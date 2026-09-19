import hashlib
from datetime import UTC, datetime, timedelta

import jwt

from app.config import JWT_EXPIRES_IN, JWT_SECRET


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def issue_token(user_id: int, role: str) -> str:
    expires = datetime.now(UTC) + timedelta(seconds=JWT_EXPIRES_IN)
    return jwt.encode({"sub": str(user_id), "role": role, "exp": expires}, JWT_SECRET, "HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
