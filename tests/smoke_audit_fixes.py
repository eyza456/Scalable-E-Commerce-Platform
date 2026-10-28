"""Regresion HTTP real de los hallazgos H-01 a H-05, con limpieza propia."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import uuid

from gateway_stability import api,exchange
from smoke_purchase import service_code,wait_for_inventory
from smoke_inventory import cleanup


def main():
    marker="fixed-audit-"+uuid.uuid4().hex
    email=marker+"@"+"b"*60+"."+"c"*50+".com"
    user=product=None
    orders=[]
    complete=False
    results={}
    try:
        user=api("/api/auth/register","POST",{"name":marker,"email":email,"password":"Fixed-Test-2026"},expected=201)
        results["valid_long_email"]={"length":len(email),"http_status":201}
        for label,password in (("password_80_bytes","x"*80),("password_utf8_74_bytes","é"*37)):
            api("/api/auth/register","POST",{"name":marker,"email":marker+"short@example.com","password":password},expected=422)
            results[label]={"http_status":422}
        token=api("/api/auth/login","POST",{"email":email.upper(),"password":"Fixed-Test-2026"})["access_token"]
        admin=service_code("payment-service",'''
import sys
from datetime import datetime,timedelta,timezone
from jose import jwt
from app.core.config import settings
print(jwt.encode({"sub":sys.argv[1],"email":sys.argv[2],"role":"admin","exp":datetime.now(timezone.utc)+timedelta(minutes=5)},settings.SECRET_KEY,algorithm=settings.JWT_ALGORITHM))
''',user["id"],email)
        product=api("/api/products/","POST",{"name":marker,"price":"10.00","stock":100},admin,expected=201)
        def add(_):
            api("/api/cart/items","POST",{"product_id":product["id"],"quantity":1},token,expected=201)
        with ThreadPoolExecutor(max_workers=10) as pool:list(pool.map(add,range(20)))
        cart=api("/api/cart",token=token)
        assert cart["items"][0]["quantity"]==20
        results["concurrent_cart_adds"]={"requested":20,"observed":20}
        def confirm(_):
            status,data,_,_=exchange("/api/orders","POST",token=token,headers={"Idempotency-Key":cart["version"]})
            assert status in (200,201),(status,data)
            return data
        with ThreadPoolExecutor(max_workers=4) as pool:responses=list(pool.map(confirm,range(4)))
        ids={p["id"] for p in responses}
        assert len(ids)==1
        paid=responses[0];orders.append(paid)
        assert len(api("/api/orders",token=token))==1
        results["concurrent_checkouts"]={"requests":4,"orders_created":1,"checkout_id":cart["version"]}
        payment=api("/api/payments","POST",{"order_id":paid["id"],"method":"card"},token,expected=201)
        assert payment["processed_at"] is not None
        wait_for_inventory(paid["id"])
        results["approved_processed_at"]=payment["processed_at"]

        api("/api/cart/items","POST",{"product_id":product["id"],"quantity":1},token,expected=201)
        api(f'/api/products/{product["id"]}',"PUT",{"price":"20.00"},admin)
        status,body,_,_=exchange("/api/orders","POST",token=token)
        assert status==409 and body["detail"]["code"]=="PRICE_CHANGED",(status,body)
        results["price_changed"]={"http_status":status,"code":body["detail"]["code"]}
        api(f'/api/cart/items/{product["id"]}',"PUT",{"quantity":1},token)
        for fields,code in (({"stock":0},"INSUFFICIENT_STOCK"),({"stock":100,"is_active":False},"PRODUCT_UNAVAILABLE")):
            api(f'/api/products/{product["id"]}',"PUT",fields,admin)
            status,body,_,_=exchange("/api/orders","POST",token=token)
            assert status==409 and body["detail"]["code"]==code,(status,body)
            results[code.lower()]={"http_status":status,"code":code}
        assert len(api("/api/orders",token=token))==1
        api(f'/api/products/{product["id"]}',"PUT",{"stock":100,"is_active":True},admin)
        rejected_order=api("/api/orders","POST",token=token,expected=201);orders.append(rejected_order)
        api(f'/api/products/{product["id"]}',"PUT",{"stock":0},admin)
        rejection=api("/api/payments","POST",{"order_id":rejected_order["id"],"method":"card"},token,expected=409)
        transaction=api("/api/payments/transactions/"+rejection["detail"]["transaction_id"],token=token)
        assert transaction["processed_at"] is not None
        results["rejected_processed_at"]=transaction["processed_at"]
        complete=True
    finally:
        if complete or not orders:
            cleanup(user,product,orders)
        else:
            print("Datos conservados para diagnostico:",marker)
    Path("docs/auditoria/cierre-hallazgos-resultados.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print("OK: hallazgos corregidos por HTTP: correo largo, limites bcrypt, 20 altas, checkout unico, revalidacion y fecha final.")
    return results


if __name__=="__main__":main()
