"""Run the negotiation experiment from a copied project without Git metadata."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Stage3ArchiveReproductionTests(unittest.TestCase):
    def test_independent_copy_runs_without_git(self):
        with TemporaryDirectory(prefix="researchradar-stage3-") as temporary:
            base = Path(temporary)
            copy = base / "extracted"
            (copy / "src").mkdir(parents=True)
            (copy / "tools").mkdir()
            (copy / "data").mkdir()
            (copy / "experiments/lab3").mkdir(parents=True)
            shutil.copytree(ROOT / "src/researchradar", copy / "src/researchradar",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            shutil.copy2(ROOT / "data/frozen_sources.json", copy / "data/frozen_sources.json")
            shutil.copy2(ROOT / "experiments/lab3/scenarios.json",
                         copy / "experiments/lab3/scenarios.json")
            shutil.copy2(ROOT / "tools/run_negotiation_experiments.py",
                         copy / "tools/run_negotiation_experiments.py")
            self.assertFalse((copy / ".git").exists())
            output = base / "smoke"
            outside = base / "other-cwd"
            outside.mkdir()
            env = os.environ.copy()
            env["PYTHONPATH"] = str(copy / "src")
            env["PATH"] = ""
            env.pop("OPENROUTER_API_KEY", None)
            module = subprocess.run([sys.executable, "-c",
                "import researchradar.negotiation as n; print(n.__file__)"],
                cwd=outside, env=env, capture_output=True, text=True,
                check=True, timeout=15).stdout.strip()
            self.assertEqual(Path(module).resolve(),
                             (copy / "src/researchradar/negotiation.py").resolve())
            result = subprocess.run([sys.executable,
                str(copy / "tools/run_negotiation_experiments.py"),
                "--repeats", "1", "--output", str(output)],
                cwd=outside, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with (output / "raw.csv").open(encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 10)
            metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
            self.assertIsNone(metadata["code_commit_at_run"])
            self.assertEqual(metadata["code_commit_source"],
                             "unavailable_no_git_metadata")
            self.assertEqual(len(list((output / "traces").glob("*.json"))), 10)
            self.assertEqual(len(list(output.glob("*.svg"))), 4)


if __name__ == "__main__":
    unittest.main()
