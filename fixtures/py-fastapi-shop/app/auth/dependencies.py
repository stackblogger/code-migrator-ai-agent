from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException

from app.auth.security import decode_token


@dataclass
class CurrentUser:
    id: int
    role: str


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = decode_token(authorization.removeprefix("Bearer "))
    except jwt.PyJWTError as error:
        raise HTTPException(status_code=401, detail="Invalid token") from error
    return CurrentUser(id=int(payload["sub"]), role=payload["role"])
