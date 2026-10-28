from contextlib import asynccontextmanager
from app.http_client import close as close_http_pool
from fastapi import FastAPI

from app.routers import cart


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
