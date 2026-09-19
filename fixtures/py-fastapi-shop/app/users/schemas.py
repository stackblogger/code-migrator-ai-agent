from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class CreateUser(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    created_at: datetime
