"""Mutaciones optimistas atomicas y versionado del carrito en Redis."""
import json
import uuid

from fastapi import HTTPException
from redis.exceptions import RedisError, WatchError


def atomic(client, user_id, change=None, allow_frozen=False):
    key = f"cart:{user_id}"
    for _ in range(50):
        try:
            with client.pipeline() as pipe:
                pipe.watch(key)
                raw = pipe.get(key)
                cart = json.loads(raw) if raw else {"items": []}
                initialized = bool(cart.get("version"))
                cart.setdefault("version", str(uuid.uuid4()))
                cart.setdefault("checkout_id", None)
                cart.setdefault("last_checkout_id", None)
                if change is not None:
                    if cart["checkout_id"] and not allow_frozen:
                        raise HTTPException(409, {"code": "CHECKOUT_IN_PROGRESS", "checkout_id": cart["checkout_id"]})
                    change(cart)
                elif initialized:
                    pipe.unwatch()
                    return cart
                pipe.multi()
                pipe.set(key, json.dumps(cart))
                pipe.execute()
                return cart
        except WatchError:
            continue
        except RedisError as exc:
            raise HTTPException(503, "Carrito temporalmente no disponible") from exc
    raise HTTPException(409, {"code": "CART_BUSY", "message": "Reintentar la operacion"})


def changed(cart):
    cart["version"] = str(uuid.uuid4())
    cart["last_checkout_id"] = None


def prepare(client, user_id, checkout_id):
    def change(cart):
        if cart["checkout_id"] == checkout_id:
            return
        if cart["checkout_id"] or cart["version"] != checkout_id:
            raise HTTPException(409, {"code": "STALE_CART", "message": "Actualizar el carrito"})
        if not cart["items"]:
            raise HTTPException(409, {"code": "EMPTY_CART"})
        cart["checkout_id"] = checkout_id
    return atomic(client, user_id, change, allow_frozen=True)


def finish(client, user_id, checkout_id, committed):
    def change(cart):
        if cart["checkout_id"] != checkout_id:
            # No vaciar nunca una version posterior, ni un checkout diferente.
            return
        cart["checkout_id"] = None
        cart["version"] = str(uuid.uuid4())
        cart["last_checkout_id"] = checkout_id if committed else None
        if committed:
            cart["items"] = []
    return atomic(client, user_id, change, allow_frozen=True)
