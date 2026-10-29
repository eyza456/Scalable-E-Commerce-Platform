"""Verify 2/3/1/2 independent scaling for every application, not only orders."""
import hashlib
import json

import multinstance as multi
from fresh_install import APPS, ROOT

REPORT = ROOT / "docs/escalabilidad/independencia.json"
multi.backend.LOG = REPORT.with_suffix(".log")


class IndependentMultinstance(multi.Multinstance):
    def wait_replicas(self, service):
        self.py("user-service",'''
import json,sys,time,urllib.request
for base in json.loads(sys.argv[1]):
 deadline=time.monotonic()+90
 while True:
  try:
   with urllib.request.urlopen(base+'/health',timeout=3) as r:assert json.load(r)['status']=='healthy'
   break
  except Exception:
   if time.monotonic()>deadline:raise
   time.sleep(1)
''',json.dumps(self.addresses(service)))

    def healthy(self):
        for service in APPS:
            self.wait_replicas(service)

    def prepare(self):
        super().prepare()
        name="tests/multinstance_independence.py"
        self.result["sha256"][name]=hashlib.sha256((ROOT/name).read_bytes().replace(b"\r\n",b"\n")).hexdigest()

    def verify(self):
        super().verify()
        self.phase("Comprobando escalado independiente de cada uno de los seis servicios...")
        results={}
        for service in APPS:
            before={n:sorted(c["Id"] for c in self.containers(n)) for n in APPS if n!=service}
            for size in (3,1,2):
                self.dc("up","-d","--no-deps","--no-recreate","--scale",f"{service}={size}",service)
                assert len(self.containers(service))==size
                assert before=={n:sorted(c["Id"] for c in self.containers(n)) for n in before}
                # Wait inside each new process; HTTP readiness is independent
                # from Docker's Running flag.
                self.wait_replicas(service)
            results[service]={"replicas":[2,3,1,2],"other_app_ids_unchanged":True,"all_replicas_healthy":True}
        self.result["checks"]["all_services_independent_scaling"]=results


def main():
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    multi.backend.LOG.write_text("",encoding="utf-8")
    test=IndependentMultinstance()
    try:
        test.verify()
        test.result["status"]="passed"
    except Exception as exc:
        test.result.update(status="failed",error=str(exc))
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
            test.result.update(status="failed",cleanup_error=str(exc))
            raise
        finally:REPORT.write_text(json.dumps(test.result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("OK: every application scaled independently; isolated project removed.")


if __name__=="__main__":main()
