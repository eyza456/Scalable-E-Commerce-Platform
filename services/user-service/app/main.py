from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app.schema import initialize_schema
from app.models import User
from app.database import engine
from app.routers import auth, users


@asynccontextmanager
async def lifespan(app):
    initialize_schema()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="User Service",
    description="Microservicio encargado de usuarios y autenticación",
    version="1.0.0",
)

app.include_router(auth.router)
app.include_router(users.router)


@app.get("/")
def root():
    return {"service": "User Service", "status": "running"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/ready")
def readiness_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="user database unavailable") from exc
    return {"status": "ready", "dependencies": {"database": "ready"}}
