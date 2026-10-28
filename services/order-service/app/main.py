import threading
from contextlib import asynccontextmanager
from app.cancellations import run_recovery


from fastapi import FastAPI

from app.database import Base, engine
from app.models import Order, OrderItem
from app.routers import orders
from app.rabbitmq import start_consumer

Base.metadata.create_all(
    bind=engine
)


@asynccontextmanager
async def lifespan(app):
    stop = threading.Event()
    worker = threading.Thread(target=run_recovery, args=(stop,), daemon=True)
    worker.start()
    yield
    stop.set()
    worker.join(timeout=2)


app = FastAPI(
    lifespan=lifespan,
    title="Order Service",
    description="Microservicio encargado de gestionar órdenes",
    version="1.0.0"
)


app.include_router(
    orders.router
)


@app.get("/")
def root():

    return {
        "service": "Order Service",
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
