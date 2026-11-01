from contextlib import asynccontextmanager

import threading
import os

import pika
from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app.routers import products, reservations, categories
from app.rabbitmq import start_consumer
from app.database import engine


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


@app.get("/ready")
def readiness_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        connection = pika.BlockingConnection(pika.ConnectionParameters(
            host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
            port=int(os.getenv("RABBITMQ_PORT", "5672")),
            connection_attempts=1, retry_delay=0, socket_timeout=1, stack_timeout=2,
        ))
        connection.close()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="product dependencies unavailable") from exc
    return {"status": "ready", "dependencies": {"database": "ready", "rabbitmq": "ready"}}
