import os

PORT = int(os.getenv("PORT", "8000"))
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./shop.db")
JWT_SECRET = os.environ["JWT_SECRET"] if "JWT_SECRET" in os.environ else "change-me"
JWT_EXPIRES_IN = int(os.getenv("JWT_EXPIRES_IN", "3600"))
