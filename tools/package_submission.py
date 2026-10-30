"""Build separate submission and reproducible audit archives from explicit paths."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables"
VERSION = "v1.2"
BASE = [
    ".env.example", ".github/workflows/tests.yml", ".gitignore", "AGENTS.md",
    "README.md", "pyproject.toml", "submission_manifest.md",
    "deliverables/ResearchRadar_MAS_Architecture.docx",
    "deliverables/ResearchRadar_MAS_Architecture.pdf",
]
FOLDERS = ("src/researchradar", "tests", "docs", "tools", "project_guide")
EXCLUDED_PARTS = {"__pycache__", "tmp", ".git", "run_output"}


def selected(audit: bool) -> list[Path]:
    paths = [ROOT / name for name in BASE]
    for folder in FOLDERS + (("audit_evidence",) if audit else ()):
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file()
                     and not any(part in EXCLUDED_PARTS or part.endswith(".egg-info")
                                 for part in p.relative_to(ROOT).parts)
                     and p.suffix not in {".pyc", ".log", ".db", ".sqlite3"})
    result = sorted(set(paths))
    for path in result:
        relative = path.relative_to(ROOT)
        if (not path.is_file() or any(part in EXCLUDED_PARTS or part.endswith(".egg-info")
                                      for part in relative.parts)
                or path.suffix in {".pyc", ".log", ".db", ".sqlite3"}
                or path.name == ".env"):
            raise RuntimeError(f"unexpected file: {relative}")
        if path.suffix in {".py", ".md", ".txt", ".yml", ".ps1", ".json"}:
            content = path.read_text(encoding="utf-8")
            if ("sk-" + "or-v1-") in content or ("github" + "_pat_") in content:
                raise RuntimeError(f"credential-like text: {relative}")
    return result


def build(audit: bool) -> Path:
    kind = "audit" if audit else "submission"
    output = OUT / f"ResearchRadar_MAS_lab1_{VERSION}_{kind}.zip"
    paths = selected(audit)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest = [f"ResearchRadar MAS {VERSION} {kind}", f"Commit: {commit}",
                "Release: https://github.com/KAndyD/ResearchRadar_MAS/releases/tag/lab1-v1.2",
                "SHA-256 of archive members:"]
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in paths:
            name = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            archive.writestr(name, data)
            manifest.append(f"{sha256(data).hexdigest()}  {name}")
        archive.writestr("ARCHIVE_MANIFEST.txt", "\n".join(manifest) + "\n")
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError(f"corrupted archive: {output}")
        expected = {p.relative_to(ROOT).as_posix() for p in paths} | {"ARCHIVE_MANIFEST.txt"}
        if set(archive.namelist()) != expected:
            raise RuntimeError(f"unexpected archive inventory: {output}")
    print(output, len(paths), "files, SHA-256", sha256(output.read_bytes()).hexdigest())
    return output


if __name__ == "__main__":
    build(False)
    build(True)
