"""One collection run for the scheduler: scan.py --save, one log line per run.

Runs without a console (pythonw), so the scan's report is captured and only
the outcome is appended to data/collect.log: time, seconds taken, file saved,
or the error. Schedule it every 5 minutes; each run is independent.
"""
import contextlib
import io
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    sys.argv = ["scan.py", "--save"]
    out = io.StringIO()
    t0 = time.time()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            import scan
            scan.main()
        failed = [ln.strip() for ln in out.getvalue().splitlines() if "FAILED" in ln]
        saved = [ln.strip() for ln in out.getvalue().splitlines() if ln.startswith("Saved")]
        status = "ok " + (saved[-1] if saved else "nothing saved")
        if failed:
            status += " | " + "; ".join(failed)
    except Exception:
        status = "ERROR " + traceback.format_exc().strip().splitlines()[-1]
    log = ROOT / "data" / "collect.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z  {time.time() - t0:5.1f}s  {status}\n")


if __name__ == "__main__":
    run()
