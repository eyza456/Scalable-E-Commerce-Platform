from contextlib import asynccontextmanager
import os
import pika

from fastapi import FastAPI, HTTPException

from app.routers import notifications
from app.rabbitmq import start_consumer


@asynccontextmanager
async def lifespan(app: FastAPI):

    import threading

    print("====================================")
    print("INICIANDO NOTIFICATION SERVICE")
    print("====================================")

    thread = threading.Thread(
        target=start_consumer,
        daemon=True
    )

    thread.start()

    yield

    print("Notification Service detenido")


app = FastAPI(
    title="Notification Service",
    description="Microservicio encargado de gestionar notificaciones",
    version="1.0.0",
    lifespan=lifespan
)


app.include_router(
    notifications.router
)


@app.get("/")
def root():

    return {
        "service": "Notification Service",
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
        connection = pika.BlockingConnection(pika.ConnectionParameters(
            host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
            port=int(os.getenv("RABBITMQ_PORT", "5672")),
            connection_attempts=1, retry_delay=0, socket_timeout=1, stack_timeout=2,
        ))
        connection.close()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="notification rabbitmq unavailable") from exc
    return {"status": "ready", "dependencies": {"rabbitmq": "ready"}}
