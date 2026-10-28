"""Publica evidencia y comparacion sin modificar objetivos ni muestras del benchmark."""
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/rendimiento"
BASE = OUT / "baseline-9b6eeb3"


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main():
    result = json.loads((OUT / "resultado.json").read_text(encoding="utf-8"))
    baseline = json.loads((BASE / "resultado.json").read_text(encoding="utf-8"))
    assert result["status"] in ("passed", "targets-not-met")
    assert result["mode"] == baseline["mode"] == "acceptance-local"
    assert result["source_commit"] != baseline["source_commit"], "El resultado aun corresponde a la linea base"
    for name in ("services/payment-service/app/outbox.py", "services/payment-service/app/core/rabbitmq.py"):
        measured_source = subprocess.check_output(["git", "show", result["source_commit"] + ":" + name], cwd=ROOT)
        assert digest(ROOT / name) == hashlib.sha256(measured_source.replace(b"\r\n", b"\n")).hexdigest(), "Cambio el codigo medido: " + name
    assert result["goals"] == baseline["goals"], "Los objetivos/perfil han cambiado"
    assert result["dataset"] == baseline["dataset"], "Cambio el conjunto de datos inicial"
    assert result["goals_file_sha256"] == baseline["goals_file_sha256"]
    assert result["goals_file_sha256"] == hashlib.sha256((ROOT / "tests/performance_goals.json").read_bytes()).hexdigest()
    old_hashes = json.loads((BASE / "evidencias.json").read_text(encoding="utf-8"))["sha256"]
    for name in ("tests/performance_load.py", "tests/performance_metrics.py", "tests/fresh_install.py"):
        assert digest(ROOT / name) == old_hashes[name], f"Cambio el instrumento: {name}"
    target = next(s for s in result["stages"] if s["concurrency"] == result["goals"]["target_concurrency"])
    old = next(s for s in baseline["stages"] if s["concurrency"] == baseline["goals"]["target_concurrency"])
    samples = [json.loads(line) for line in (OUT / "resultado-muestras.jsonl").read_text().splitlines()]
    requests = sum(s["requests"] for s in result["stages"])
    assert sum(s["operation"] != "purchase_flow" for s in samples) == requests
    resources = {}
    for sample in json.loads((OUT / "resultado-recursos.json").read_text()):
        if not sample["phase"].startswith("vu-"):
            continue
        for row in sample.get("containers", []):
            name = row["Name"].removeprefix(result["project"] + "-").removesuffix("-1")
            values = resources.setdefault(name, {"cpu": [], "mem": []})
            values["cpu"].append(float(row["CPUPerc"].rstrip("%")))
            value, unit = re.match(r"([\d.]+)(\w+)", row["MemUsage"].split("/")[0].strip()).groups()
            values["mem"].append(float(value) * {"B": 1/1048576, "KiB": 1/1024, "MiB": 1, "GiB": 1024}[unit])
    resource_summary = {name: {"cpu_peak_percent": max(v["cpu"]), "cpu_mean_percent": statistics.mean(v["cpu"]),
                        "memory_peak_mib": max(v["mem"]), "samples": len(v["cpu"])} for name, v in resources.items()}
    (OUT / "recursos-resumen.json").write_text(json.dumps(resource_summary, indent=2), encoding="utf-8")
    with (OUT / "metricas.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["concurrency", "operation", "samples", "errors", "p50_ms", "p95_ms", "p99_ms", "max_ms", "per_second"])
        writer.writeheader()
        for stage in result["stages"]:
            for operation, metrics in stage["operations"].items():
                writer.writerow({"concurrency": stage["concurrency"], "operation": operation,
                                 **{key: metrics[key] for key in writer.fieldnames[2:]}})
    before = old["operations"]["purchase_flow"]
    after = target["operations"]["purchase_flow"]
    reduction = (1 - after["p95_ms"] / before["p95_ms"]) * 100
    invariant = result["invariants"]
    status = "APROBADO para el perfil local" if result["evaluation"]["passed"] else "OBJETIVOS NO CUMPLIDOS"
    lines = ["# Rendimiento tras optimizar Outbox", "", f"**Resultado: {status}.**", "",
             "Se repitio la misma prueba: objetivos JSON, generador, calculo de metricas y preparacion de entorno con hashes identicos a la linea base. No se relajo ningun umbral. [Linea base preservada](baseline-9b6eeb3/README.md) y [objetivos](objetivos.md).", "",
             "## Cambio y garantias", "",
             "El worker drena inmediatamente cualquier lote sano, completo o parcial. Cuando la cola esta vacia espera un segundo; si falla una entrega o hay excepcion de DB mantiene el backoff de cinco segundos. Cada lote reutiliza una conexion/canal privados y declara una vez cada destino; conserva ACK por mensaje, mandatory, persistencia, IDs estables, SQL, skip_locked y entrega al menos una vez.", "",
             "Las diez pruebas nuevas verifican drenaje de 120 entregas, backoff con fallos parciales/DB/broker, dos workers concurrentes, recuperacion tras fallo de commit, reutilizacion de canal, NACK, mensajes no enrutables y ausencia de conexiones al broker en vacio. Un fallo de commit despues del ACK puede reenviar el mismo ID; los consumidores siguen siendo idempotentes.", "",
             "Se conserva tambien el [primer ensayo intermedio](iteracion-1-c81a190/README.md): solo drenar lotes completos dejo p95 en 10,203 s y no aprobo. La version final agrega menor espera en vacio y conexion por lote sin modificar el instrumento.", "",
             "## Comparacion a 20 usuarios", "",
             "| Metrica | Antes | Despues | Objetivo |", "| --- | ---: | ---: | ---: |",
             f"| Compra p95 (s) | {before['p95_ms']/1000:.3f} | {after['p95_ms']/1000:.3f} | <=10 |",
             f"| Compra p99 (s) | {before['p99_ms']/1000:.3f} | {after['p99_ms']/1000:.3f} | <=15 |",
             f"| Solicitudes utiles/s | {old['useful_requests_per_second']:.2f} | {target['useful_requests_per_second']:.2f} | >=20 |",
             f"| Errores HTTP inesperados (%) | {old['error_percent']:.2f} | {target['error_percent']:.2f} | <1 |",
             f"| Compras medidas a 20 usuarios | {before['samples']} | {after['samples']} | >=100 |", "",
             f"Reduccion observada de p95: **{reduction:.2f}%**. Es una comparacion de dos ejecuciones locales, no una demostracion de causalidad exclusiva ni una estimacion de capacidad productiva.", "",
             "## Etapas de la nueva ejecucion", "",
             "| Usuarios | Segundos reales | HTTP | HTTP/s total | HTTP/s util | Errores (%) | Compra p95 (s) | Compra p99 (s) |",
             "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for stage in result["stages"]:
        flow = stage["operations"]["purchase_flow"]
        lines.append(f"| {stage['concurrency']} | {stage['elapsed_seconds']:.2f} | {stage['requests']} | {stage['requests_per_second']:.2f} | {stage['useful_requests_per_second']:.2f} | {stage['error_percent']:.2f} | {flow['p95_ms']/1000:.3f} | {flow['p99_ms']/1000:.3f} |")
    lines += ["", "## Todos los objetivos de latencia a 20 usuarios", "",
              "| Operacion | Muestras | p50 (ms) | p95 (ms) | p99 (ms) | Limite p95/p99 (ms) | Estado |",
              "| --- | ---: | ---: | ---: | ---: | --- | --- |"]
    for operation, limits in result["goals"]["latency_ms"].items():
        m = target["operations"][operation]
        passed = m["p95_ms"] <= limits["p95"] and m["p99_ms"] <= limits["p99"] and m["samples"] >= result["goals"]["minimum_samples_per_operation"]
        lines.append(f"| {operation} | {m['samples']} | {m['p50_ms']:.2f} | {m['p95_ms']:.2f} | {m['p99_ms']:.2f} | {limits['p95']}/{limits['p99']} | {'Cumple' if passed else 'No cumple'} |")
    failed = [c for c in result["evaluation"]["checks"] if not c["passed"]]
    if failed:
        lines += ["", "## Incumplimientos que siguen abiertos", "",
                  "La compra completa entra en su objetivo, pero no se aprueba RNF-01 mientras fallen otros limites. No se han relajado umbrales ni se ha reducido la carga para ocultarlo.", "",
                  "| Criterio | Medido | Limite |", "| --- | ---: | ---: |"]
        for check in failed:
            lines.append(f"| {check['criterion']} | {check['observed']:.2f} | {check.get('required_max', check.get('required_min'))} |")
        lines += ["", "Al reducir la espera se procesa mas trafico y se generan mas pedidos durante las mismas etapas. Los historiales crecen mas que en la linea base; no es una comparacion de bases con cardinalidad final identica. El perfil inicial, tiempos, objetivos y generador si permanecen iguales.", "",
                  "El siguiente trabajo es perfilar SQL y tiempos de espera del historial, y las llamadas HTTP/ocupacion de conexiones de checkout y pago bajo 20 usuarios. En el codigo actual se crean clientes HTTP sin reutilizacion por muchas llamadas entre servicios; es un candidato a investigar, no una causa demostrada por esta medicion. Medir trazas y planes antes de cambiar otros componentes. Mantener la mejora Outbox y repetir el mismo perfil despues de corregir esos puntos."]
    lines += ["", "## Integridad", "",
              f"{requests} solicitudes HTTP medidas; {sum(s['errors'] for s in result['stages'])} errores inesperados. Compras totales contando calentamiento: {invariant['completed_flows_including_warmup']}. Integridad: {'APROBADA' if invariant['passed'] else 'FALLIDA'}.", "",
              f"Pagos: {invariant['payments']}. Pedidos: {invariant['orders']}. Inventario: {invariant['inventory']}.", "",
              "## Entorno y recursos", "",
              f"Host {result['host']['platform']}; Docker {result['host']['docker_server']}, {result['host']['docker_cpus']} CPU y {result['host']['docker_memory_bytes']/1024**3:.2f} GiB. Contenedores adicionales activos: antes {baseline['host']['other_running_containers']}, despues {result['host']['other_running_containers']}. Generador y servicios comparten equipo. Versiones de dependencias iguales: {result['dependency_versions'] == baseline['dependency_versions']}. Versiones medidas: {result['dependency_versions']}.", "",
              "CPU 100 % representa aproximadamente un nucleo. Se muestrea cada cinco segundos mas el tiempo de docker stats; los maximos no necesariamente coinciden. No hay limites de recursos por servicio.", "",
              "| Servicio | CPU media (%) | CPU maxima (%) | RAM maxima (MiB) | Muestras |", "| --- | ---: | ---: | ---: | ---: |"]
    for name, metrics in sorted(resource_summary.items(), key=lambda item: item[1]["cpu_peak_percent"], reverse=True):
        lines.append(f"| {name} | {metrics['cpu_mean_percent']:.2f} | {metrics['cpu_peak_percent']:.2f} | {metrics['memory_peak_mib']:.2f} | {metrics['samples']} |")
    lines += ["", "## Alcance y reproducibilidad", "",
              "Carga cerrada a 1/5/10/20 usuarios, 60 segundos programados por etapa y 15 segundos de calentamiento excluido. La duracion real incluye ciclos en curso. Preparacion, registro y login fuera de la medida. Catalogo de 100 productos; paginas de 20; compra de un producto compartido con stock suficiente; historiales pequenos que crecen por etapa. Los sondeos quedan fuera del throughput util; la compra termina al observar PAID. Integridad de inventario y eventos se verifica despues de drenar pendientes.", "",
              "No demuestra sostenibilidad durante horas, saturacion, tasas abiertas de llegada, grandes bases, replicas, otros hosts ni SLA de produccion. Hay diferencias de carga externa no controladas entre ejecuciones. Las dependencias no estan fijadas, aunque se registran y comparan versiones. La instalacion habitual no se modifica por el benchmark y el proyecto aislado se elimina al terminar.", "",
              "```powershell\npython -X utf8 tests/performance_metrics_test.py\npython -X utf8 tests/performance_load.py\npython -X utf8 tests/performance_report.py\n```", "",
              "[Resultado](resultado.json), [CSV](metricas.csv), [muestras](resultado-muestras.jsonl), [recursos](resultado-recursos.json), [recursos resumidos](recursos-resumen.json), [comparacion JSON](comparacion-outbox.json), [hashes](evidencias.json), [linea base completa](baseline-9b6eeb3/informe.md). Log local: ejecucion.log. La etiqueta v0.1.0-rc.1 permanece intacta."]
    (OUT / "informe.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    comparison = {"same_goals": True, "same_instrument": True, "same_dataset": True, "baseline_evidence_commit": "9b6eeb3",
                  "same_dependency_versions": result["dependency_versions"] == baseline["dependency_versions"],
                  "baseline_source_commit": baseline["source_commit"], "source_commit": result["source_commit"],
                  "before_p95_ms": before["p95_ms"], "after_p95_ms": after["p95_ms"], "p95_reduction_percent": reduction,
                  "before_useful_rps": old["useful_requests_per_second"], "after_useful_rps": target["useful_requests_per_second"],
                  "evaluation": result["evaluation"], "invariants_passed": invariant["passed"]}
    (OUT / "comparacion-outbox.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    paths = ["tests/performance_goals.json", "tests/performance_metrics.py", "tests/performance_load.py", "tests/performance_metrics_test.py",
             "tests/performance_report.py", "tests/payment_stability.py", "tests/fresh_install.py", "docker-compose.yml",
             "services/payment-service/app/outbox.py", "services/payment-service/app/core/rabbitmq.py",
             "docs/rendimiento/resultado.json", "docs/rendimiento/resultado-muestras.jsonl", "docs/rendimiento/resultado-recursos.json"]
    (OUT / "evidencias.json").write_text(json.dumps({"source_commit": result["source_commit"], "goals_unchanged": True,
                  "hash_format": "SHA-256 de bytes UTF-8 con CRLF normalizado a LF", "sha256": {name: digest(ROOT / name) for name in paths}}, indent=2), encoding="utf-8")
    print(f"Informe generado: {status}; compra p95 {before['p95_ms']/1000:.3f} -> {after['p95_ms']/1000:.3f} s")


if __name__ == "__main__":
    main()
