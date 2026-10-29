"""Create a source-and-report submission archive from an explicit allowlist."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "deliverables/ResearchRadar_MAS_lab1_v1.1_submission.zip"
FILES = [ROOT / name for name in (
    ".env.example", ".github/workflows/tests.yml", "AGENTS.md", "README.md",
    "pyproject.toml", "submission_manifest.md",
    "deliverables/ResearchRadar_MAS_Architecture.docx",
    "deliverables/ResearchRadar_MAS_Architecture.pdf",
)]
for folder in ("src/researchradar", "tests", "docs", "tools", "project_guide"):
    FILES.extend(p for p in (ROOT / folder).rglob("*") if p.is_file()
                 and "__pycache__" not in p.parts and p.suffix != ".pyc")

selected = sorted(set(FILES))
for path in selected:
    relative = path.relative_to(ROOT)
    if any(part in {"__pycache__", "tmp", ".git", "run_output"} or
           part.endswith(".egg-info") for part in relative.parts):
        raise RuntimeError(f"unexpected generated path: {relative}")
    if path.suffix in {".pyc", ".log"} or path.name == ".env":
        raise RuntimeError(f"unexpected private file: {relative}")
    if not path.exists():
        raise FileNotFoundError(relative)
    if path.suffix in {".py", ".md", ".txt", ".yml", ".ps1"}:
        text = path.read_text(encoding="utf-8")
        if ("sk-" + "or-v1-") in text or ("github" + "_pat_") in text:
            raise RuntimeError(f"credential-like text: {relative}")

with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as archive:
    for path in selected:
        archive.write(path, path.relative_to(ROOT).as_posix())
print(OUTPUT, len(selected), "files")
