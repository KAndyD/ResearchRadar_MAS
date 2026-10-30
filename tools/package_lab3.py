"""Build complete lab3 submission and audit ZIPs with verified SHA-256 manifests."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables"
VERSION = "lab3-v1.0"
BASE = (
    ".env.example", ".github/workflows/tests.yml", "AGENTS.md", "README.md",
    "pyproject.toml", "submission_manifest_lab3.md",
    "deliverables/ResearchRadar_MAS_Resource_Negotiation.pdf",
)
FOLDERS = ("src/researchradar", "tests", "data", "experiments", "docs", "tools")
EXCLUDED = {"__pycache__", ".git", "tmp", "run_output", ".venv"}
BAD_SUFFIX = {".pyc", ".log", ".db", ".sqlite3", ".zip"}


def selected(audit: bool) -> list[Path]:
    names = BASE
    if audit:
        names += ("deliverables/ResearchRadar_MAS_Resource_Negotiation.docx",
                  "project_guide/Лабораторные-МАС.pdf")
    paths = [ROOT / name for name in names]
    for folder in FOLDERS + (("audit_evidence",) if audit else ()):
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file()
                     and not any(part in EXCLUDED or part.endswith(".egg-info")
                                 for part in p.relative_to(ROOT).parts)
                     and p.suffix not in BAD_SUFFIX)
    result = sorted(set(paths))
    for path in result:
        relative = path.relative_to(ROOT)
        if (not path.is_file() or any(part in EXCLUDED or part.endswith(".egg-info")
                                      for part in relative.parts)
                or path.suffix in BAD_SUFFIX or path.name == ".env"):
            raise RuntimeError(f"unwanted member: {relative}")
        if path.suffix in {".py", ".md", ".txt", ".yml", ".ps1", ".json", ".csv"}:
            value = path.read_text(encoding="utf-8")
            if ("sk-" + "or-v1-") in value or ("github" + "_pat_") in value:
                raise RuntimeError(f"credential-like text: {relative}")
    return result


def build(audit: bool) -> Path:
    kind = "audit" if audit else "submission"
    output = OUT / f"ResearchRadar_MAS_lab3_v1.0_{kind}.zip"
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                     cwd=ROOT, text=True).strip()
    experiment = json.loads((ROOT / "experiments/lab3/results/metadata.json").read_text(encoding="utf-8"))
    manifest = [f"ResearchRadar MAS {VERSION} {kind}",
                f"Archive source commit: {commit}",
                f"Experiment code commit: {experiment['code_commit_at_run'] or 'unknown'}",
                f"Experiment commit source: {experiment['code_commit_source']}",
                f"Frozen data SHA-256: {experiment['frozen_sha256']}",
                f"Release: https://github.com/KAndyD/ResearchRadar_MAS/releases/tag/{VERSION}",
                "SHA-256 of archive members:"]
    paths = selected(audit)
    member_lines = []
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in paths:
            name = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            archive.writestr(name, data)
            member_lines.append(f"{sha256(data).hexdigest()}  {name}")
        archive.writestr("ARCHIVE_MANIFEST.txt", "\n".join(manifest + member_lines) + "\n")
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("archive member damaged")
        expected = {p.relative_to(ROOT).as_posix() for p in paths} | {"ARCHIVE_MANIFEST.txt"}
        if set(archive.namelist()) != expected:
            raise RuntimeError("archive inventory changed")
        for line in member_lines:
            digest, name = line.split("  ", 1)
            if sha256(archive.read(name)).hexdigest() != digest:
                raise RuntimeError(f"member checksum mismatch: {name}")
    print(output, len(paths), "files, SHA-256", sha256(output.read_bytes()).hexdigest())
    return output


if __name__ == "__main__":
    build(False)
    build(True)
