from fastapi import FastAPI

from app.database import Base, engine
from app.models import User
from app.routers import auth,users

# Crea las tablas en la base de datos
Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="User Service",
    description="Microservicio encargado de usuarios y autenticación",
    version="1.0.0"
)

app.include_router(auth.router)
app.include_router(users.router)


@app.get("/")
def root():
    return {
        "service": "User Service",
        "status": "running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }