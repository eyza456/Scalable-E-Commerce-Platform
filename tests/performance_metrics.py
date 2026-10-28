"""Estadisticas y evaluacion explicita; no descartar errores o muestras lentas."""
from collections import Counter
import math


def percentile(values, percent):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percent / 100) - 1)] if ordered else None


def summarize(samples, elapsed):
    output = {}
    for operation in sorted({s["operation"] for s in samples}):
        selected = [s for s in samples if s["operation"] == operation]
        values = [s["ms"] for s in selected]
        errors = sum(not s["ok"] for s in selected)
        output[operation] = {
            "samples": len(selected), "errors": errors, "error_percent": errors / len(selected) * 100,
            "p50_ms": percentile(values, 50), "p95_ms": percentile(values, 95), "p99_ms": percentile(values, 99),
            "max_ms": max(values), "per_second": len(selected) / elapsed,
            "statuses": dict(Counter(str(s["status"]) for s in selected)),
        }
    requests = [s for s in samples if s["operation"] != "purchase_flow"]
    useful = [s for s in requests if not s["operation"].endswith("_poll")]
    return {"operations": output, "elapsed_seconds": elapsed, "requests": len(requests),
            "errors": sum(not s["ok"] for s in requests),
            "error_percent": sum(not s["ok"] for s in requests) / len(requests) * 100 if requests else 100,
            "requests_per_second": len(requests) / elapsed,
            "useful_requests_per_second": len(useful) / elapsed}


def evaluate(summary, goals, correctness):
    checks = []
    for operation, limits in goals["latency_ms"].items():
        observed = summary["operations"].get(operation, {})
        count = observed.get("samples", 0)
        checks.append({"criterion": f"{operation}.samples", "observed": count,
                       "required_min": goals["minimum_samples_per_operation"],
                       "passed": count >= goals["minimum_samples_per_operation"]})
        for metric, maximum in limits.items():
            value = observed.get(metric + "_ms")
            checks.append({"criterion": f"{operation}.{metric}_ms", "observed": value, "required_max": maximum,
                           "passed": value is not None and value <= maximum})
    checks += [{"criterion": "unexpected_errors_percent", "observed": summary["error_percent"],
                "required_below": goals["maximum_unexpected_error_percent"],
                "passed": summary["error_percent"] < goals["maximum_unexpected_error_percent"]},
               {"criterion": "useful_requests_per_second", "observed": summary["useful_requests_per_second"],
                "required_min": goals["minimum_useful_requests_per_second"],
                "passed": summary["useful_requests_per_second"] >= goals["minimum_useful_requests_per_second"]},
               {"criterion": "business_invariants", "observed": correctness, "passed": correctness is True}]
    return {"passed": all(c["passed"] for c in checks), "checks": checks}
