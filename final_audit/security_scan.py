"""Scan tracked files and published assets without displaying potential secrets."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "run_output/final_audit_downloads"
TAGS = ("lab1-v1.2", "lab2-v1.1", "lab3-v1.1", "lab4-v1.1")
TOKEN = re.compile(rb"(?:sk-or-v1-|github_pat_)[A-Za-z0-9_\-]{20,}")
PRIVATE_PATH = re.compile(rb"[A-Za-z]:\\Users\\[A-Za-z0-9_.-]+\\")
BAD_NAME = re.compile(r"(^|/)(?:\.env|\.git|\.venv|__pycache__)(?:/|$)|\.(?:sqlite|sqlite3|db|pyc)$", re.I)


def scan(items: list[tuple[str, bytes]]) -> dict:
    return {
        "files": len(items),
        "credential_pattern_files": [name for name, data in items if TOKEN.search(data)],
        "unwanted_names": [name for name, _ in items if BAD_NAME.search(name) and name != ".env.example"],
        "absolute_user_path_files": [name for name, data in items if PRIVATE_PATH.search(data)],
    }


def main() -> None:
    names = [name for name in subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
             .decode("utf-8").split("\0") if name]
    tracked = scan([(name, (ROOT / name).read_bytes()) for name in names if (ROOT / name).is_file()])
    output = {"tracked": tracked, "releases": {}}
    for tag in TAGS:
        folder = DOWNLOADS / tag
        assets = scan([(path.name, path.read_bytes()) for path in folder.iterdir() if path.is_file()])
        archives = {}
        for path in folder.glob("*.zip"):
            with ZipFile(path) as archive:
                archives[path.name] = scan([(name, archive.read(name)) for name in archive.namelist()])
        output["releases"][tag] = {"asset_files": assets, "archives": archives}
        print(tag, "assets", assets["files"], "archive_members", [x["files"] for x in archives.values()],
              "credential_matches", sum(len(x["credential_pattern_files"]) for x in archives.values()))
    print("tracked", tracked["files"], "credential_matches", len(tracked["credential_pattern_files"]))
    (ROOT / "final_audit/security_scan.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
