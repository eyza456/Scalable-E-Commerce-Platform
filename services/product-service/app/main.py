
import threading

from fastapi import FastAPI

from app.routers import products, reservations, categories
from app.rabbitmq import start_consumer


app = FastAPI(
    title="Product Service",
    description="Microservicio encargado de la gestión de productos",
    version="1.0.0"
)


app.include_router(
    products.router
)
app.include_router(reservations.router)
app.include_router(reservations.release_router)
app.include_router(categories.router)


@app.get("/")
def root():
    return {
        "service": "Product Service",
        "status": "running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


def rabbitmq_worker():
    start_consumer()


threading.Thread(
    target=rabbitmq_worker,
    daemon=True
).start()
