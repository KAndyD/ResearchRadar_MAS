"""Compare published archive members with exact Git blobs at each canonical tag."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
TAGS = ("lab1-v1.2", "lab2-v1.1", "lab3-v1.1", "lab4-v1.1")


def read_blobs(specs: list[str]) -> dict[str, bytes | None]:
    process = subprocess.run(["git", "cat-file", "--batch"], cwd=ROOT,
                             input=("\n".join(specs) + "\n").encode("utf-8"),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    data, offset, out = process.stdout, 0, {}
    for spec in specs:
        end = data.index(b"\n", offset)
        header = data[offset:end].decode("utf-8", errors="replace")
        offset = end + 1
        if header.endswith(" missing"):
            out[spec] = None
            continue
        _, kind, size_text = header.rsplit(" ", 2)
        assert kind == "blob"
        size = int(size_text)
        out[spec] = data[offset:offset + size]
        offset += size + 1
    return out


def main() -> None:
    result = {}
    for tag in TAGS:
        path = next((ROOT / "run_output/final_audit_downloads" / tag).glob("*audit.zip"))
        with ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name != "ARCHIVE_MANIFEST.txt"]
            specs = [f"{tag}:{name}" for name in names]
            blobs = read_blobs(specs)
            missing = [name for name in names if blobs[f"{tag}:{name}"] is None]
            different = [name for name in names if blobs[f"{tag}:{name}"] is not None
                         and archive.read(name) != blobs[f"{tag}:{name}"]]
            newline_only = [name for name in different if
                            archive.read(name).replace(b"\r\n", b"\n") ==
                            blobs[f"{tag}:{name}"].replace(b"\r\n", b"\n")]
            material = [name for name in different if name not in newline_only]
        result[tag] = {"checked": len(names), "missing_from_tag": missing,
                       "newline_only_difference": newline_only,
                       "material_difference": material}
        print(tag, "checked", len(names), "missing", len(missing),
              "newline_only", len(newline_only), "material", len(material))
        if missing or material:
            print("sample", (missing + material)[:10])
    (ROOT / "final_audit/tag_sync.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
