from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, get_current_user
from app.database import get_db
from app.orders import service
from app.orders.schemas import CreateOrder, OrderOut

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderOut, status_code=201)
def create(
    data: CreateOrder,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    return service.create_order(db, user.id, data)


@router.get("", response_model=list[OrderOut])
def list_mine(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    return service.list_orders(db, user.id)


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel(
    order_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    return service.cancel_order(db, user.id, order_id)
