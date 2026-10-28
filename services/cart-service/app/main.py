from fastapi import FastAPI

from app.routers import cart


app = FastAPI(
    title="Cart Service",
    description="Microservicio encargado de la gestión del carrito de compras",
    version="1.0.0"
)


app.include_router(
    cart.router
)


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