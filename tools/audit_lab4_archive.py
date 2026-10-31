"""Reproduce the final v1.1 audit ZIP outside Git, without network access."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "deliverables/ResearchRadar_MAS_lab4_v1.1_audit.zip"
EVIDENCE = ROOT / "run_output/lab4_v1_1_archive_reproduction.json"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ResearchRadarLab4v11Audit-") as temp:
        target = Path(temp).resolve()
        assert not target.is_relative_to(ROOT.resolve())
        with ZipFile(ARCHIVE) as archive:
            assert archive.testzip() is None
            manifest = archive.read("ARCHIVE_MANIFEST.txt").decode("utf-8")
            lines = manifest.split("Archive member SHA-256:\n", 1)[1].splitlines()
            assert len(lines) == len(archive.namelist()) - 1
            for line in lines:
                digest, name = line.split("  ", 1)
                assert sha256(archive.read(name)).hexdigest() == digest
                assert (target / name).resolve().is_relative_to(target)
                assert not name.endswith(".env") and ".git/" not in name
                assert not name.endswith((".sqlite3", ".pyc"))
            archive.extractall(target)
        assert not (target / ".git").exists()
        subprocess.run([sys.executable, "-m", "venv",
                        str(target / "venv")], check=True, timeout=50)
        python = target / "venv/Scripts/python.exe"
        env = os.environ.copy()
        env.pop("OPENROUTER_API_KEY", None)
        env["PYTHONPATH"] = str(target / "src")
        system_root = os.environ.get("SystemRoot", "C:\\Windows")
        env["PATH"] = os.pathsep.join((str(target / "venv/Scripts"),
                                       system_root + "\\System32", system_root))
        env["PIP_NO_INDEX"] = "1"
        assert shutil.which("git", path=env["PATH"]) is None
        commands = [
            [str(python), "-m", "pip", "install", "--no-index", "--find-links",
             "vendor/wheels", "-e", "."],
            [str(python), "-c", "import researchradar,pathlib; "
             "print(pathlib.Path(researchradar.__file__).resolve())"],
            [str(python), "-m", "unittest", "discover", "-s", "tests", "-q"],
            [str(python), "-m", "researchradar.cli", "multi agent systems", "--mode", "demo",
             "--output", "run_output/stage1.json"],
            [str(python), "-m", "researchradar.cli_stage2", "multi agent systems",
             "--mode", "demo", "--coordination", "contract-net",
             "--output", "run_output/stage2.json"],
            [str(python), "-m", "researchradar.cli_stage3", "multi agent systems",
             "--mode", "demo", "--resource-policy", "negotiation",
             "--output", "run_output/stage3.json"],
            [str(python), "-m", "researchradar.cli_stage4", "multi agent systems",
             "--mode", "demo", "--analysis", "recorded", "--recorded-analysis",
             "data/lab4_v1.1_fixture_analysis.json", "--output", "run_output/stage4.json"],
            [str(python), "tools/run_lab4_experiments.py", "--repeats", "1",
             "--output", "run_output/faults"],
            [str(python), "tools/verify_lab4_results.py", "run_output/faults"],
            [str(python), "tools/verify_lab4_results.py", "experiments/lab4/results"],
            [str(python), "tools/run_lab4_llm_experiments.py", "--output",
             "run_output/legacy_llm"],
            [str(python), "tools/verify_lab4_llm_results.py", "run_output/legacy_llm"],
            [str(python), "tools/run_lab4_v1_1_llm_experiments.py", "--output",
             "run_output/new_llm"],
            [str(python), "tools/verify_lab4_v1_1_llm_results.py", "run_output/new_llm"],
            [str(python), "tools/verify_lab4_v1_1_live.py"],
        ]
        outputs = []
        for command in commands:
            done = subprocess.run(command, cwd=target, env=env, capture_output=True,
                                  text=True, timeout=120)
            if done.returncode:
                raise RuntimeError(f"archive check failed: {command[1:]}\n"
                                   + done.stdout[-1200:] + done.stderr[-1200:])
            outputs.append({"command": command[1:], "stdout_tail": done.stdout[-400:],
                            "stderr_tail": done.stderr[-400:]})
        imported = Path(outputs[1]["stdout_tail"].strip())
        assert imported.is_relative_to(target / "src")
        reproduced = json.loads((target / "run_output/faults/metadata.json").read_text())
        assert reproduced["protected_code_commit"] is None
        assert reproduced["protected_code_commit_source"] == "unavailable_no_git_metadata"
        report = {"archive_sha256": sha256(ARCHIVE.read_bytes()).hexdigest(),
                  "outside_repository": True, "git_metadata_available": False,
                  "git_executable_on_path": False, "network_calls": 0,
                  "import_from_extracted_copy": True,
                  "manifest_members_verified": len(lines), "checks": outputs}
    EVIDENCE.parent.mkdir(exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"audit ZIP reproduced: {len(outputs)} checks, {len(lines)} member hashes")


if __name__ == "__main__":
    main()
