from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.orders import service
from app.orders.models import Order, OrderStatus
from app.orders.schemas import CreateOrder


def test_rejects_zero_total():
    with pytest.raises(HTTPException) as error:
        service.create_order(MagicMock(), 1, CreateOrder(total=Decimal("0")))
    assert error.value.status_code == 400


def test_does_not_cancel_paid_orders():
    db = MagicMock()
    db.scalar.return_value = Order(id=2, user_id=1, total=Decimal("5"), status=OrderStatus.PAID)
    with pytest.raises(HTTPException) as error:
        service.cancel_order(db, 1, 2)
    assert error.value.status_code == 400
