from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.orders.models import Order, OrderStatus
from app.orders.schemas import CreateOrder
from app.users.service import get_user


def create_order(db: Session, user_id: int, data: CreateOrder) -> Order:
    if data.total <= 0:
        raise HTTPException(status_code=400, detail="Total must be greater than zero")
    user = get_user(db, user_id)
    order = Order(user_id=user.id, total=data.total, note=data.note)
    db.add(order)
    db.commit()
    return order


def list_orders(db: Session, user_id: int) -> list[Order]:
    query = select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
    return list(db.scalars(query))


def cancel_order(db: Session, user_id: int, order_id: int) -> Order:
    order = db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user_id))
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    if order.status == OrderStatus.PAID:
        raise HTTPException(status_code=400, detail="Paid orders cannot be cancelled")
    order.status = OrderStatus.CANCELLED
    db.commit()
    return order
