from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, get_current_user
from app.database import get_db
from app.users import service
from app.users.schemas import CreateUser, UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=201)
def register(data: CreateUser, db: Session = Depends(get_db)):
    return service.create_user(db, data)


@router.get("/{user_id}", response_model=UserOut)
def find_one(
    user_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    return service.get_user(db, user_id)
