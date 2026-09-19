import uvicorn
from fastapi import FastAPI

from app.config import PORT
from app.database import Base, engine
from app.orders.router import router as orders_router
from app.users.router import router as users_router

app = FastAPI(title="Shop")
app.include_router(users_router)
app.include_router(orders_router)


@app.on_event("startup")
def create_tables() -> None:
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
