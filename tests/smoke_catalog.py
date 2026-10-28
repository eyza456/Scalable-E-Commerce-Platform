import json
import uuid
from urllib.parse import urlencode

from smoke_purchase import request, service_code


def main():
    marker = "catalog-test-" + uuid.uuid4().hex
    tokens = json.loads(service_code("payment-service", '''
import json
from datetime import datetime,timedelta,timezone
from jose import jwt
from app.core.config import settings
def token(role):
    return jwt.encode({"sub":"42","role":role,"email":"test@example.com",
        "exp":datetime.now(timezone.utc)+timedelta(minutes=3)},settings.SECRET_KEY,algorithm=settings.JWT_ALGORITHM)
print(json.dumps({r:token(r) for r in ("admin","Customer","seller")}))
'''))
    category = product = None
    try:
        request(8002, "/categories", "POST", {"name":marker}, expected=401)
        for role in ("Customer", "seller"):
            request(8002, "/categories", "POST", {"name":marker}, tokens[role], expected=403)
        category = request(8002, "/categories", "POST", {"name":marker}, tokens["admin"], expected=201)
        request(8002, "/categories", "POST", {"name":marker.upper()}, tokens["admin"], expected=409)
        assert request(8002, f'/categories/{category["id"]}')["name"] == marker
        product = request(8002, "/products/", "POST", {
            "name":marker+" Laptop", "price":"10.00", "stock":2, "category_id":category["id"],
        }, tokens["seller"], expected=201)
        query = urlencode({"name":marker.upper(), "category_id":category["id"], "available":"true", "limit":1})
        rows = request(8002, "/products/?"+query)
        assert [p["id"] for p in rows] == [product["id"]]
        request(8002, "/products/?skip=-1", expected=422)
        request(8002, "/products/?limit=101", expected=422)
        request(8002, "/products/?category_id=0", expected=422)
        request(8002, f'/categories/{category["id"]}', "DELETE", token=tokens["admin"], expected=409)
        request(8002, f'/categories/{category["id"]}', "PUT", {"name":marker+" renamed"}, tokens["admin"])
        assert request(8002, f'/products/{product["id"]}')["category"] == marker+" renamed"
        request(8002, f'/products/{product["id"]}', "PUT", {"stock":0}, tokens["seller"])
        assert request(8002, "/products/?"+query) == []
        unavailable = urlencode({"category_id":category["id"], "available":"false"})
        assert request(8002, "/products/?"+unavailable)[0]["id"] == product["id"]
        request(8002, f'/products/{product["id"]}', "PUT", {"category_id":None}, tokens["seller"])
        request(8002, f'/categories/{category["id"]}', "DELETE", token=tokens["admin"], expected=204)
        request(8002, f'/categories/{category["id"]}', expected=404)
        category = None
        print("OK: catalogo HTTP, permisos admin/seller/cliente, categorias, filtros, paginacion y eliminacion protegida.")
    finally:
        if product:
            request(8002, f'/products/{product["id"]}', "DELETE", token=tokens["admin"], expected=204)
        if category:
            request(8002, f'/categories/{category["id"]}', "DELETE", token=tokens["admin"], expected=204)


if __name__ == "__main__":
    main()
