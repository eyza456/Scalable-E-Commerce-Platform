"""Sondas de auditoria: registran limitaciones, no forman parte de la suite de regresion.

Ejecutar desde la raiz. Datos HTTP propios, esquema PostgreSQL y clave Redis
exclusivos. No modifica el codigo funcional ni oculta los resultados negativos.
"""
import json
from pathlib import Path
import uuid

from gateway_stability import api, exchange
from smoke_purchase import service_code
from smoke_inventory import cleanup


def cart_concurrency():
    return json.loads(service_code("cart-service", '''
import json,threading,uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock,patch
from app.routers import cart
from app.schemas import CartItemCreate
real=cart.redis_client
uid="audit-"+uuid.uuid4().hex
key="cart:"+uid
barrier=threading.Barrier(2)
class SynchronizedRedis:
    def get(self,k):
        snapshot=real.get(k)
        barrier.wait(timeout=10)
        return snapshot
    def set(self,*args,**kwargs):
        return real.set(*args,**kwargs)
response=Mock(status_code=200)
response.json.return_value={"id":1,"name":"Audit","price":"1.00","stock":10,"is_active":True}
try:
    def add(_):
        cart.add_item_to_cart(CartItemCreate(product_id=1,quantity=1),{"id":uid})
    with patch.object(cart,"redis_client",SynchronizedRedis()),patch.object(cart.httpx,"get",return_value=response):
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(add,range(2)))
    result=json.loads(real.get(key))
    print(json.dumps({"expected_quantity":2,"observed_quantity":result["items"][0]["quantity"],
        "scope":"Redis real; lecturas sincronizadas; consulta de producto simulada"}))
finally:
    real.delete(key)
'''))


def duplicate_checkout():
    return json.loads(service_code("order-service", '''
import json,threading,uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock,patch
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker
from app.database import Base,engine
from app.models import Order
from app.routers import orders
schema="audit_checkout_"+uuid.uuid4().hex
with engine.begin() as c:c.execute(text(f'CREATE SCHEMA "{schema}"'))
audit=create_engine(engine.url,connect_args={"options":f"-csearch_path={schema}"})
Base.metadata.create_all(audit)
sessions=sessionmaker(bind=audit)
barrier=threading.Barrier(2)
response=Mock(status_code=200)
response.json.return_value={"items":[{"product_id":1,"name":"Audit","quantity":2,"price":"1.00","subtotal":"2.00"}],"total":"2.00"}
def same_snapshot(*args,**kwargs):
    barrier.wait(timeout=10)
    return response
def create(_):
    with sessions() as db:return orders.create_order({"id":42,"token":"audit"},db).id
try:
    with patch.object(orders.httpx,"get",side_effect=same_snapshot),patch.object(orders.httpx,"delete",return_value=Mock(status_code=200)):
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(create,range(2)))
    print(json.dumps({"orders_created_from_same_cart":len(ids),"expected_orders":1,
        "scope":"PostgreSQL aislado; dos respuestas de carrito sincronizadas"}))
finally:
    audit.dispose()
    with engine.begin() as c:c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
'''))


def stale_checkout():
    marker="audit-checkout-"+uuid.uuid4().hex
    user=product=None
    orders=[]
    try:
        user=api("/api/auth/register","POST",{"name":marker,"email":marker+"@example.com","password":"Audit-Test-2026"},expected=201)
        token=api("/api/auth/login","POST",{"email":user["email"],"password":"Audit-Test-2026"})["access_token"]
        admin=service_code("payment-service",'''
import sys
from datetime import datetime,timedelta,timezone
from jose import jwt
from app.core.config import settings
print(jwt.encode({"sub":sys.argv[1],"role":"admin","email":sys.argv[2],"exp":datetime.now(timezone.utc)+timedelta(minutes=2)},settings.SECRET_KEY,algorithm=settings.JWT_ALGORITHM))
''',user["id"],user["email"])
        product=api("/api/products/","POST",{"name":marker,"price":"10.00","stock":2},admin,expected=201)
        api("/api/cart/items","POST",{"product_id":product["id"],"quantity":2},token,expected=201)
        api(f'/api/products/{product["id"]}',"PUT",{"price":"20.00","stock":0,"is_active":False},admin)
        status,data,_,_=exchange("/api/orders","POST",token=token)
        if status==201:
            orders.append(data)
        return {"checkout_http_status":status,"expected_status":"rechazo antes de crear el pedido",
                "catalog_stock":0,"catalog_active":False,"catalog_unit_price":"20.00",
                "order_total":str(data.get("total")),"order_unit_price":str(data.get("items",[{}])[0].get("price")),
                "scope":"HTTP real a traves del gateway; registros propios"}
    finally:
        cleanup(user,product,orders)


def registration_limits():
    import urllib.error,urllib.request
    from gateway_stability import BASE
    marker="audit-input-"+uuid.uuid4().hex
    cases=[("password_80_bytes",marker+"@example.com","x"*80),
           ("email_over_database_limit",marker+"@"+"b"*60+"."+"c"*50+".com","Audit-Test-2026")]
    results=[]
    try:
        for name,email,password in cases:
            request=urllib.request.Request(BASE+"/api/auth/register",method="POST",
                headers={"Content-Type":"application/json"},data=json.dumps({"name":marker,"email":email,"password":password}).encode())
            try:
                with urllib.request.urlopen(request,timeout=15) as response:status=response.status
            except urllib.error.HTTPError as exc:
                status=exc.code
                exc.close()
            results.append({"case":name,"http_status":status,"email_length":len(email),"password_bytes":len(password.encode()),
                            "expected":"validacion controlada 4xx o soporte completo; no 500"})
    finally:
        for _,email,_ in cases:
            service_code("user-service",'''
import sys
from sqlalchemy import text
from app.database import engine
with engine.begin() as c:c.execute(text("DELETE FROM users WHERE email=:email"),{"email":sys.argv[1]})
''',email)
    return results


if __name__ == "__main__":
    # Las reproducciones anteriores corresponden al baseline 47c5085.
    # Ejecutar ahora la regresion vigente sin sobrescribir la evidencia historica.
    from smoke_audit_fixes import main
    main()
