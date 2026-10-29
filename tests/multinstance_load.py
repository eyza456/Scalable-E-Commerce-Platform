"""Original local-mvp-20vu-v1 load and thresholds on two replicas per service."""
import hashlib
import json

import fresh_install as backend
import performance_load as load
from multinstance_independence import IndependentMultinstance
from fresh_install import ROOT

OUT = ROOT / "docs/escalabilidad/carga"
backend.LOG = OUT / "ejecucion.log"
load.OUT = OUT


class ReplicaPerformance(IndependentMultinstance, load.Performance):
    def __init__(self):
        goals_path = ROOT / "tests/performance_goals.json"
        load.Performance.__init__(self, json.loads(goals_path.read_text(encoding="utf-8")))
        self.result["goals_file_sha256"] = hashlib.sha256(goals_path.read_bytes()).hexdigest()
        self.result["host"]["other_running_containers"] = len(self.run(["docker","ps","-q"],log=False).splitlines())

    def race(self):
        # Same instrument, dataset, warmup, stages and goals. Keep the baseline
        # report untouched; this measurement belongs to the replica profile.
        load.Performance.exercise(self)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    backend.LOG.write_text("",encoding="utf-8")
    test = ReplicaPerformance()
    try:
        test.verify()
    except Exception as exc:
        test.result.update(status="execution-failed",error=str(exc))
        if test.compose:
            try:test.dc("logs","--no-color","--tail","50",timeout=60)
            except Exception:pass
        raise
    finally:
        try:
            test.cleanup()
            assert test.original_state()==test.original,"Existing containers changed"
            test.result["checks"]["original_installation"]="Container IDs, start times and restart counts unchanged"
        except Exception as exc:
            test.result.update(status="cleanup-failed",cleanup_error=str(exc))
            raise
        finally:
            for name in ("tests/multinstance_load.py","tests/performance_load.py","tests/performance_metrics.py"):
                test.result.setdefault("sha256",{})[name]=hashlib.sha256((ROOT/name).read_bytes().replace(b"\r\n",b"\n")).hexdigest()
            (OUT/"resultado.json").write_text(json.dumps(test.result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            (OUT/"muestras.jsonl").write_text("\n".join(json.dumps(s) for s in test.samples)+"\n",encoding="utf-8")
            (OUT/"recursos.json").write_text(json.dumps(test.resources,indent=2)+"\n",encoding="utf-8")
    print("Replica load result:",test.result["status"],flush=True)
    if test.result["status"]!="passed":raise SystemExit(2)


if __name__=="__main__":main()
