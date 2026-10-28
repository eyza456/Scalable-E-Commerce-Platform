import multiprocessing as mp
import os
import time
import traceback

from sqlalchemy.orm import Session

from app import rabbitmq

MESSAGE = {
    "event": "PAYMENT_COMPLETED",
    "order_id": 9005,
    "transaction_id": "TX-RACE-SERVICE-005",
    "items": [
        {"product_id": 9001, "quantity": 2}
    ]
}

_original_flush = Session.flush


def worker(label, barrier, results):
    """
    Ejecuta la función real de Product Service.

    La barrera sincroniza ambos procesos justo antes
    del primer flush que registra el evento.
    """

    original_flush = Session.flush
    synchronized = False

    def synchronized_flush(self, *args, **kwargs):
        nonlocal synchronized

        if not synchronized:
            synchronized = True
            print(
                f"[{label}] Esperando al otro proceso antes de flush()",
                flush=True
            )
            barrier.wait(timeout=30)

        return original_flush(self, *args, **kwargs)

    Session.flush = synchronized_flush

    try:
        print(f"[{label}] Iniciando procesamiento", flush=True)

        rabbitmq.process_payment_completed(MESSAGE)

        results.put((label, "OK"))

    except Exception as exc:
        traceback.print_exc()
        results.put((label, f"ERROR: {exc}"))

    finally:
        Session.flush = original_flush


if __name__ == "__main__":
    ctx = mp.get_context("fork")

    barrier = ctx.Barrier(2)
    results = ctx.Queue()

    processes = [
        ctx.Process(
            target=worker,
            args=(label, barrier, results)
        )
        for label in ("A", "B")
    ]

    for process in processes:
        process.start()

    for process in processes:
        process.join(timeout=60)

    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join()
            print(
                f"[ERROR] Proceso {process.pid} excedió el tiempo",
                flush=True
            )

    print("\n========== RESULTADOS ==========")

    while not results.empty():
        print(results.get())

    print("================================")
