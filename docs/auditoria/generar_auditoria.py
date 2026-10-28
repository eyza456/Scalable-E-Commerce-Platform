"""Genera la matriz a partir del PDF original y verifica todos los enlaces al codigo.

Ejecutar con el Python del runtime de documentos (requiere pypdf).
No modifica el codigo funcional ni ejecuta la suite: consume su log ya terminado.
"""
import ast
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/auditoria"
PDF = Path("C:/Users/Usuario/Downloads/Plataforma_escalable_comercio_electronico.pdf")
DATE = "2026-10-28"

FILES = {
    "auth":"services/user-service/app/routers/auth.py",
    "users":"services/user-service/app/routers/users.py",
    "usecurity":"services/user-service/app/core/security.py",
    "uauth":"services/user-service/app/dependencies/auth.py",
    "umodel":"services/user-service/app/models/user.py",
    "uschema":"services/user-service/app/schemas/user.py",
    "product":"services/product-service/app/crud/product.py",
    "products":"services/product-service/app/routers/products.py",
    "pmodel":"services/product-service/app/models/product.py",
    "categories":"services/product-service/app/routers/categories.py",
    "psecurity":"services/product-service/app/core/security.py",
    "cart":"services/cart-service/app/routers/cart.py",
    "redis":"services/cart-service/app/redis_client.py",
    "orders":"services/order-service/app/routers/orders.py",
    "omodel":"services/order-service/app/models.py",
    "ocancel":"services/order-service/app/cancellations.py",
    "orabbit":"services/order-service/app/rabbitmq.py",
    "osecurity":"services/order-service/app/core/security.py",
    "payments":"services/payment-service/app/routers/payments.py",
    "payment_model":"services/payment-service/app/models/payment.py",
    "inventory":"services/payment-service/app/inventory.py",
    "outbox":"services/payment-service/app/outbox.py",
    "reservations":"services/product-service/app/reservations.py",
    "validation":"services/product-service/app/services/payment_validation.py",
    "msg":"services/order-service/app/messaging.py",
    "compose":"docker-compose.yml",
    "gw":"gateway/nginx.conf",
    "proxy":"gateway/proxy.inc",
    "gwdocker":"gateway/Dockerfile",
    "config":"services/payment-service/app/core/config.py",
    "pmain":"services/payment-service/app/main.py",
    "nmain":"services/notification-service/app/main.py",
    "runner":"tests/run_stability.ps1",
    "catalogtest":"tests/catalog_stability.py",
    "profiletest":"tests/profile_stability.py",
    "usertest":"tests/user_stability.py",
    "ordertest":"tests/order_stability.py",
    "paytest":"tests/payment_stability.py",
    "stocktest":"tests/product_stability.py",
    "gatewaytest":"tests/gateway_stability.py",
    "resilience":"tests/gateway_resilience.py",
    "purchase":"tests/smoke_purchase.py",
    "httpinventory":"tests/smoke_inventory.py",
    "httporders":"tests/smoke_orders.py",
    "httpprofile":"tests/smoke_profile.py",
    "httpcatalog":"tests/smoke_catalog.py",
    "probes":"tests/audit_probes.py",
    "git":"docs/auditoria/estado-entorno.json",
}


def evidence(spec):
    alias, _, anchor = spec.partition("@")
    path = ROOT / FILES[alias]
    assert path.is_file(), path
    source = path.read_text(encoding="utf-8-sig")
    line = 1
    if anchor:
        nodes = ast.walk(ast.parse(source)) if path.suffix == ".py" else []
        node = next((n for n in nodes if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == anchor), None)
        if node:
            line = node.lineno
        else:
            hits = [i+1 for i,s in enumerate(source.splitlines()) if anchor in s]
            assert hits, (spec, "ancla inexistente")
            line = hits[0]
    return {"path": FILES[alias], "line":line}


def link(ref):
    label = f'{ref["path"]}:{ref["line"]}'
    return f'[{label}](<{(ROOT/ref["path"]).as_posix()}:{ref["line"]}>)'


def run(command):
    p = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {"command":command,"exit_code":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}


# Solo conservar configuracion no sensible del entorno, nunca valores de secretos.
compose = json.loads(subprocess.run(["docker","compose","config","--format","json"],cwd=ROOT,capture_output=True,text=True,check=True).stdout)
environment = {
    "audit_date":DATE,
    "git_head":run(["git","rev-parse","--verify","HEAD"]),
    "git_tracked_files":run(["git","ls-files"]),
    "docker_status":run(["docker","compose","ps","--format","{{.Service}} {{.State}} {{.Health}}"]),
    "services":{name:{k: data.get(k) for k in ("image","container_name","ports","restart","volumes")}
                | {"environment_keys":sorted(data.get("environment",{})),"has_healthcheck":bool(data.get("healthcheck"))}
                for name,data in compose["services"].items()},
    "pdf_path":PDF.as_posix(),
    "pdf_sha256":hashlib.sha256(PDF.read_bytes()).hexdigest(),
    "application_code_changed_by_audit":False,
}
(OUT/"estado-entorno.json").write_text(json.dumps(environment,ensure_ascii=False,indent=2),encoding="utf-8")

log_path = OUT / f"suite-completa-{DATE}.log"
raw = log_path.read_bytes()
log = raw.decode("utf-16") if raw.startswith((b"\xff\xfe",b"\xfe\xff")) else raw.decode("utf-8-sig")
log = re.sub(r"\x1b\[[0-9;]*m", "", log)
log_path.write_text(log,encoding="utf-8")
runs = [{"tests":int(n),"seconds":float(s)} for n,s in re.findall(r"Ran (\d+) tests? in ([\d.]+)s",log)]
assert sum(r["tests"] for r in runs)==89, runs
assert len(re.findall(r"^OK\s*$",log,re.M))==len(runs)
assert not re.search(r"^FAILED\b|^ERROR:\s|^FAIL:\s",log,re.M)
suite = {"audit_date":DATE,"command":"powershell -NoProfile -ExecutionPolicy Bypass -File tests/run_stability.ps1",
         "observed_exit_code":0,"unittest_total":89,"unittest_failures":0,"unittest_runs":runs,
         "additional_success_messages":[s.strip() for s in log.splitlines() if s.startswith("OK:")],
         "nginx_configuration_valid":"configuration file /etc/nginx/nginx.conf test is successful" in log,
         "scope":"Runner canonico completo; no es una prueba de carga ni una instalacion desde cero",
         "legacy_excluded":{"file":"services/product-service/test_concurrency_53.py",
                            "reason":"Script manual con IDs fijos 9001/9005, transaccion fija y multiprocessing fork; sus invariantes tienen pruebas automatizadas aisladas en product_stability.py"}}
(OUT/"resultado-suite.json").write_text(json.dumps(suite,ensure_ascii=False,indent=2),encoding="utf-8")

requirements = []
reader = PdfReader(PDF)
for page_no, page in enumerate(reader.pages,1):
    text = page.extract_text()
    for m in re.finditer(r"(?m)^(RF-\d{2}|RNF-\d{2})\s*$",text):
        after = text[m.end():]
        end = after.index(".")+1
        description = " ".join(after[:end].split())
        assert not re.search(r"\b(?:RF|RNF)-\d",description), (m.group(1),description)
        requirements.append({"id":m.group(1),"page":page_no,"requirement":description})
assert len(requirements)==78 and len({r["id"] for r in requirements})==78
assert {r["id"] for r in requirements}=={f"RF-{i:02}" for i in range(1,51)}|{f"RNF-{i:02}" for i in range(1,29)}

# estado, codigo, verificacion y alcance/pendiente. C no implica aptitud productiva.
C,P,N = "Cumplido","Parcial","Pendiente"
RF = {
1:(C,["auth@register"],["purchase"],"Registro implementado y ejercitado por HTTP; limites extremos se auditan en RNF-12."),
2:(C,["auth@register","umodel@__table_args__"],["profiletest@test_concurrent_email_claims_only_allow_one_account","httpprofile"],"Duplicados controlados; indice unico lower(email) tambien protege concurrencia."),
3:(C,["auth@login"],["httpprofile","purchase"],"Login real con credenciales y con el nuevo correo tras actualizar perfil."),
4:(C,["usecurity@create_access_token","auth@login"],["profiletest@test_email_update_renews_token"],"JWT firmado y con expiracion."),
5:(C,["uauth@get_current_user","psecurity@get_current_user"],["gatewaytest@test_protected_routes_keep_backend_authentication"],"Rutas protegidas exigen JWT; no se afirma revocacion centralizada de tokens."),
6:(C,["users@get_me"],["usertest@test_profile_route_returns_profile_and_uses_normal_authentication","httpprofile"],"Consulta de la propia cuenta."),
7:(C,["users@update_me"],["profiletest","httpprofile"],"Actualizacion parcial de nombre/correo; se rechazan campos privilegiados y se renueva JWT."),
8:(C,["umodel@role = Column","psecurity@require_roles"],["httpcatalog"],"Roles Customer, admin y seller; falta un endpoint de asignacion de roles del diseno, ver D-01."),
9:(C,["psecurity@require_roles","osecurity@require_admin"],["httpcatalog","httpprofile"],"Permisos por rol en operaciones administrativas."),
10:(C,["usecurity@hash_password","umodel@password_hash"],["purchase"],"bcrypt y persistencia del hash; la validacion de longitud de contrasena es incompleta, ver H-04."),
11:(C,["products@create_new_product","product@create_product"],["gatewaytest@test_profile_catalog_cart_purchase_history_and_cancel_through_gateway"],"Alta con permisos y categoria existente."),
12:(C,["products@read_products","product@get_products"],["catalogtest@test_unavailable_includes_inactive_and_out_of_stock"],"El filtro available=true permite listar disponibles; el listado sin filtro tambien incluye inactivos."),
13:(C,["products@read_product"],["purchase"],"Detalle publico por ID y 404 cuando no existe."),
14:(C,["products@update_existing_product","product@update_product"],["httpcatalog"],"Actualizacion con permisos y validacion de categoria."),
15:(C,["product@delete_product"],["httpcatalog"],"Eliminacion autorizada; se impide borrar productos con reservas pendientes."),
16:(C,["categories","pmodel@category_id"],["catalogtest@test_category_assignment_and_legacy_name"],"Categorias relacionadas por FK; compatibilidad con nombre antiguo y migracion de datos."),
17:(C,["product@get_products"],["catalogtest@test_search_treats_percent_and_underscore_as_literal"],"Busqueda parcial por nombre y filtros combinables; no es busqueda avanzada Elasticsearch."),
18:(C,["reservations@reserve","products@decrease_product_stock"],["stocktest@test_competing_orders_cannot_reserve_same_units"],"Stock disponible y reservas atomicas; descuento idempotente y liberacion coordinada."),
19:(C,["product@get_products","pmodel@is_active"],["catalogtest@test_unavailable_includes_inactive_and_out_of_stock"],"Disponibilidad expresada por stock/is_active y filtro available; no existe campo de respuesta available como en el ejemplo del PDF."),
20:(C,["products@create_new_product","psecurity@require_roles"],["httpcatalog"],"CRUD y descuento manual de stock protegidos por admin/seller."),
21:(C,["cart@add_item_to_cart","cart@get_cart"],["purchase"],"Carrito Redis separado por identificador del JWT."),
22:(C,["cart@add_item_to_cart"],["gatewaytest@test_profile_catalog_cart_purchase_history_and_cancel_through_gateway"],"Alta basica funcional; actualizaciones concurrentes pierden datos, registrado en RNF-02/H-02."),
23:(C,["cart@update_cart_item"],["gatewaytest@test_profile_catalog_cart_purchase_history_and_cancel_through_gateway"],"Actualizacion de cantidad con comprobacion de stock en ese momento."),
24:(C,["cart@delete_cart_item"],[],"Implementado por inspeccion. La suite canonica no tiene una asercion HTTP dedicada a eliminar un item; no se inventa esa cobertura."),
25:(C,["cart@clear_cart","orders@create_order"],["purchase"],"Vaciado por DELETE /cart; ejercitado por creacion de pedido. No se comprueba atomicidad entre ambos servicios."),
26:(C,["cart@get_cart"],["gatewaytest@test_profile_catalog_cart_purchase_history_and_cancel_through_gateway"],"Contenido y totales del propio carrito."),
27:(C,["cart@get_cart"],["purchase"],"Subtotal y total calculados con Decimal a partir del snapshot del carrito."),
28:(P,["cart@add_item_to_cart","orders@create_order","reservations@reserve"],["probes@stale_checkout"],"Se valida al agregar y antes de pagar, pero no al crear/confirmar el pedido. Se reprodujo HTTP 201 con stock 0 y producto inactivo; precio del carrito anterior."),
29:(C,["orders@create_order"],["purchase"],"Creacion desde items del carrito; duplicacion concurrente queda documentada en H-03/RNF-02."),
30:(C,["omodel@Order"],["ordertest"],"Clave primaria autogenerada por PostgreSQL; no equivale a idempotencia de checkout."),
31:(C,["omodel@created_at"],["ordertest"],"Fecha/hora de creacion almacenada en orders."),
32:(C,["orders@create_order","omodel@user_id"],["httporders"],"Asocia user_id del JWT emitido por registro/login; no hay FK entre bases independientes ni introspeccion de usuario en cada servicio."),
33:(C,["omodel@OrderItem","orders@create_order"],["ordertest@test_history_only_contains_owner_and_stable_order"],"Items, cantidades y snapshot del producto persistidos."),
34:(C,["cart@get_cart","orders@create_order"],["purchase"],"El sistema calcula el total en Cart y Order persiste cart.total. No recalcula precios actuales en checkout; H-01 separa esa limitacion del calculo basico."),
35:(C,["orders@list_orders"],["ordertest@test_history_only_contains_owner_and_stable_order","httporders"],"Historial privado, filtrado por estado y paginado con orden estable."),
36:(C,["orders@get_order"],["httporders"],"Detalle restringido al propietario."),
37:(C,["orders@update_order_status","ocancel@finish_cancellation"],["ordertest","httporders"],"PENDING, PAID, PROCESSING, SHIPPED, DELIVERED, CANCELLED y estado adicional recuperable CANCELLING."),
38:(C,["orders@update_order_status","osecurity@require_admin"],[],"Transiciones administrativas implementadas y protegidas. La suite no recorre por HTTP toda la cadena PROCESSING-SHIPPED-DELIVERED; cobertura a ampliar."),
39:(C,["payments@create_payment"],["paytest@test_payment_and_three_deliveries_commit_together"],"Intento durable asociado a pedido y propietario."),
40:(C,["inventory@settle_payment","payment_model@status = Column"],["paytest@test_insufficient_stock_rejects_without_paid_event"],"Registra PENDING, PAID, REJECTED o CANCELLED."),
41:(C,["inventory@settle_payment"],["httpinventory"],"PAID y REJECTED reales distinguidos; el rechazo actual es por stock. No hay simulacion adicional de rechazo bancario."),
42:(C,["inventory@settle_payment","outbox@dispatch_pending","orabbit@process_payment_completed"],["purchase","gatewaytest"],"Actualizacion eventual mediante Outbox/RabbitMQ; compra completa y recuperacion verificadas."),
43:(C,["inventory@settle_payment"],["httpinventory"],"El rechazo por stock conserva el pedido PENDING para reintentar, permitido por RF-43. Difiere del diagrama de la pagina 36 que muestra CANCELLED."),
44:(P,["payment_model@created_at","inventory@settle_payment"],["paytest@test_inventory_outage_leaves_recoverable_intent"],"Solo existe created_at del intento; al recuperarse minutos despues no se registra processed_at/updated_at de la resolucion. Falta fecha real del procesamiento final."),
45:(C,["payments@create_payment","inventory@settle_payment"],["purchase","httpinventory"],"Pago simulado sin pasarela real; stock decide aprobacion/rechazo."),
46:(C,["compose@api-gateway:","gw"],["gatewaytest"],"Entrada central http://localhost:8000. Acceso directo de depuracion sigue publicado; ver D-07."),
47:(C,["gw","proxy"],["gatewaytest@test_profile_catalog_cart_purchase_history_and_cancel_through_gateway"],"Enrutamiento efectivo a los cinco servicios funcionales y categorias."),
48:(C,["gw"],["gatewaytest@test_unknown_routes_do_not_reach_arbitrary_backends"],"Rutas /api/auth, users, products, categories, cart, orders y payments definidas."),
49:(P,["gw@resolver","proxy@proxy_pass"],["resilience"],"Base Nginx/DNS preparada y recuperacion por cambio de IP probada; no hay balanceo configurado ni prueba de varias replicas. Capacidad futura, no bloqueo del MVP inicial."),
50:(C,["gw","proxy"],["gatewaytest@test_internal_paths_are_not_public_even_with_key_header","resilience"],"Politicas centrales: bloqueo de rutas internas, retirada de clave interna, IP reenviada y trazabilidad. JWT sigue en servicios."),
}

RNF = {
1:(N,["runner"],[],"Pendiente de evidencia: no hay SLO, umbrales, prueba de carga ni medicion p95/p99. Las duraciones de unittest no demuestran rendimiento adecuado."),
2:(P,["cart@add_item_to_cart","orders@create_order","inventory@settle_payment"],["paytest@test_simultaneous_payments_only_create_one_payment","probes@cart_concurrency","probes@duplicate_checkout"],"Pagos/inventario concurrentes protegidos; Redis GET-SET pierde altas y el mismo carrito produce pedidos duplicados."),
3:(C,["redis","compose@redis:"],["purchase"],"Redis integrado permite ampliar cache. Hoy almacena carritos; no se afirma cache del catalogo ni mejoras de rendimiento medidas."),
4:(C,["umodel@__table_args__","pmodel@category_id","omodel@user_id"],["catalogtest"],"Indices PK, email normalizado, categorias y usuarios. No se hicieron EXPLAIN ni benchmark de consultas."),
5:(P,["compose@container_name: user-service","compose@ports:"],["paytest"],"Separacion por servicio presente, pero container_name y puertos host fijos impiden --scale directo de servicios. Falta despliegue de replicas verificado."),
6:(P,["compose@container_name: product-service","outbox@dispatch_pending"],["paytest","stocktest"],"Bloqueos/skip_locked ayudan a replicas; Compose impone nombre/puerto unicos y no se probo un despliegue multinstancia."),
7:(P,["compose","gwdocker"],[],"Base en contenedores y variables de entorno; no hay manifiestos ni verificacion Kubernetes. Preparacion futura, fuera del MVP inicial segun pagina 8."),
8:(P,["validation@verify_payment_and_order","orders@create_order","config"],["resilience"],"Bases independientes y contratos HTTP/eventos, pero consumidores validan contra otras APIs y checkout depende de Cart. Minimizar acoplamiento sigue parcial."),
9:(C,["auth@register","umodel@password_hash"],["profiletest@test_partial_name_update_keeps_email_password_and_role"],"Se persiste hash; no un campo de contrasena en claro."),
10:(C,["usecurity@hash_password","usecurity@verify_password"],["purchase"],"bcrypt funcional para longitudes soportadas. El desajuste de 72 bytes se clasifica en RNF-12, no como ausencia de hash."),
11:(C,["usecurity@create_access_token","uauth@get_current_user"],["gatewaytest@test_protected_routes_keep_backend_authentication"],"JWT firmado, expiracion y autenticacion ejercitadas por HTTP."),
12:(P,["uschema@UserCreate","usecurity@hash_password","umodel@email = Column"],["probes@registration_limits"],"Se reprodujeron 500 con contrasena ASCII de 80 bytes y correo valido de 160 caracteres. Validacion Pydantic no coincide con bcrypt/DB."),
13:(C,["psecurity@require_roles","osecurity@require_admin","users@update_me"],["httpcatalog","httpprofile"],"Roles protegen operaciones administrativas y perfil rechaza campos privilegiados."),
14:(C,["config","compose"],[],"Secretos se leen desde variables de entorno. No se copiaron valores sensibles a la auditoria; no constituye auditoria completa de gestion/rotacion de secretos."),
15:(P,["gw@listen 80;","compose@127.0.0.1:"],[],"Gateway HTTP preparado para configurarse; no hay certificado, listener HTTPS ni validacion TLS. Capacidad futura, no bloqueo MVP."),
16:(C,["compose","pmain"],["resilience","purchase"],"Procesos/imagenes separados y bases por servicio; las dependencias funcionales siguen siendo necesarias."),
17:(C,["gw","proxy"],["resilience"],"Backend ausente no detiene Nginx ni /health; recupera al backend. No demuestra continuidad de toda compra si falla una dependencia."),
18:(P,["msg@forward","ocancel@run_recovery","compose@rabbitmq:"],["probes@registration_limits","paytest","stocktest"],"Hay timeouts, reintentos, DLQ y recuperadores, pero quedan excepciones de entrada sin traducir y no hay persistencia nombrada de Redis/RabbitMQ en Compose."),
19:(C,["compose@restart: unless-stopped"],[],"Politica de reinicio configurada para servicios e infraestructura."),
20:(C,["gwdocker@HEALTHCHECK","pmain@health_check","nmain@health_check"],["purchase","resilience"],"Checks HTTP de vida presentes; no comprueban readiness de DB/Redis/consumidores. No se afirma salud integral."),
21:(P,["orders@create_order","cart@add_item_to_cart","pmain"],[],"Modulos por responsabilidad, pero logica de negocio/DB en routers, arranque en importacion y archivos .bak conviven con fuentes activas."),
22:(C,["compose","orders","payments","reservations"],["purchase"],"Usuarios, catalogo, carrito, pedidos, pagos y notificaciones separados; inventario pertenece a Product."),
23:(C,["pmain@FastAPI(","orders","gw"],["gatewaytest"],"OpenAPI accesible en los seis servicios y documentacion Markdown del gateway. No hay Swagger agregado en /api/docs, por diseno."),
24:(C,["runner"],["paytest","ordertest","gatewaytest"],"Suite automatizada ejecutada: 89 unittest y escenarios adicionales. Pytest era una tecnologia propuesta, no el mecanismo real."),
25:(P,["git"],[],"Repositorio Git inicializado, pero HEAD no existe y git ls-files esta vacio: no hay commits ni codigo bajo seguimiento."),
26:(C,["compose","gwdocker"],["purchase","resilience"],"Los seis microservicios y el gateway tienen imagen/contenedor; constatados en ejecucion."),
27:(P,["compose","runner"],["purchase"],"Verificado Windows con Docker Linux. Runner PowerShell y script legado fork no demuestran ejecucion en macOS/Linux; no se probo instalacion limpia."),
28:(C,["config","compose"],[],"URLs, DB y claves configuradas por entorno; defaults locales y limites del gateway permanecen en configuracion versionable."),
}

rows=[]
for r in requirements:
    functional = r["id"].startswith("RF-")
    number=int(r["id"].split("-")[1])
    status, code, verification, note=(RF if functional else RNF)[number]
    rows.append(r|{"type":"Funcional" if functional else "No funcional","status":status,
                   "code":[evidence(s) for s in code],"verification":[evidence(s) for s in verification],
                   "finding":note,"scope":"Futuro / no bloquea MVP" if r["id"] in ("RF-49","RNF-07","RNF-15") else "MVP / calidad"})

(OUT/"matriz-requisitos.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
with (OUT/"matriz-requisitos.csv").open("w",encoding="utf-8-sig",newline="") as f:
    writer=csv.DictWriter(f,fieldnames=["id","tipo","pagina_pdf","requisito","estado","alcance","codigo","verificacion","observacion"])
    writer.writeheader()
    for row in rows:
        fmt=lambda refs:"; ".join(f'{x["path"]}:{x["line"]}' for x in refs)
        writer.writerow({"id":row["id"],"tipo":row["type"],"pagina_pdf":row["page"],"requisito":row["requirement"],
                         "estado":row["status"],"alcance":row["scope"],"codigo":fmt(row["code"]),
                         "verificacion":fmt(row["verification"]),"observacion":row["finding"]})

counts=Counter(row["status"] for row in rows)
md=[f"# Auditoria de requisitos - {DATE}","",
    "Fuente: Plataforma_escalable_comercio_electronico.pdf, 37 paginas. Se revisaron los 50 RF y los 28 RNF completos, ademas de los casos de uso, criterios de aceptacion y diferencias del diseno. El PDF se trato como especificacion de referencia, no como instrucciones operativas.","",
    "## Resultado", "",
    "| Grupo | Cumplido | Parcial | Pendiente | Total |","| --- | ---: | ---: | ---: | ---: |"]
for kind in ("Funcional","No funcional"):
    selected=[r for r in rows if r["type"]==kind]; count=Counter(r["status"] for r in selected)
    md.append(f'| {kind} | {count[C]} | {count[P]} | {count[N]} | {len(selected)} |')
md += [f'| **Total** | **{counts[C]}** | **{counts[P]}** | **{counts[N]}** | **78** |',"",
    "Cumplido: capacidad presente con evidencia de codigo y, cuando existe, prueba ejecutada. No significa aptitud productiva ni cobertura exhaustiva. Parcial: falta parte del comportamiento o de su verificacion. Pendiente: no hay evidencia suficiente para afirmar la capacidad. Los RNF de rendimiento/portabilidad no se aprueban por inferencia.","",
    "Los objetivos futuros (balanceo, Kubernetes, HTTPS) se distinguen expresamente de los bloqueos del MVP. No desplegarlos ahora no contradice la exclusion de alcance de la pagina 8.","",
    "## Ejecucion completa", "",
    "Comando: `powershell -NoProfile -ExecutionPolicy Bypass -File tests/run_stability.ps1`.","",
    "Resultado observado: codigo de salida **0**; **89 pruebas unittest aprobadas, 0 fallos**. Tambien pasaron migracion/downgrade de categorias, dos comprobaciones RabbitMQ TTL/DLQ, cinco scripts HTTP (perfil, catalogo, compra, inventario, pedidos) y `nginx -t`. Las diez pruebas HTTP del gateway incluyen una compra completa; la prueba aislada confirma caida y cambio de IP del backend.","",
    "Evidencia: [log completo](suite-completa-2026-10-28.log), [resultado estructurado](resultado-suite.json), [OpenAPI observado](openapi-observado.json) y [estado del entorno sin secretos](estado-entorno.json).", "",
    "Se ejecuto el runner canonico completo. El script manual `services/product-service/test_concurrency_53.py` no se ejecuto sobre los datos reales: exige fixtures fijos 9001/9005 y fork. Sus invariantes ya tienen pruebas aisladas y concurrentes en la suite. `gateway_probe.py` es un servidor auxiliar, no un test independiente.","",
    "No se hicieron cambios funcionales para hacer pasar la suite. No se ejecuto una instalacion desde cero ni una prueba de carga. No se midieron SLO. El log contiene errores intencionales de escenarios negativos que terminaron en OK; no son fallos de la suite.","",
    "## Hallazgos reproducidos fuera de la cobertura existente", "",
    "La suite positiva pasa, pero no demuestra ausencia de defectos. Se agregaron sondas de auditoria separadas, sin incorporarlas como pruebas verdes al runner. [Resultados](sondas-2026-10-28.json), [codigo reproducible](../../tests/audit_probes.py).", "",
    "| Hallazgo | Resultado observado | Requisito relacionado | Accion pendiente |",
    "| --- | --- | --- | --- |",
    "| H-01: checkout desactualizado | HTTP 201 con producto inactivo, stock 0, precio actual 20 y precio del item 10; pedido total 20 por dos unidades antiguas. HTTP real via gateway. | RF-28 | Revalidar existencia, actividad, stock y politica de precios al crear el pedido. Reservar antes de pagar evita PAID sin stock, pero no corrige la creacion del pedido. |",
    "| H-02: altas concurrentes en carrito | Dos altas de una unidad dejan cantidad 1, no 2. Redis real; lecturas sincronizadas y Product simulado. | RNF-02 | Operacion atomica Redis con Lua/WATCH o estructura equivalente. |",
    "| H-03: checkout duplicado | Dos respuestas sincronizadas del mismo carrito crean dos pedidos diferentes en PostgreSQL aislado. | RNF-02 / fiabilidad | Consumo idempotente del carrito, identificador de checkout y coordinacion ante fallo al vaciar. Un PK unico no evita pedidos duplicados semanticamente. |",
    "| H-04: limites de entrada | Registro devuelve HTTP 500 para contrasena de 80 bytes y correo valido de 160 caracteres. Casos HTTP reales, sin cuentas residuales. | RNF-12 / RNF-18 | Alinear limites de bcrypt/DB y schemas; traducir errores en respuestas controladas. |",
    "| H-05: fecha del pago | Solo created_at del intento; no processed_at de su resolucion posterior. Evidencia estatica. | RF-44 | Registrar fecha de aprobacion/rechazo/cancelacion de la transaccion. |",
    "| H-06: Git | Sin HEAD, sin commits y git ls-files vacio. | RNF-25 | Revisar .gitignore/secretos y crear seguimiento real; la auditoria no hizo commits. |", "",
    "Prioridad de cierre: H-01/H-02/H-03/H-04; despues RF-44, versionado y mediciones. Los precios antiguos deben resolverse con una regla de negocio explicita, no cambiando silenciosamente el importe de una orden ya creada.","",
    "Otras limitaciones: Compose no declara volumenes nombrados para Redis/RabbitMQ; no se garantiza durabilidad al recrearlos. Los /health son principalmente liveness. No se probaron replicas reales, TLS ni otros sistemas operativos. La prueba de resiliencia del gateway no demuestra durabilidad del broker.","",
    "## Matriz de requisitos funcionales", "",
]
for kind in ("Funcional","No funcional"):
    if kind=="No funcional":md += ["## Matriz de requisitos no funcionales",""]
    md += ["| ID / pagina PDF | Requisito literal | Estado | Codigo | Verificacion | Alcance, limites y pendiente |",
           "| --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        if row["type"]!=kind:continue
        code="<br>".join(link(r) for r in row["code"])
        tests="<br>".join(link(r) for r in row["verification"]) or "Inspeccion; sin prueba dedicada en la suite."
        md.append(f'| {row["id"]} / p. {row["page"]} | {row["requirement"]} | **{row["status"]}** | {code} | {tests} | {row["finding"]} |')
    md.append("")

md += ["## Casos de uso y aceptacion", "",
    "Los siguientes estados se refieren al flujo basico, no cancelan los hallazgos negativos anteriores. Un criterio general puede cumplirse mientras un RF mas especifico queda parcial.","",
    "| Caso PDF | Estado | Evidencia y limite |","| --- | --- | --- |"]
cases=[("CU-01 Registro","purchase"),("CU-02 Login","httpprofile"),("CU-03 Consultar productos","catalogtest"),
       ("CU-04 Gestionar productos","httpcatalog"),("CU-05 Agregar al carrito","gatewaytest"),
       ("CU-06 Crear pedido","purchase"),("CU-07 Procesar pago","httpinventory"),("CU-08 Historial","httporders")]
for label,ref in cases:md.append(f'| {label} (pp. 20-21) | Cumplido, flujo basico | {link(evidence(ref))}; ver RF relacionados para limites. |')
md += ["", "| Criterio 2.7, pp. 22-23 | Estado | Evidencia |","| --- | --- | --- |"]
criteria=[("1 Registro/login","purchase"),("2 Hash seguro","usecurity@hash_password"),("3 Generar/validar JWT","gatewaytest"),
          ("4 Gestion de productos por administrador","httpcatalog"),("5 Consulta de disponibles","catalogtest"),
          ("6 Agregar/modificar/eliminar carrito","cart"),("7 Crear pedidos","purchase"),("8 Estado identificable","httporders"),
          ("9 Simulacion de pago","httpinventory"),("10 Contenedores independientes","compose"),
          ("11 Comunicacion por APIs","gatewaytest"),("12 Docker Compose","runner")]
for label,ref in criteria:
    note=" La eliminacion individual esta inspeccionada, sin asercion HTTP dedicada en la suite." if label.startswith("6 ") else ""
    md.append(f'| {label} | Cumplido, alcance basico | {link(evidence(ref))}.{note} |')

md += ["", "## Diferencias de diseno y ampliaciones", "",
    "Estas observaciones no se suman al conteo de los 78 requisitos formales.","",
    "| ID / PDF | Estado | Evidencia / diferencia |","| --- | --- | --- |",
    f'| D-01 / p. 25 | Parcial | {link(evidence("users"))}: existen GET/PUT /users/me, pero faltan GET /users y GET /users/{{id}} del diseno y administracion explicita de roles. |',
    f'| D-02 / p. 28 | Parcial | {link(evidence("payments@get_payment_by_transaction"))}: consulta por transaction_id, no GET /payments/{{id}} como en el plano. |',
    f'| D-03 / pp. 28, 33 | Parcial | {link(evidence("payment_model"))}: PAID sustituye APPROVED; no updated_at/processed_at. El campo created_at del intento no resuelve RF-44. |',
    '| D-04 / p. 36 | Parcial | El diagrama propone REJECTED -> CANCELLED. La regla actual conserva PENDING para reponer/reintentar, como permite RF-43. Requiere armonizar documento y decision de negocio. |',
    f'| D-05 / p. 25 | Parcial | {link(evidence("orders@create_order"))}: separacion router/service/repository no es uniforme; varios routers contienen negocio y SQL. |',
    f'| D-06 / pp. 30-33 | Parcial | {link(evidence("umodel"))}, {link(evidence("omodel"))}, {link(evidence("pmodel"))}: User usa create_at y no updated_at; Order no tiene updated_at; item usa price en vez de unit_price; disponibilidad se calcula con stock/is_active. Son diferencias respecto al modelo propuesto. |',
    f'| D-07 / p. 35 | Parcial | {link(evidence("compose"))}: el gateway existe, pero los puertos directos 8001-8006 e infraestructura siguen publicados. No se impone entrada exclusiva por gateway; entorno de desarrollo. |',
    f'| D-08 / p. 34 | Cumplido en finalidad | {link(evidence("runner"))}: automatizacion con unittest en lugar del Pytest propuesto. No se considera incumplimiento funcional por cambiar la herramienta. |',
    f'| D-09 / p. 36 | Parcial, futuro adelantado | {link(evidence("nmain"))}: Notification Service y RabbitMQ existen, pero notificaciones solo imprimen en consola, sin envio real ni deduplicacion persistente. |',
    '| D-10 / pp. 8, 36-37 | Pendiente, fuera de MVP | Pasarela real/reembolsos, inventario como servicio separado, Elasticsearch, Kubernetes, autoscaling, monitoreo Prometheus/Grafana, logs centralizados y CI/CD no estan implementados. No se exigen para declarar el alcance inicial. |',
    '| D-11 / p. 36 | Parcial, futuro | DNS Docker resuelve nombres de servicios; no se incorporo un catalogo independiente de Service Discovery. |',
    '', '## Entregables y reproducibilidad','',
    '- [Matriz CSV](matriz-requisitos.csv), [matriz JSON](matriz-requisitos.json).',
    '- [Resultado de la suite](resultado-suite.json) y [log](suite-completa-2026-10-28.log).',
    '- [Sondas negativas](sondas-2026-10-28.json), reproducibles con `python -X utf8 tests/audit_probes.py`.',
    '- [Generador de este informe](generar_auditoria.py); requiere pypdf. Extrae los 78 textos del PDF y valida archivos/lineas de evidencia antes de escribir.',
    '- [Snapshot de codigo](hashes-evidencias.json) y hash del PDF en estado-entorno.json. Los enlaces son a lineas verificadas del checkout auditado; cambios posteriores pueden desplazarlas.',
    '', 'Conclusion: los flujos principales estan implementados y la suite canonica pasa, pero el cumplimiento no es completo. Antes de cerrar el MVP deben resolverse los defectos reproducidos de checkout/concurrencia/validacion y RF-44; el estado futuro/productivo requiere evidencia adicional.',
]
(OUT/"matriz-requisitos.md").write_text("\n".join(md)+"\n",encoding="utf-8")
hashes={r["path"]:hashlib.sha256((ROOT/r["path"]).read_bytes()).hexdigest()
        for row in rows for r in row["code"]+row["verification"]}
(OUT/"hashes-evidencias.json").write_text(json.dumps(hashes,indent=2,ensure_ascii=False),encoding="utf-8")
print(json.dumps({"formal_requirements":len(rows),"status_counts":counts,"unittest_passed":89},ensure_ascii=False))
