from app.http_client import close as close_http_pool
import threading
import os
import pika
from contextlib import asynccontextmanager
from app.cancellations import run_recovery
from app.checkouts import run_recovery as run_checkout_recovery


from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app.schema import initialize_schema
from app.database import engine
from app.models import Order, OrderItem
from app.routers import orders
from app.rabbitmq import start_consumer


@asynccontextmanager
async def lifespan(app):
    initialize_schema()
    stop = threading.Event()
    worker = threading.Thread(target=run_recovery, args=(stop,), daemon=True)
    checkout_worker = threading.Thread(
        target=run_checkout_recovery, args=(stop,), daemon=True
    )
    consumer = threading.Thread(target=start_consumer, args=(stop,), daemon=True)
    consumer.start()
    worker.start()
    checkout_worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=2)
        checkout_worker.join(timeout=2)
        consumer.join(timeout=2)
        close_http_pool()


app = FastAPI(
    lifespan=lifespan,
    title="Order Service",
    description="Microservicio encargado de gestionar órdenes",
    version="1.0.0",
)


app.include_router(orders.router)


@app.get("/")
def root():

    return {"service": "Order Service", "status": "running"}


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
        raise HTTPException(status_code=503, detail="order dependencies unavailable") from exc
    return {"status": "ready", "dependencies": {"database": "ready", "rabbitmq": "ready"}}
