"""Read-only verification of the four published ResearchRadar release bundles."""
from __future__ import annotations

import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "run_output" / "final_audit_downloads"
GH = Path(r"C:\Program Files\GitHub CLI\gh.exe")
TAGS = ("lab1-v1.2", "lab2-v1.1", "lab3-v1.1", "lab4-v1.1")
COMMANDS = {
    "lab1-v1.2": [("tests", ["-m", "unittest", "discover", "-s", "tests", "-q"]),
                   ("demo", ["-m", "researchradar.cli", "multi agent systems", "--mode", "demo",
                             "--output", "run_output/audit_stage1.json"])],
    "lab2-v1.1": [("tests", ["-m", "unittest", "discover", "-s", "tests", "-q"]),
                   ("demo_centralized", ["-m", "researchradar.cli_stage2", "multi agent systems", "--mode", "demo",
                                         "--coordination", "centralized", "--output", "run_output/audit_stage2_c.json"]),
                   ("demo_contract_net", ["-m", "researchradar.cli_stage2", "multi agent systems", "--mode", "demo",
                                        "--coordination", "contract-net", "--output", "run_output/audit_stage2_cn.json"])],
    "lab3-v1.1": [("tests", ["-m", "unittest", "discover", "-s", "tests", "-q"]),
                   ("demo_baseline", ["-m", "researchradar.cli_stage3", "multi agent systems", "--mode", "demo",
                                      "--resource-policy", "baseline", "--output", "run_output/audit_stage3_b.json"]),
                   ("demo_negotiation", ["-m", "researchradar.cli_stage3", "multi agent systems", "--mode", "demo",
                                         "--resource-policy", "negotiation", "--credits", "4", "--slots", "1",
                                         "--output", "run_output/audit_stage3_n.json"]),
                   ("verify_results", ["tools/verify_lab3_results.py", "--results", "experiments/lab3/results"])],
    "lab4-v1.1": [("tests", ["-m", "unittest", "discover", "-s", "tests", "-q"]),
                   ("demo_stage4", ["-m", "researchradar.cli_stage4", "multi agent systems", "--mode", "demo",
                                    "--analysis", "recorded", "--recorded-analysis", "data/lab4_v1.1_fixture_analysis.json",
                                    "--output", "run_output/audit_stage4.json"]),
                   ("verify_faults", ["tools/verify_lab4_results.py", "experiments/lab4/results"]),
                   ("verify_old_llm", ["tools/verify_lab4_llm_results.py", "experiments/lab4/llm_results"]),
                   ("verify_new_llm", ["tools/verify_lab4_v1_1_llm_results.py", "experiments/lab4_v1_1/results"]),
                   ("verify_live_replay", ["tools/verify_lab4_v1_1_live.py"])],
}


def run(args: list[str], cwd: Path, env: dict[str, str] | None = None, timeout: int = 180) -> dict:
    process = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=timeout)
    output = process.stdout + "\n" + process.stderr
    # Retain short, sanitized evidence only. Commands here never open credentials.
    return {"command": args[1:], "exit_code": process.returncode, "output_tail": output[-1200:]}


def manifest_check(archive: ZipFile) -> dict:
    names = archive.namelist()
    if archive.testzip() is not None:
        raise AssertionError("ZIP CRC failure")
    lines = archive.read("ARCHIVE_MANIFEST.txt").decode("utf-8").splitlines()
    records = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match:
            records[match.group(2)] = match.group(1)
    if set(records) != set(names) - {"ARCHIVE_MANIFEST.txt"}:
        raise AssertionError("manifest member list differs from ZIP")
    bad = [name for name, digest in records.items() if sha256(archive.read(name)).hexdigest() != digest]
    if bad:
        raise AssertionError(f"member SHA mismatch: {bad}")
    if any(Path(name).is_absolute() or ".." in Path(name).parts for name in names):
        raise AssertionError("unsafe ZIP path")
    unwanted = [name for name in names if name.lower().endswith((".sqlite", ".sqlite3", ".db"))
                or name == ".env" or "/.env" in name or name.startswith(".git/")
                or "/.git/" in name or "/.venv/" in name or "__pycache__" in name]
    secret_pattern = re.compile(rb"(?:sk-or-v1-|github_pat_)[A-Za-z0-9_\-]{20,}")
    secret_files = [name for name in names if name.endswith((".py", ".md", ".json", ".txt", ".yml", ".csv"))
                    and secret_pattern.search(archive.read(name))]
    return {"member_count": len(records), "crc_ok": True, "sha256_ok": True,
            "unwanted_names": unwanted, "credential_pattern_files": secret_files,
            "manifest_header": lines[:len(lines) - len(records)]}


def main() -> None:
    output = {"python": sys.version.split()[0], "releases": {}, "workspace": None}
    outside = Path(tempfile.mkdtemp(prefix="ResearchRadarFinalAudit-"))
    output["workspace"] = str(outside)
    for tag in TAGS:
        meta = json.loads(subprocess.check_output([str(GH), "release", "view", tag, "--json",
                                                   "tagName,url,assets,isDraft,isPrerelease"],
                                                  cwd=ROOT, text=True, encoding="utf-8"))
        record = {"url": meta["url"], "assets": [], "tag_commit": None, "archive_checks": {}, "runs": []}
        record["tag_commit"] = subprocess.check_output(["git", "rev-list", "-n", "1", tag],
                                                        cwd=ROOT, text=True).strip()
        local_dir = DOWNLOADS / tag
        for asset in meta["assets"]:
            path = local_dir / asset["name"]
            digest = sha256(path.read_bytes()).hexdigest()
            matched = asset.get("digest") == "sha256:" + digest
            entry = {"name": asset["name"], "sha256": digest, "remote_digest_match": matched,
                     "size": path.stat().st_size}
            if not matched:
                raise AssertionError(f"Release digest mismatch: {tag}/{asset['name']}")
            if path.suffix == ".zip":
                with ZipFile(path) as archive:
                    entry["archive"] = manifest_check(archive)
                if entry["archive"]["unwanted_names"] or entry["archive"]["credential_pattern_files"]:
                    raise AssertionError(f"unsafe archive member: {tag}/{asset['name']}")
            record["assets"].append(entry)
        audit_path = next(local_dir.glob("*audit.zip"))
        target = outside / tag
        target.mkdir()
        with ZipFile(audit_path) as archive:
            archive.extractall(target)
        if any((p / ".git").exists() for p in (target, target.parent)):
            raise AssertionError("Git directory present in audit extraction hierarchy")
        (target / "run_output").mkdir(exist_ok=True)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(target / "src")
        env["PYTHONNOUSERSITE"] = "1"
        import_result = run([sys.executable, "-c", "import researchradar; print(researchradar.__file__)"], target, env)
        if import_result["exit_code"] or str(target / "src") not in import_result["output_tail"]:
            raise AssertionError(f"wrong import origin: {tag}")
        record["import"] = import_result
        for label, args in COMMANDS[tag]:
            result = run([sys.executable] + args, target, env, timeout=300)
            result["label"] = label
            record["runs"].append(result)
        output["releases"][tag] = record
        print(tag, "assets", len(record["assets"]), "runs", [(r["label"], r["exit_code"]) for r in record["runs"]])
    raw = ROOT / "run_output/final_audit_execution_raw.json"
    raw.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    clean = json.dumps(output, ensure_ascii=False, indent=2)
    clean = clean.replace(str(outside), "<AUDIT_EXTRACTION>")
    clean = clean.replace(str(Path.home()), "<USER_HOME>")
    dest = ROOT / "final_audit/protocol.json"
    dest.write_text(clean + "\n", encoding="utf-8")
    print(dest)


if __name__ == "__main__":
    main()
