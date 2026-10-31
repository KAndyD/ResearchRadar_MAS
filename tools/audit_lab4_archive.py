"""Test the submission ZIP from a separate directory without Git or network."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "deliverables/ResearchRadar_MAS_lab4_v1.0_submission.zip"
EVIDENCE = ROOT / "audit_evidence/lab4_archive_reproduction.json"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ResearchRadarLab4Audit-") as temp:
        target = Path(temp).resolve()
        assert not target.is_relative_to(ROOT.resolve())
        with ZipFile(ARCHIVE) as archive:
            assert archive.testzip() is None
            for name in archive.namelist():
                assert (target / name).resolve().is_relative_to(target)
            archive.extractall(target)
        assert not (target / ".git").exists()
        subprocess.run([sys.executable, "-m", "venv", "--system-site-packages",
                        str(target / "venv")], check=True, timeout=40)
        python = target / "venv/Scripts/python.exe"
        env = os.environ.copy()
        env.pop("OPENROUTER_API_KEY", None)
        env["PYTHONPATH"] = str(target / "src")
        env["PATH"] = os.pathsep.join((str(target / "venv/Scripts"),
                                         os.environ.get("SystemRoot", "C:\\Windows") + "\\System32",
                                         os.environ.get("SystemRoot", "C:\\Windows")))
        env["PIP_NO_INDEX"] = "1"
        checks = [
            [str(python), "-c", "import researchradar, pathlib; "
             "print(pathlib.Path(researchradar.__file__).resolve())"],
            [str(python), "-m", "unittest", "discover", "-s", "tests", "-q"],
            [str(python), "-m", "researchradar.cli_stage4", "multi agent systems",
             "--mode", "demo", "--analysis", "recorded", "--recorded-analysis",
             "data/lab4_fixture_analysis.json", "--output", "run_output/demo.json"],
            [str(python), "tools/run_lab4_experiments.py", "--repeats", "1",
             "--output", "run_output/faults"],
            [str(python), "tools/verify_lab4_results.py", "run_output/faults"],
            [str(python), "tools/run_lab4_llm_experiments.py", "--output",
             "run_output/llm"],
            [str(python), "tools/verify_lab4_llm_results.py", "run_output/llm"],
        ]
        outputs = []
        for command in checks:
            done = subprocess.run(command, cwd=target, env=env, capture_output=True,
                                  text=True, timeout=100)
            if done.returncode:
                raise RuntimeError(f"archive check failed: {command[1:]}\n"
                                   + done.stdout[-1000:] + done.stderr[-1000:])
            outputs.append({"command": command[1:], "stdout_tail": done.stdout[-500:],
                            "stderr_tail": done.stderr[-500:]})
        imported = Path(outputs[0]["stdout_tail"].strip())
        assert imported.is_relative_to(target / "src")
        reproduced = json.loads((target / "run_output/faults/metadata.json").read_text())
        assert reproduced["protected_code_commit"] is None
        assert reproduced["protected_code_commit_source"] == "unavailable_no_git_metadata"
        report = {"archive_sha256": sha256(ARCHIVE.read_bytes()).hexdigest(),
                  "outside_repository": True, "git_metadata_available": False,
                  "git_executable_on_path": False, "network_calls": 0,
                  "import_from_extracted_copy": True, "checks": outputs}
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"archive reproduction passed: {len(outputs)} checks; {EVIDENCE}")


if __name__ == "__main__":
    main()
