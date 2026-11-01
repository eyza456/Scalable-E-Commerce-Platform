from contextlib import asynccontextmanager
from app.http_client import close as close_http_pool
from fastapi import FastAPI, HTTPException

from app.routers import cart
from app.redis_client import redis_client


@asynccontextmanager
async def lifespan(app):
    try:
        yield
    finally:
        close_http_pool()


app = FastAPI(
    lifespan=lifespan,
    title="Cart Service",
    description="Microservicio encargado de la gestión del carrito de compras",
    version="1.0.0"
)


app.include_router(
    cart.router
)
app.include_router(cart.internal_router)


@app.get("/")
def root():

    return {
        "service": "Cart Service",
        "status": "running"
    }


@app.get("/health")
def health_check():

    return {
        "status": "healthy"
    }


@app.get("/ready")
def readiness_check():
    try:
        redis_client.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="cart redis unavailable") from exc
    return {"status": "ready", "dependencies": {"redis": "ready"}}
