"""Resume diagnostico SQL/HTTP; no interpreta sus tiempos como aceptacion de carga."""
import hashlib
import json
from pathlib import Path
import statistics

from performance_metrics import percentile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/perfilado"
TARGETS = [("order-service", "GET", "/orders"), ("order-service", "POST", "/orders"),
           ("payment-service", "POST", "/payments")]
FIELDS = ["total_ms", "db_connect_ms", "db_execute_ms", "orm_all_ms", "db_held_ms",
          "http_client_init_ms", "http_send_ms", "serialize_ms"]


def main():
    runs, data, summary = {}, {}, {}
    for label in ("antes", "despues"):
        runs[label] = json.loads((OUT / f"{label}.json").read_text(encoding="utf-8"))
        assert runs[label]["status"] == "profile-recorded" and runs[label]["invariants"]["passed"]
        data[label] = [json.loads(line) for line in (OUT / f"{label}-requests.jsonl").read_text().splitlines()]
        summary[label] = {}
        for service, method, path in TARGETS:
            records = [r for r in data[label] if (r["service"], r["method"], r["path"]) == (service, method, path)]
            assert records
            summary[label][method + " " + path] = {"service": service, "samples": len(records),
                "fields": {name: {"mean_ms": statistics.mean(r[name] for r in records),
                                  "p50_ms": percentile([r[name] for r in records], 50),
                                  "p95_ms": percentile([r[name] for r in records], 95)} for name in FIELDS},
                "sql_statements_mean": statistics.mean(len(r["sql"]) for r in records),
                "http_calls_mean": statistics.mean(r["http_calls"] for r in records)}
    assert runs["antes"]["instrument_sha256"] == runs["despues"]["instrument_sha256"]
    assert runs["antes"]["goals"] == runs["despues"]["goals"]
    assert runs["antes"]["dataset"] == runs["despues"]["dataset"]
    lines = ["# Perfilado de historial, checkout y pago", "",
             "Diagnostico en proyectos Docker separados, con 20 usuarios, 100 productos, cinco segundos de calentamiento y 30 segundos de carga. El mismo instrumento fue inyectado en las copias de Order, Payment, Cart y Product; no forma parte de las aplicaciones desplegadas. Los datos agregados incluyen calentamiento y no se usan para aprobar RNF-01. La aceptacion se obtiene del [benchmark original sin instrumentacion](../rendimiento/informe.md).", "",
             "## Metodo y alcance de los contadores", "",
             "- total_ms: peticion ASGI completa, con dependencias y limpieza de sesion.",
             "- db_connect_ms: adquisicion del engine, incluyendo espera de pool y nueva conexion si corresponde; no separa ambos costes.",
             "- db_execute_ms: cursor SQL, incluyendo bloqueos y espera del driver; no incluye toda la materializacion ORM.",
             "- orm_all_ms: Query.all completo, incluyendo SQL, materializacion y carga de relaciones. Aplica al historial; checkout/pago usan otros metodos ORM.",
             "- db_held_ms: tiempo de prestamo de conexiones; puede incluir llamadas HTTP y serializacion mientras la sesion sigue abierta.",
             "- http_client_init_ms: construccion de Client HTTPX por llamada. En la mejora el transporte/TLS se construye una vez y se amortiza; ese primer coste sigue dentro de total_ms.",
             "- http_send_ms: envio HTTP, espera de transporte/red y servicio remoto, incluida lectura de la respuesta HTTPX; urllib mide hasta las cabeceras.",
             "- serialize_ms: validacion/conversion de respuesta de FastAPI, incluyendo esperas de programacion; no representa exclusivamente CPU ni todo el renderizado JSON. En el historial optimizado la validacion y el renderizado se hacen explicitamente en el worker; serialize_ms de FastAPI puede ser cero sin que se haya omitido validacion.", "",
             "Los contadores se solapan: no sumar columnas ni percentiles. Parte del tiempo restante incluye cola del threadpool, dependencias, ORM no cubierto y programacion del event loop. Las trazas enlazan llamadas mediante un ID sintetico; no guardan tokens, cuerpos ni parametros SQL. Solo se almacenan tabla y duracion de cada sentencia.", "",
             "## Comparacion diagnostica (p95 en ms)", "",
             "| Ruta | Contador | Antes | Despues |", "| --- | --- | ---: | ---: |"]
    for _, method, path in TARGETS:
        name = method + " " + path
        for field in FIELDS:
            if field == "orm_all_ms" and method != "GET":
                continue
            a, b = summary["antes"][name]["fields"][field]["p95_ms"], summary["despues"][name]["fields"][field]["p95_ms"]
            lines.append(f"| {name} | {field} | {a:.2f} | {b:.2f} |")
    lines += ["", "## Planes SQL en reposo", "",
              "Despues de drenar el trabajo se ejecuta EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) sobre historial del usuario con mas pedidos, historial filtrado PAID y seleccion de items de los ultimos 20 pedidos. No se ejecuta sobre datos reales del usuario. Son planes en reposo y cache caliente, no evidencia de ausencia de contencion durante carga.", "",
              "| Consulta | Ejecucion antes (ms) | Ejecucion despues (ms) | Plan antes/despues |", "| --- | ---: | ---: | --- |"]
    plans = {label: json.loads((OUT / f"{label}-planes.json").read_text()) for label in runs}
    for name in plans["antes"]:
        a, b = plans["antes"][name][0], plans["despues"][name][0]
        lines.append(f"| {name} | {a['Execution Time']:.3f} | {b['Execution Time']:.3f} | {a['Plan']['Node Type']} / {b['Plan']['Node Type']} |")
    lines += ["", "## Decision y resultado", "",
              "Los planes del conjunto pequeno son baratos, mientras la construccion repetida de clientes HTTP tiene coste medible y mantiene conexiones SQL ocupadas durante el checkout. Se reutiliza el transporte HTTP en tres servicios; cada llamada conserva un cliente efimero para evitar mezclar cookies o encabezados de autenticacion. En el historial se valida el modelo publico en el worker, se copia su representacion JSON y se libera la conexion de lectura antes del renderizado; asi se evita otra ronda de validacion ORM en el event loop/threadpool. El esquema, filtros por usuario y orden/paginacion se mantienen. No se agregaron indices ni se ampliaron pools SQL para ocultar esperas. No se introdujeron reintentos de POST, cache de precios/stock ni omision de validaciones.", "",
              "El contador de construccion HTTP baja claramente, pero este diagnostico no demuestra por si solo una mejora global: tambien hay espera/ORM/serializacion y variacion de carga del equipo. Las latencias totales no se aprobaron a partir de esta corrida. El resultado vinculante del perfil local esta en el benchmark completo sin hooks.", "",
              f"Registros capturados: antes {len(data['antes'])}, despues {len(data['despues'])}. Compras integras: antes {runs['antes']['invariants']['completed_flows_including_warmup']}, despues {runs['despues']['invariants']['completed_flows_including_warmup']}. El volumen final no es identico porque el generador es cerrado y el numero de ciclos depende de las respuestas. No son mediciones de saturacion ni un SLA productivo.", "",
              "Se preserva un [fallo de arranque aislado](arranque-fallido.json): RabbitMQ no pudo leer su cookie antes de iniciar las aplicaciones. Se elimino ese proyecto y el siguiente arranque limpio completo el perfil. No se utilizo ese intento como muestra de rendimiento.", "",
              "## Reproducir", "",
              "```powershell\npython -X utf8 tests/profile_api.py --label antes\n# Aplicar el cambio que se desea comparar\npython -X utf8 tests/profile_api.py --label despues\npython -X utf8 tests/profile_report.py\n```", "",
              "Para reconstruir el antes exacto usar el codigo del source_commit registrado en antes.json; no volver a generar antes sobre el codigo optimizado. El instrumento se conserva en tests/profile_instrument.py y ambos resultados incluyen su hash. Los proyectos y volumenes temporales se eliminan. Logs locales antes.log/despues.log excluidos de Git.", "",
              "[Resumen JSON](resumen.json), [datos antes](antes-requests.jsonl), [datos despues](despues-requests.jsonl), [planes antes](antes-planes.json), [planes despues](despues-planes.json), [metadatos antes](antes.json), [metadatos despues](despues.json)."]
    (OUT / "informe.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files = ["tests/profile_api.py", "tests/profile_instrument.py", "tests/profile_report.py"] + [str((OUT / f"{label}{suffix}").relative_to(ROOT)) for label in runs for suffix in (".json", "-requests.jsonl", "-planes.json")]
    (OUT / "resumen.json").write_text(json.dumps({"same_instrument": True, "same_diagnostic_profile": True,
        "source_commits": {label: runs[label]["source_commit"] for label in runs}, "routes": summary,
        "hash_format": "SHA-256 UTF-8 con CRLF normalizado a LF",
        "sha256": {name: hashlib.sha256((ROOT/name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for name in files}}, indent=2), encoding="utf-8")
    print("Informe SQL/HTTP generado; diagnostico separado de la aceptacion.")


if __name__ == "__main__":
    main()
