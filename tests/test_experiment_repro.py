"""Regression coverage for experiments outside Git and the installed checkout."""
from __future__ import annotations

import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from tools import run_experiments


ROOT = Path(__file__).resolve().parents[1]


class ExperimentReproductionTests(unittest.TestCase):
    def test_script_runs_from_independent_copy_without_git_or_git_executable(self):
        with TemporaryDirectory(prefix="researchradar-repro-") as temporary:
            base = Path(temporary)
            copy = base / "extracted"
            (copy / "src").mkdir(parents=True)
            (copy / "tools").mkdir()
            (copy / "data").mkdir()
            shutil.copytree(ROOT / "src/researchradar", copy / "src/researchradar",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            shutil.copy2(ROOT / "tools/run_experiments.py", copy / "tools/run_experiments.py")
            shutil.copy2(ROOT / "data/frozen_sources.json", copy / "data/frozen_sources.json")
            self.assertFalse((copy / ".git").exists())
            outside = base / "unrelated-cwd"
            outside.mkdir()
            output = base / "new-results"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(copy / "src")
            env["PATH"] = ""  # sys.executable is absolute; Git cannot be discovered.
            env.pop("OPENROUTER_API_KEY", None)
            origin = subprocess.run([sys.executable, "-c",
                "import researchradar.coordination as c; print(c.__file__)"],
                cwd=outside, env=env, capture_output=True, text=True, timeout=15,
                check=True).stdout.strip()
            self.assertEqual(Path(origin).resolve(),
                             (copy / "src/researchradar/coordination.py").resolve())
            run = subprocess.run([sys.executable, str(copy / "tools/run_experiments.py"),
                                  "--repeats", "1", "--output", str(output)],
                                 cwd=outside, env=env, capture_output=True, text=True,
                                 timeout=60)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            with (output / "raw.csv").open(encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 8)
            self.assertEqual(len({(r["scenario"], r["seed"], r["mechanism"])
                                  for r in rows}), 8)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            paired = json.loads((output / "paired.json").read_text(encoding="utf-8"))
            self.assertEqual(len(summary), 8)
            self.assertEqual(len(paired), 4)
            for item in summary:
                matching = [r for r in rows if r["scenario"] == item["scenario"]
                            and r["mechanism"] == item["mechanism"]]
                self.assertEqual(len(matching), 1)
                self.assertAlmostEqual(float(matching[0]["wall_ms"]),
                                       item["wall_ms_mean"], places=5)
            for item in paired:
                pair = {r["mechanism"]: r for r in rows
                        if r["scenario"] == item["scenario"]}
                difference = (float(pair["contract-net"]["wall_ms"])
                              - float(pair["centralized"]["wall_ms"]))
                self.assertAlmostEqual(difference, item["wall_ms_difference_mean"], places=5)
            metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["version"], "lab2-v1.1")
            self.assertEqual(metadata["version_source"], "script_constant")
            self.assertIsNone(metadata["code_commit_at_run"])
            self.assertEqual(metadata["code_commit_source"], "unavailable_no_git_metadata")
            self.assertEqual(metadata["frozen_sha256"],
                             sha256((copy / "data/frozen_sources.json").read_bytes()).hexdigest())
            self.assertEqual((metadata["repeats"], metadata["runs"]), (1, 8))
            self.assertTrue(metadata["python_version"])
            self.assertTrue(metadata["platform"])
            self.assertEqual(len(list((output / "traces").glob("*.json"))), 8)
            self.assertEqual(len(list(output.glob("*.svg"))), 3)

    def test_git_metadata_failures_are_nonfatal_and_never_invent_sha(self):
        with TemporaryDirectory(prefix="researchradar-git-") as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            cases = [
                (FileNotFoundError(), "unavailable_git_not_installed"),
                (subprocess.CalledProcessError(128, "git"), "unavailable_git_command_failed"),
                (subprocess.TimeoutExpired("git", 3), "unavailable_git_timeout"),
            ]
            with patch.object(run_experiments, "ROOT", root):
                for failure, source in cases:
                    with self.subTest(source=source), patch.object(
                            run_experiments.subprocess, "run", side_effect=failure):
                        self.assertEqual(run_experiments.code_revision(), (None, source))
                with patch.object(run_experiments.subprocess, "run",
                                  side_effect=[Mock(stdout=""), Mock(stdout="not a SHA\n")]):
                    self.assertEqual(run_experiments.code_revision(),
                                     (None, "unavailable_invalid_git_response"))
                sha = "a" * 40
                with patch.object(run_experiments.subprocess, "run",
                                  side_effect=[Mock(stdout=""), Mock(stdout=sha + "\n")]):
                    self.assertEqual(run_experiments.code_revision(), (sha, "git_head"))
                with patch.object(run_experiments.subprocess, "run",
                                  return_value=Mock(stdout=" M tools/run_experiments.py\n")):
                    self.assertEqual(run_experiments.code_revision(),
                                     (None, "unavailable_dirty_checkout"))


if __name__ == "__main__":
    unittest.main()
