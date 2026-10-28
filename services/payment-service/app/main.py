from fastapi import FastAPI
from contextlib import asynccontextmanager
from threading import Event, Thread
from app.outbox import run_outbox
from app.inventory import run_recovery

from app.database import Base, engine
from app.models import Payment
from app.routers import payments


Base.metadata.create_all(
    bind=engine
)


@asynccontextmanager
async def lifespan(app):
    stop = Event()
    worker = Thread(target=run_outbox, args=(stop,), daemon=True)
    recovery = Thread(target=run_recovery, args=(stop,), daemon=True)
    worker.start()
    recovery.start()
    yield
    stop.set()
    worker.join(timeout=2)
    recovery.join(timeout=2)


app = FastAPI(
    lifespan=lifespan,
    title="Payment Service",
    description="Microservicio encargado del procesamiento de pagos",
    version="1.0.0"
)


app.include_router(
    payments.router
)


@app.get("/")
def root():

    return {
        "service": "Payment Service",
        "status": "running"
    }


@app.get("/health")
def health_check():

    return {
        "status": "healthy"
    }
