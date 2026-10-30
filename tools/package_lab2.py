"""Package reproducible Lab 2 submission and audit artifacts."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables"
BASE = (
    ".env.example", ".github/workflows/tests.yml", "AGENTS.md", "README.md",
    "pyproject.toml", "submission_manifest_lab2.md",
    "deliverables/ResearchRadar_MAS_Task_Allocation.pdf",
)
FOLDERS = ("src/researchradar", "tests", "data", "experiments/results",
           "docs/diagrams", "project_guide")
DOCS = ("docs/architecture.md", "docs/decisions.md", "docs/source_policy.md",
        "docs/api_validation.md", "docs/test-status.md", "docs/progress.md",
        "docs/handoff.md")
SCRIPTS = ("tools/run_experiments.py", "tools/build_lab2_report.py",
           "tools/build_lab2_pdf.py", "tools/embed_lab2_vectors.ps1",
           "tools/requirements-report.txt")
EXCLUDED = {"__pycache__", ".git", "tmp", "run_output"}
BAD_SUFFIX = {".pyc", ".log", ".db", ".sqlite3"}


def selected(audit: bool) -> list[Path]:
    names = BASE + DOCS + SCRIPTS
    if audit:
        names += ("deliverables/ResearchRadar_MAS_Task_Allocation.docx",)
    paths = [ROOT / name for name in names]
    for folder in FOLDERS + (("audit_evidence",) if audit else ()):
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file())
    result = sorted(set(paths))
    for path in result:
        relative = path.relative_to(ROOT)
        if (not path.is_file() or any(part in EXCLUDED or part.endswith(".egg-info")
                                      for part in relative.parts)
                or path.suffix in BAD_SUFFIX or path.name == ".env"):
            raise RuntimeError(f"unwanted member: {relative}")
        if path.suffix in {".py", ".md", ".txt", ".yml", ".ps1", ".json", ".csv"}:
            content = path.read_text(encoding="utf-8")
            if ("sk-" + "or-v1-") in content or ("github" + "_pat_") in content:
                raise RuntimeError(f"credential-like text in {relative}")
    return result


def build(audit: bool) -> Path:
    kind = "audit" if audit else "submission"
    output = OUT / f"ResearchRadar_MAS_lab2_v1.0_{kind}.zip"
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                     cwd=ROOT, text=True).strip()
    manifest = [f"ResearchRadar MAS lab2-v1.0 {kind}", f"Commit: {commit}",
                "Release: https://github.com/KAndyD/ResearchRadar_MAS/releases/tag/lab2-v1.0",
                "SHA-256 of archive members:"]
    paths = selected(audit)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in paths:
            name = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            archive.writestr(name, data)
            manifest.append(f"{sha256(data).hexdigest()}  {name}")
        archive.writestr("ARCHIVE_MANIFEST.txt", "\n".join(manifest) + "\n")
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {p.relative_to(ROOT).as_posix() for p in paths} | {
            "ARCHIVE_MANIFEST.txt"}
        for line in manifest[4:]:
            digest, name = line.split("  ", 1)
            assert sha256(archive.read(name)).hexdigest() == digest
    print(output, len(paths), "files, SHA-256", sha256(output.read_bytes()).hexdigest())
    return output


if __name__ == "__main__":
    build(False)
    build(True)
