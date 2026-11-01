from app.http_client import close as close_http_pool
import os
import pika
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from threading import Event, Thread
from sqlalchemy import text
from app.outbox import run_outbox
from app.inventory import run_recovery

from app.schema import initialize_schema
from app.database import engine
from app.models import Payment
from app.routers import payments


@asynccontextmanager
async def lifespan(app):
    initialize_schema()
    stop = Event()
    worker = Thread(target=run_outbox, args=(stop,), daemon=True)
    recovery = Thread(target=run_recovery, args=(stop,), daemon=True)
    worker.start()
    recovery.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=2)
        recovery.join(timeout=2)
        close_http_pool()


app = FastAPI(
    lifespan=lifespan,
    title="Payment Service",
    description="Microservicio encargado del procesamiento de pagos",
    version="1.0.0",
)


app.include_router(payments.router)


@app.get("/")
def root():

    return {"service": "Payment Service", "status": "running"}


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
        raise HTTPException(status_code=503, detail="payment dependencies unavailable") from exc
    return {"status": "ready", "dependencies": {"database": "ready", "rabbitmq": "ready"}}
