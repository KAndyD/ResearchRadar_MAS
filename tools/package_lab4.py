"""Create self-contained submission and audit ZIPs with member hashes."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables"
BASE = (".env.example", ".github/workflows/tests.yml", "AGENTS.md", "README.md",
        "pyproject.toml", "submission_manifest_lab4_v1.0.md",
        "deliverables/ResearchRadar_MAS_Reliability_Assessment.pdf",
        "deliverables/ResearchRadar_MAS_Reliability_Assessment.docx")
FOLDERS = ("src/researchradar", "tests", "data", "experiments", "docs", "tools",
           "deliverables/figures")
EXCLUDED = {"__pycache__", ".git", "tmp", "run_output", ".venv"}
BAD_SUFFIX = {".pyc", ".log", ".db", ".sqlite3"}


def selected(audit: bool) -> list[Path]:
    paths = [ROOT / name for name in BASE]
    if audit:
        paths.append(ROOT / "project_guide/Лабораторные-МАС.pdf")
    for folder in FOLDERS + (("audit_evidence",) if audit else ()):
        paths.extend(path for path in (ROOT / folder).rglob("*") if path.is_file()
                     and not any(part in EXCLUDED or part.endswith(".egg-info")
                                 for part in path.relative_to(ROOT).parts)
                     and path.suffix not in BAD_SUFFIX)
    result = sorted(set(paths))
    for path in result:
        rel = path.relative_to(ROOT)
        if (not path.is_file() or any(part in EXCLUDED or part.endswith(".egg-info")
                                      for part in rel.parts)
                or path.suffix in BAD_SUFFIX or path.name == ".env"):
            raise RuntimeError(f"unwanted member: {rel}")
        if path.suffix in {".py", ".md", ".txt", ".yml", ".ps1", ".json", ".csv", ".svg"}:
            value = path.read_text(encoding="utf-8")
            if ("sk-" + "or-v1-") in value or ("github" + "_pat_") in value:
                raise RuntimeError(f"credential-like text: {rel}")
    return result


def build(audit: bool) -> Path:
    OUT.mkdir(exist_ok=True)
    kind = "audit" if audit else "submission"
    target = OUT / f"ResearchRadar_MAS_lab4_v1.0_{kind}.zip"
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                         text=True, timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        commit = "unavailable_no_git"
    exp = json.loads((ROOT / "experiments/lab4/results/metadata.json").read_text(encoding="utf-8"))
    header = [f"ResearchRadar MAS lab4-v1.0 {kind}",
              f"Archive source commit: {commit}",
              f"Protected experiment code commit: {exp['protected_code_commit']}",
              f"Historical tag: {exp['baseline_tag']}",
              f"Historical source ZIP SHA-256: {exp['baseline_sha256']}",
              "Archive member SHA-256:"]
    paths = selected(audit)
    records = []
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in paths:
            name = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            archive.writestr(name, data)
            records.append(f"{sha256(data).hexdigest()}  {name}")
        archive.writestr("ARCHIVE_MANIFEST.txt", "\n".join(header + records) + "\n")
    with ZipFile(target) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {p.relative_to(ROOT).as_posix() for p in paths} | {
            "ARCHIVE_MANIFEST.txt"}
        for line in records:
            digest, name = line.split("  ", 1)
            assert sha256(archive.read(name)).hexdigest() == digest
    print(f"{target} {len(paths)} files SHA-256 {sha256(target.read_bytes()).hexdigest()}")
    return target


if __name__ == "__main__":
    build(False)
    build(True)
