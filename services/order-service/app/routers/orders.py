import httpx

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import Session, selectinload
from typing import Literal
from app.cancellations import finish_cancellation

from app.core.config import settings
from app.core.security import get_current_user, require_admin
from app.database import get_db
from app.models import Order, OrderItem
from app.schemas import OrderResponse, OrderStatusUpdate
from app.core.internal_security import verify_internal_service


router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)


@router.get("/health")
def orders_health():

    return {
        "service": "Order Service",
        "status": "healthy"
    }


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED
)
def create_order(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    user_id = current_user["id"]

    # ==================================
    # 1. OBTENER CARRITO
    # ==================================

    try:

        response = httpx.get(
            f"{settings.CART_SERVICE_URL}/cart",
            headers={
                "Authorization": f"Bearer {current_user['token']}"
            },
            timeout=10.0
        )

    except httpx.RequestError:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo conectar con Cart Service"
        )

    if response.status_code != 200:

        raise HTTPException(
            status_code=response.status_code,
            detail="No se pudo obtener el carrito"
        )

    cart = response.json()

    # ==================================
    # 2. VALIDAR CARRITO
    # ==================================

    items = cart.get("items", [])

    if not items:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede crear una orden con el carrito vacío"
        )

    # ==================================
    # 3. CREAR ORDEN
    # ==================================

    order = Order(
        user_id=user_id,
        status="PENDING",
        total=cart["total"]
    )

    db.add(order)

    db.flush()

    # ==================================
    # 4. CREAR ITEMS DE LA ORDEN
    # ==================================

    for item in items:

        order_item = OrderItem(
            order_id=order.id,
            product_id=item["product_id"],
            product_name=item["name"],
            quantity=item["quantity"],
            price=item["price"],
            subtotal=item["subtotal"]
        )

        db.add(order_item)

    # ==================================
    # 5. GUARDAR
    # ==================================

    db.commit()

    db.refresh(order)

    # ==================================
    # 6. VACIAR CARRITO
    # ==================================

    try:

        clear_response = httpx.delete(
            f"{settings.CART_SERVICE_URL}/cart",
            headers={
                "Authorization": f"Bearer {current_user['token']}"
            },
            timeout=10.0
        )

        if clear_response.status_code not in [200, 404]:

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="La orden fue creada pero no se pudo vaciar el carrito"
            )

    except httpx.RequestError:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La orden fue creada pero no se pudo vaciar el carrito"
        )

    return order

@router.get("", response_model=list[OrderResponse])
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    order_status: Literal["PENDING", "CANCELLING", "CANCELLED", "PAID", "PROCESSING", "SHIPPED", "DELIVERED"] | None = Query(None, alias="status"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Order).options(selectinload(Order.items)).filter(Order.user_id == current_user["id"])
    if order_status is not None:
        query = query.filter(Order.status == order_status)
    return query.order_by(Order.created_at.desc(), Order.id.desc()).offset(skip).limit(limit).all()


@router.post("/{order_id}/cancel", response_model=OrderResponse,
             responses={202: {"model": OrderResponse, "description": "Cancelacion pendiente de recuperacion"},
                        409: {"description": "Pago confirmado o estado no cancelable"}})
def cancel_order(
    order_id: int,
    response: Response,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = (db.query(Order).filter(Order.id == order_id, Order.user_id == current_user["id"])
             .with_for_update().first())
    if order is None:
        raise HTTPException(404, "La orden no existe")
    if order.status == "CANCELLED":
        return order
    if order.status not in ("PENDING", "CANCELLING"):
        raise HTTPException(409, "Solo se pueden cancelar pedidos pendientes; un pago confirmado requiere reembolso")
    order.status = "CANCELLING"
    db.commit()
    order = finish_cancellation(db, order_id)
    if order.status not in ("CANCELLED", "CANCELLING"):
        raise HTTPException(409, "El pago se confirmo antes de la cancelacion; requiere reembolso")
    if order.status == "CANCELLING":
        response.status_code = 202
    return order


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user["id"]

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.user_id == user_id
        )
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La orden no existe"
        )

    return order


@router.patch("/{order_id}/status", response_model=OrderResponse)
def update_order_status(
    order_id: int,
    status_data: OrderStatusUpdate,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Actualiza el estado administrativo de una orden.

    Restricciones:
    - Solo administradores.
    - PAID no puede establecerse manualmente.
    - Se respetan las transiciones autorizadas.
    """

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La orden no existe"
        )

    requested_status = status_data.status

    # PAID pertenece exclusivamente al flujo de pagos.
    if requested_status == "PAID":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "El estado PAID solo puede establecerse "
                "mediante un pago verificado"
            )
        )

    # Transiciones administrativas permitidas.
    allowed_transitions = {
        "PENDING": set(),
        "PAID": {"PROCESSING"},
        "PROCESSING": {"SHIPPED"},
        "SHIPPED": {"DELIVERED"},
        "DELIVERED": set(),
        "CANCELLED": set(),
    }

    current_status = order.status

    if current_status not in allowed_transitions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La orden tiene un estado desconocido"
        )

    if requested_status not in allowed_transitions[current_status]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Transicion no permitida: "
                f"{current_status} -> {requested_status}"
            )
        )

    order.status = requested_status

    db.commit()
    db.refresh(order)

    return order


@router.get(
    "/internal/{order_id}",
    dependencies=[Depends(verify_internal_service)]
)
def get_internal_order(
    order_id: int,
    db: Session = Depends(get_db)
):
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Orden no encontrada"
        )

    return {
        "order_id": order.id,
        "user_id": order.user_id,
        "status": order.status,
        "items": [
            {
                "product_id": item.product_id,
                "quantity": item.quantity
            }
            for item in order.items
        ]
    }
