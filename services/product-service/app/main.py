from contextlib import asynccontextmanager

import threading

from fastapi import FastAPI

from app.routers import products, reservations, categories
from app.rabbitmq import start_consumer


@asynccontextmanager
async def lifespan(app):
    stop = threading.Event()
    consumer = threading.Thread(target=start_consumer, args=(stop,), daemon=True)
    consumer.start()
    try:
        yield
    finally:
        stop.set()
        consumer.join(timeout=2)


app = FastAPI(
    lifespan=lifespan,
    title="Product Service",
    description="Microservicio encargado de la gestión de productos",
    version="1.0.0",
)


app.include_router(products.router)
app.include_router(reservations.router)
app.include_router(reservations.release_router)
app.include_router(categories.router)


@app.get("/")
def root():
    return {"service": "Product Service", "status": "running"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
