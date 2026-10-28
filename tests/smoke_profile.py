import json
import uuid

from smoke_purchase import request, service_code


marker = "profile-test-" + uuid.uuid4().hex
users = []
try:
    request(8001,"/users/me","PUT",{"name":"Changed"},expected=401)
    for suffix in ("first","other"):
        users.append(request(8001,"/auth/register","POST",{
            "name":marker+suffix,"email":marker+suffix+"@example.com","password":"Profile-Test-2026",
        },expected=201))
    token = request(8001,"/auth/login","POST",{"email":users[0]["email"],"password":"Profile-Test-2026"})["access_token"]
    request(8001,"/users/me","PUT",{"role":"admin"},token,expected=422)
    request(8001,"/users/me","PUT",{"id":users[1]["id"],"name":"Changed"},token,expected=422)
    request(8001,"/users/me","PUT",{"email":users[1]["email"].upper()},token,expected=409)
    request(8001,"/users/me","PUT",{"name":None},token,expected=422)
    new_email = marker+"updated@example.com"
    profile = request(8001,"/users/me","PUT",{"name":"Updated profile","email":new_email},token)
    assert profile["email"] == new_email and profile["role"] == "Customer"
    assert "password_hash" not in profile
    refreshed = request(8001,"/users/me",token=profile["access_token"])
    assert refreshed["name"] == "Updated profile" and refreshed["id"] == users[0]["id"]
    request(8001,"/auth/login","POST",{"email":users[0]["email"],"password":"Profile-Test-2026"},expected=401)
    request(8001,"/auth/login","POST",{"email":new_email.upper(),"password":"Profile-Test-2026"})
    other_token = request(8001,"/auth/login","POST",{"email":users[1]["email"],"password":"Profile-Test-2026"})["access_token"]
    assert request(8001,"/users/me",token=other_token)["name"] == users[1]["name"]
    print("OK: perfil HTTP, autenticacion, validacion, duplicados, cuenta ajena protegida y login con correo nuevo.")
finally:
    for user in users:
        service_code("user-service", '''
import sys
from sqlalchemy import text
from app.database import engine
with engine.begin() as c:
    c.execute(text("DELETE FROM users WHERE id=:id AND email LIKE :marker"),
              {"id":int(sys.argv[1]),"marker":sys.argv[2]+"%"})
''',user["id"],marker)
