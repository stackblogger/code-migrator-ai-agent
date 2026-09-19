from migrator.adapters.frameworks.fastapi import FastApiAdapter
from migrator.adapters.frameworks.sqlalchemy import SqlAlchemyAdapter
from migrator.concepts.models import ConceptKind
from tests.unit.concepts.helpers import by_key, extract

APP = {
    "app/auth.py": """
from fastapi import HTTPException, status

def require_user(token: str | None = None):
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no")

def get_db():
    yield None
""",
    "app/schemas.py": """
from pydantic import BaseModel, EmailStr, Field

class Base(BaseModel):
    email: EmailStr

class Signup(Base):
    name: str = Field(min_length=2, max_length=20)
    age: int | None = Field(default=None, ge=18)
    plan: str = "free"
""",
    "app/routes.py": """
from fastapi import APIRouter, Depends, FastAPI, HTTPException, status

router = APIRouter(prefix="/accounts")
app = FastAPI()
app.include_router(router, prefix="/v1")

@router.post("/{account_id}/signup", status_code=status.HTTP_201_CREATED)
def signup(account_id: int, data: Signup, db=Depends(get_db), user=Depends(require_user)):
    raise HTTPException(status_code=409, detail="exists")

@router.get("", dependencies=[Depends(require_user)])
def list_accounts():
    return []

@app.get("/health")
def health():
    raise HTTPException(status_code=code)
""",
}


def test_routes_auth_and_body(make_repo):
    result = extract(make_repo, FastApiAdapter(), APP)
    routes = by_key(result, ConceptKind.ROUTE)
    signup = routes["POST /accounts/{}/signup"]
    assert (signup["status"], signup["auth"], signup["body"]) == (201, True, "Signup")
    assert signup["guards"] == ["require_user"]  # get_db does not raise 401, so it is not auth
    assert routes["GET /accounts"]["auth"] is True  # from dependencies=[...]
    assert routes["GET /health"] == {**routes["GET /health"], "status": 200, "auth": False}


def test_pydantic_fields_including_parent_model(make_repo):
    fields = by_key(extract(make_repo, FastApiAdapter(), APP), ConceptKind.INPUT_FIELD)
    prefix = "POST /accounts/{}/signup body."
    assert fields[prefix + "name"] == {
        "constraints": ["max_length=20", "min_length=2", "string"],
        "required": True,
    }
    assert fields[prefix + "age"] == {"constraints": ["int", "min=18"], "required": False}
    assert fields[prefix + "plan"]["required"] is False


def test_errors_and_notes(make_repo):
    result = extract(make_repo, FastApiAdapter(), APP)
    assert set(by_key(result, ConceptKind.ERROR)) == {"HTTP 401", "HTTP 409"}
    notes = " ".join(result.notes)
    assert "include_router(prefix=...)" in notes
    assert "unknown status" in notes


MODELS = {
    "models.py": """
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

class Author(Base):
    __tablename__ = "authors"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    bio: Mapped[str | None] = mapped_column()
    nick = Column("nickname", String(20))
    strict = Column(String(5), nullable=False)
    editor_id: Mapped[int] = mapped_column(ForeignKey("editors.id"))

class NotATable:
    x = Column(Integer)
""",
}


def test_sqlalchemy_columns(make_repo):
    result = extract(make_repo, SqlAlchemyAdapter(), MODELS)
    columns = by_key(result, ConceptKind.COLUMN)
    assert columns["authors.id"]["primary_key"] is True
    assert columns["authors.email"] == {"nullable": False, "unique": True, "primary_key": False}
    assert columns["authors.bio"]["nullable"] is True
    assert columns["authors.nickname"]["nullable"] is True  # plain Column() default
    assert columns["authors.strict"]["nullable"] is False
    assert columns["authors.editor_id"]["references"] == "editors"
    assert set(by_key(result, ConceptKind.TABLE)) == {"authors"}
