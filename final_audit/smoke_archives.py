"""Small new experiment runs in isolated release extractions, never saved corpora."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
AUDIT = json.loads((ROOT / "run_output/final_audit_execution_raw.json").read_text(encoding="utf-8"))
BASE = Path(AUDIT["workspace"])
CASES = {
    "lab2-v1.1": ["tools/run_experiments.py", "--repeats", "1", "--output", "run_output/audit_smoke"],
    "lab3-v1.1": ["tools/run_negotiation_experiments.py", "--repeats", "1", "--output", "run_output/audit_smoke"],
    "lab4-v1.1": ["tools/run_lab4_experiments.py", "--repeats", "1", "--output", "run_output/audit_smoke"],
}


def main() -> None:
    output = {}
    for tag, command in CASES.items():
        cwd = BASE / tag
        env = os.environ.copy()
        env["PYTHONPATH"] = str(cwd / "src")
        env["PYTHONNOUSERSITE"] = "1"
        process = subprocess.run([sys.executable] + command, cwd=cwd, env=env,
                                 capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 timeout=300)
        output[tag] = {"command": command, "exit_code": process.returncode,
                       "stdout_tail": process.stdout[-1200:], "stderr_tail": process.stderr[-500:]}
        print(tag, process.returncode, process.stdout[-180:].strip())
        if process.returncode:
            raise RuntimeError(f"smoke failed: {tag}")
    (ROOT / "final_audit/smoke_log.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
