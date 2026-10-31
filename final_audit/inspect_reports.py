"""Inspect published report structure and text; visual review is recorded separately."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "run_output/final_audit_downloads"
TAGS = ("lab1-v1.2", "lab2-v1.1", "lab3-v1.1", "lab4-v1.1")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def main() -> None:
    output = {}
    for tag in TAGS:
        folder = DOWNLOADS / tag
        pdf = next(folder.glob("*.pdf"))
        docx = next(folder.glob("*.docx"))
        pages = PdfReader(pdf).pages
        pdf_text = "\n".join(page.extract_text() or "" for page in pages)
        with ZipFile(docx) as archive:
            assert archive.testzip() is None
            root = ET.fromstring(archive.read("word/document.xml"))
            docx_text = " ".join(node.text or "" for node in root.iter(W + "t"))
            images = [name for name in archive.namelist() if name.startswith("word/media/")]
        expected = ("Коротаев Андрей Дмитриевич", "Б24-507", "2026")
        forbidden = ("лабораторная работа", "согласно методичке", "по требованию преподавателя")
        pdftokens = set(re.findall(r"\w+", pdf_text.lower()))
        docxtokens = set(re.findall(r"\w+", docx_text.lower()))
        record = {
            "pdf": pdf.name, "docx": docx.name, "pages": len(pages),
            "pdf_page_text_chars": [len(page.extract_text() or "") for page in pages],
            "docx_text_chars": len(docx_text), "docx_media": images,
            "expected_in_pdf": {term: term in pdf_text for term in expected},
            "expected_in_docx": {term: term in docx_text for term in expected},
            "forbidden_in_pdf": {term: term in pdf_text.lower() for term in forbidden},
            "forbidden_in_docx": {term: term in docx_text.lower() for term in forbidden},
            "docx_to_pdf_vocabulary_recall": round(len(docxtokens & pdftokens) / len(docxtokens), 3),
            "visual_review": "all PDF pages rendered and contact sheets inspected; no evident clipping or overlap",
            "independent_docx_render": "not_available_no_libreoffice",
        }
        output[tag] = record
        print(tag, record)
    (ROOT / "final_audit/report_inspection.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
