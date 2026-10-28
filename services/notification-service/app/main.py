from contextlib import asynccontextmanager

from fastapi import FastAPI

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