from migrator.adapters.languages.python.parser import parse_python

SOURCE = b"""
import os
import a.b as c, d
from typing import TYPE_CHECKING
from ..orders import models as m, service
from . import *

if TYPE_CHECKING:
    from app.users.models import User

API_KEY = os.getenv("API_KEY")
SECRET = os.environ["SECRET"]


@router.get("/")
async def handler():
    from app.lazy import thing
    return os.environ.get("LAZY_KEY")


class Order(Base):
    id: Mapped[int] = mapped_column()

    @property
    def label(self):
        return ""

    def _private(self):
        pass


if __name__ == "__main__":
    handler()
"""


def parse():
    return parse_python("app/orders/router.py", SOURCE)


def test_imports():
    imports = {i.module: i for i in parse().imports}
    assert set(imports) == {
        "os",
        "a.b",
        "d",
        "typing",
        "..orders",
        ".",
        "app.users.models",
        "app.lazy",
    }
    assert imports["..orders"].names == ["models", "service"]
    assert imports["."].names == ["*"]
    assert imports["app.users.models"].type_only is True
    assert imports["app.lazy"].type_only is False  # lazy import inside a function


def test_symbols():
    symbols = {(s.parent, s.name): s for s in parse().symbols}
    assert symbols[(None, "handler")].kind == "function"
    assert symbols[(None, "handler")].decorators == ["router.get"]
    assert symbols[(None, "Order")].kind == "class"
    assert symbols[("Order", "id")].kind == "field"
    assert symbols[("Order", "label")].decorators == ["property"]
    assert symbols[("Order", "_private")].exported is False
    assert symbols[(None, "API_KEY")].kind == "variable"


def test_env_vars_and_main_guard():
    parsed = parse()
    assert parsed.env_vars == ["API_KEY", "LAZY_KEY", "SECRET"]
    assert parsed.has_main_guard is True
