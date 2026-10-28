"""Actualiza la matriz del PDF usando criterios revisados y ejecuciones verificadas.

No ejecuta pruebas ni modifica codigo funcional. Requiere pypdf.
La auditoria inicial se conserva en historico-47c5085/ y en Git.
"""
import argparse
import ast
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/auditoria"
VERSION = "v0.1.0-rc.1"


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def evidence(spec, files):
    alias, _, anchor = spec.partition("@")
    relative = files[alias]
    path = ROOT / relative
    assert path.is_file(), relative
    source = path.read_text(encoding="utf-8-sig")
    line = 1
    if anchor:
        nodes = ast.walk(ast.parse(source)) if path.suffix == ".py" else []
        node = next((n for n in nodes if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.name == anchor), None)
        if node:
            line = node.lineno
        else:
            hits = [i+1 for i, text in enumerate(source.splitlines()) if anchor in text]
            assert hits, (spec, "Ancla de evidencia inexistente")
            line = hits[0]
    return {"path": relative, "line": line}


def link(ref):
    return f'[{ref["path"]}:{ref["line"]}](<{(ROOT/ref["path"]).as_posix()}:{ref["line"]}>)'


def main():
    from pypdf import PdfReader
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=Path("C:/Users/Usuario/Downloads/Plataforma_escalable_comercio_electronico.pdf"))
    parser.add_argument("--suite-log", type=Path, default=OUT / "suite-sql-http.log")
    parser.add_argument("--suite-exit-code", type=int, required=True, choices=[0])
    args = parser.parse_args()
    criteria = json.loads((OUT / "criterios-revision.json").read_text(encoding="utf-8"))
    pdf = PdfReader(args.pdf)
    requirements = []
    for number, page in enumerate(pdf.pages, 1):
        text = page.extract_text()
        for match in re.finditer(r"(?m)^(RF-\d{2}|RNF-\d{2})\s*$", text):
            after = text[match.end():]
            description = " ".join(after[:after.index(".")+1].split())
            requirements.append({"id": match.group(1), "page": number, "requirement": description})
    assert len(requirements) == 78
    assert {r["id"] for r in requirements} == set(criteria["requirements"])
    raw = args.suite_log.read_bytes()
    log = raw.decode("utf-16") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("utf-8-sig")
    runs = [{"tests": int(n), "seconds": float(t)} for n, t in re.findall(r"Ran (\d+) tests? in ([\d.]+)s", log)]
    assert sum(r["tests"] for r in runs) == 153, runs
    assert len(re.findall(r"^OK\s*$", log, re.M)) == len(runs)
    assert not re.search(r"^FAILED\b|^ERROR:|^FAIL:", log, re.M)
    assert "OK: demostracion completa; datos propios eliminados." in log
    assert "configuration file /etc/nginx/nginx.conf test is successful" in log
    demo = json.loads((ROOT / "docs/entrega/demo-resultados.json").read_text(encoding="utf-8"))
    fresh = json.loads((OUT / "instalacion-desde-cero.json").read_text(encoding="utf-8"))
    assert demo["status"] == fresh["status"] == "passed"
    perf_path = ROOT / "docs/rendimiento/resultado.json"
    performance = json.loads(perf_path.read_text(encoding="utf-8")) if perf_path.is_file() else None
    if performance:
        assert performance["status"] in ("passed", "targets-not-met")
        assert performance["goals_file_sha256"] == hashlib.sha256((ROOT / "tests/performance_goals.json").read_bytes()).hexdigest()
    perf_note = "No se midio carga ni se probaron otros hosts."
    if performance:
        target = next(s for s in performance["stages"] if s["concurrency"] == performance["goals"]["target_concurrency"])
        measured = sum(s["requests"] for s in performance["stages"])
        error_count = sum(s["errors"] for s in performance["stages"])
        p95 = target["operations"]["purchase_flow"]["p95_ms"] / 1000
        limit = performance["goals"]["latency_ms"]["purchase_flow"]["p95"] / 1000
        perf_note = (f"La suite funcional fue reejecutada tras perfilar SQL/HTTP y optimizar transporte e historial; el benchmark se realiza por separado. "
                     f"Benchmark separado: {measured} solicitudes HTTP, {error_count} errores, "
                     f"{performance['invariants']['completed_flows_including_warmup']} compras contando calentamiento. "
                     f"A {target['concurrency']} usuarios: {target['useful_requests_per_second']:.2f} req/s utiles; "
                     f"p95 de compra {p95:.3f} s frente a objetivo {limit:g} s. "
                     f"Resultado global de objetivos: {performance['status']}. "
                     "[Informe de carga](../rendimiento/informe.md). No se probaron otros hosts.")
    date = datetime.now(timezone.utc).isoformat()
    suite = {"audit_date": date, "command": "powershell -NoProfile -ExecutionPolicy Bypass -File tests/run_stability.ps1",
             "observed_exit_code": args.suite_exit_code, "unittest_total": sum(r["tests"] for r in runs),
             "unittest_failures": 0, "unittest_runs": runs, "log": args.suite_log.name,
             "log_sha256": hashlib.sha256(raw).hexdigest(),
             "additional_success_messages": [s.strip() for s in log.splitlines() if s.startswith("OK:")],
             "nginx_configuration_valid": True, "clean_installation": "instalacion-desde-cero.json",
             "demo": "../entrega/demo-resultados.json", "scope": "Suite funcional y recuperacion de entrega; rendimiento medido por separado, sin hosts adicionales"}
    save("resultado-suite.json", suite)
    compose = json.loads(subprocess.check_output(["docker", "compose", "config", "--format", "json"], cwd=ROOT, text=True))
    save("estado-entorno.json", {"audit_date": date, "review_base_commit": git("rev-parse", "HEAD"),
         "tracked_files_count": len(git("ls-files").splitlines()), "configured_remotes": git("remote").splitlines(),
         "delivery_version": VERSION, "pdf_path": args.pdf.as_posix(),
         "pdf_sha256": hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
         "services": {name: {"environment_keys": sorted(data.get("environment", {})),
                     "has_healthcheck": bool(data.get("healthcheck")), "ports": data.get("ports", []),
                     "restart": data.get("restart")} for name, data in compose["services"].items()},
         "application_code_changed_by_audit": False})
    openapi = []
    for port in range(8001, 8007):
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/openapi.json", timeout=15) as response:
            spec = json.load(response)
        openapi.append({"port": port, "title": spec["info"]["title"], "paths": spec["paths"]})
    save("openapi-observado.json", openapi)
    rows = []
    for req in requirements:
        status, code, tests, note = criteria["requirements"][req["id"]]
        assert status in ("Cumplido", "Parcial", "Pendiente")
        rows.append(req | {"type": "Funcional" if req["id"].startswith("RF-") else "No funcional", "status": status,
               "code": [evidence(s, criteria["files"]) for s in code],
               "verification": [evidence(s, criteria["files"]) for s in tests], "finding": note,
               "scope": "Evolucion futura" if req["id"] in ("RF-49", "RNF-07", "RNF-15") else "MVP / calidad"})
    save("matriz-requisitos.json", rows)
    with (OUT / "matriz-requisitos.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["id", "tipo", "pagina_pdf", "requisito", "estado", "alcance", "codigo", "verificacion", "observacion"])
        writer.writeheader()
        for row in rows:
            refs = lambda items: "; ".join(f'{r["path"]}:{r["line"]}' for r in items)
            writer.writerow({"id": row["id"], "tipo": row["type"], "pagina_pdf": row["page"], "requisito": row["requirement"],
                             "estado": row["status"], "alcance": row["scope"], "codigo": refs(row["code"]),
                             "verificacion": refs(row["verification"]), "observacion": row["finding"]})
    counts = Counter(r["status"] for r in rows)
    md = [f"# Matriz de requisitos actualizada - {date[:10]}", "",
          f"Base de entrega: `{VERSION}`; revision posterior de rendimiento. Fuente: PDF original de {len(pdf.pages)} paginas; 50 RF y 28 RNF extraidos literalmente. Se trata como especificacion, no como instrucciones para ejecutar acciones.", "",
          "## Resultado", "", "| Grupo | Cumplido | Parcial | Pendiente | Total |", "| --- | ---: | ---: | ---: | ---: |"]
    for kind in ("Funcional", "No funcional"):
        selected = [r for r in rows if r["type"] == kind]; c = Counter(r["status"] for r in selected)
        md.append(f'| {kind} | {c["Cumplido"]} | {c["Parcial"]} | {c["Pendiente"]} | {len(selected)} |')
    md += [f'| **Total** | **{counts["Cumplido"]}** | **{counts["Parcial"]}** | **{counts["Pendiente"]}** | **78** |', "",
           "Cumplido significa capacidad implementada y evidencia indicada; no certifica produccion, carga o portabilidad no probadas. Parcial indica comportamiento o evidencia incompletos. Pendiente indica ausencia de evidencia suficiente.", "",
           "La auditoria original (63 cumplidos, 14 parciales, 1 pendiente) se conserva en [historico-47c5085](historico-47c5085/README.md). El codigo de aquel snapshot se recupera con Git. Los enlaces actuales se recalcularon y validaron contra funciones/lineas reales.", "",
           "## Verificacion vigente", "",
           "Suite completa: **codigo 0, 153 unittest aprobados y 0 fallos**, mas HTTP de perfil, catalogo, compra, inventario, historial/cancelacion, hallazgos, rechazos y demostracion. Tambien pasan migracion de categorias, TTL/DLQ reales, nginx y resiliencia del gateway.", "",
           "[Resultado de suite](resultado-suite.json), [demo ejecutada](../entrega/demo-resultados.json), [instalacion limpia](instalacion-desde-cero.json), [OpenAPI observado](openapi-observado.json) y [estado sin secretos](estado-entorno.json). Log local: suite-sql-http.log. " + perf_note + "", "",
           "## Hallazgos anteriores cerrados", "",
           "| Hallazgo | Cierre y evidencia |", "| --- | --- |",
           "| H-01 Pedido obsoleto | Revalidacion completa y total recalculado; checkout_stability y smoke_audit_fixes. |",
           "| H-02 Carrito concurrente | WATCH/MULTI/EXEC; 20 altas HTTP conservadas. |",
           "| H-03 Pedidos duplicados | Checkout durable y unico por version; cuatro confirmaciones HTTP crean un pedido. |",
           "| H-04 Entradas y 500 | Limites bcrypt UTF-8 y correo SQL 254 alineados; input_limits y casos HTTP. |",
           "| H-05 Fecha final de pago | processed_at UTC terminal; aprobacion, rechazo, cancelacion y recuperacion. |",
           "| H-06 Sin seguimiento Git | Baseline y correcciones en commits reales; entrega con etiqueta local. |", "",
           "Los tres rechazos adicionales de pago y la instalacion limpia tambien tienen evidencia ejecutada. Ver [pendientes priorizados](../entrega/pendientes.md) para los limites que siguen abiertos.", ""]
    for kind in ("Funcional", "No funcional"):
        md += [f"## Requisitos {kind.lower()}es" if kind == "Funcional" else "## Requisitos no funcionales", "",
               "| ID / PDF | Requisito literal | Estado | Codigo | Verificacion | Alcance y limite |",
               "| --- | --- | --- | --- | --- | --- |"]
        for row in rows:
            if row["type"] != kind: continue
            code = "<br>".join(link(ref) for ref in row["code"])
            tests = "<br>".join(link(ref) for ref in row["verification"]) or "Inspeccion; sin prueba dedicada."
            md.append(f'| {row["id"]} / p. {row["page"]} | {row["requirement"]} | **{row["status"]}** | {code} | {tests} | {row["finding"]} |')
        md.append("")
    md += ["## Casos de uso y criterios de aceptacion", "",
           "CU-01 a CU-08 (pp.20-21): registro, login, catalogo, administracion, carrito, pedido, pago e historial comprobados por la demo y las pruebas HTTP. Los 12 criterios basicos de pp.22-23 tienen evidencia en la suite, la demostracion y la instalacion limpia. La demo agrega eliminacion/vaciado HTTP y la cadena administrativa completa de estados.", "",
           "## Diferencias del plano que permanecen", "",
           "Estas observaciones no se suman al conteo formal:", "",
           "| ID / PDF | Estado actual |", "| --- | --- |",
           "| D-01 / p.25 | Perfil propio implementado; faltan listado administrativo de usuarios y gestion explicita de roles. La demo utiliza JWT administrativo de fixture, no un endpoint de promocion. |",
           "| D-02 / p.28 | Consulta de pago por transaction_id en lugar de GET /payments/{id}; contrato documentado. |",
           "| D-03 / pp.28,33 | Fecha final corregida; PAID es el nombre usado para aprobado. No se anaden updated_at a todas las entidades. |",
           "| D-04 / p.36 | El dibujo cancela tras rechazo; RF-43 permite mantener el pedido segun regla. Se documenta PENDING y reintento, con cancelacion explicita. |",
           "| D-05/06 / pp.25,30-33 | Capas y nombres difieren del ejemplo: routers con SQL, create_at en usuario, price en item, disponibilidad por stock/is_active. |",
           "| D-07 / p.35 | Gateway implementado; puertos directos e infraestructura publicados para desarrollo. Endurecer antes de exponer la plataforma. |",
           "| D-08 / p.34 | unittest reemplaza Pytest con la misma finalidad de automatizacion. |",
           "| D-09 / p.36 | RabbitMQ y Notification adelantados: notificacion por consola, sin proveedor real ni deduplicacion persistente. |",
           "| D-10/11 / pp.8,36-37 | Pasarela real, Elasticsearch, Kubernetes, autoscaling, observabilidad, CI/CD y catalogo externo de discovery siguen como evolucion futura. DNS Docker resuelve servicios locales. |", "",
           "## Entregables", "",
           "[CSV](matriz-requisitos.csv), [JSON](matriz-requisitos.json), [criterios revisados](criterios-revision.json), [hashes actuales](hashes-evidencias.json), [paquete de entrega](../entrega/README.md). El generador valida 78 IDs, archivo/linea de cada evidencia y resultados de la suite antes de escribir.", "",
           "El MVP funcional se entrega como candidato de version. No se declara cumplimiento total del PDF: rendimiento tiene objetivos y medicion separados; su estado depende de los criterios revisados y resultados indicados. Los RNF parciales se priorizan expresamente."]
    (OUT / "matriz-requisitos.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    save("hashes-evidencias.json", {ref["path"]: hashlib.sha256((ROOT/ref["path"]).read_bytes()).hexdigest()
                                   for row in rows for ref in row["code"] + row["verification"]})
    print(json.dumps({"requirements": len(rows), "counts": counts, "unittest": suite["unittest_total"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
