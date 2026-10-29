"""Render the same report body as the DOCX with vector SVG figures."""
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.document import Document as DocClass
from docx.table import Table as DocTable
from docx.text.paragraph import Paragraph as DocParagraph
from docx.oxml.ns import qn
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, PageBreak,
                                Table, TableStyle, KeepTogether)
from svglib.svglib import svg2rlg

ROOT = Path(__file__).resolve().parents[1]
DOCX = ROOT / "deliverables/ResearchRadar_MAS_Architecture.docx"
PDF = ROOT / "deliverables/ResearchRadar_MAS_Architecture.pdf"
FONT_DIR = Path("C:/Windows/Fonts")
pdfmetrics.registerFont(TTFont("TimesRU", str(FONT_DIR / "times.ttf")))
pdfmetrics.registerFont(TTFont("TimesRU-Bold", str(FONT_DIR / "timesbd.ttf")))
pdfmetrics.registerFont(TTFont("Arial", str(FONT_DIR / "arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Bold", str(FONT_DIR / "arialbd.ttf")))
pdfmetrics.registerFontFamily("TimesRU", normal="TimesRU", bold="TimesRU-Bold")
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold")

styles = {
    "body": ParagraphStyle("body", fontName="TimesRU", fontSize=11, leading=14,
                           spaceAfter=7, textColor=colors.black),
    "title": ParagraphStyle("title", fontName="TimesRU-Bold", fontSize=17, leading=21,
                            alignment=TA_CENTER, spaceAfter=24),
    "center": ParagraphStyle("center", fontName="TimesRU", fontSize=11, leading=15,
                             alignment=TA_CENTER, spaceAfter=10),
    "heading": ParagraphStyle("heading", fontName="TimesRU-Bold", fontSize=14,
                              leading=18, spaceBefore=14, spaceAfter=8,
                              keepWithNext=True),
    "caption": ParagraphStyle("caption", fontName="TimesRU", fontSize=10,
                              leading=13, alignment=TA_CENTER, spaceAfter=14),
    "table": ParagraphStyle("table", fontName="TimesRU", fontSize=8.5,
                            leading=10, spaceAfter=0),
}


def figure(path: Path):
    drawing = svg2rlg(str(path))
    if drawing is None:
        raise RuntimeError(f"SVG failed: {path}")
    scale = min(1, 450 / drawing.width)
    drawing.scale(scale, scale)
    drawing.width *= scale
    drawing.height *= scale
    return drawing


def table_flowable(t: DocTable):
    data = [[Paragraph(escape(cell.text), styles["table"]) for cell in row.cells]
            for row in t.rows]
    widths = [82, 155, 220] if len(data[0]) == 3 else [115, 342]
    flow = Table(data, colWidths=widths, repeatRows=1, hAlign="CENTER")
    flow.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return KeepTogether(flow)


def main():
    source = Document(DOCX)
    story = []
    for child in source.element.body.iterchildren():
        if child.tag == qn("w:p"):
            p = DocParagraph(child, source)
            if 'w:type="page"' in child.xml:
                story.append(PageBreak())
                continue
            text = p.text.strip()
            if not text:
                story.append(Spacer(1, 10))
                continue
            if text == "FIGURE_ROLES":
                story.append(figure(ROOT / "docs/diagrams/roles.svg"))
                continue
            if text == "FIGURE_COMMUNICATION":
                story.append(figure(ROOT / "docs/diagrams/communication.svg"))
                continue
            style_name = p.style.name
            key = ("title" if style_name == "Title" else
                   "heading" if style_name.startswith("Heading") else
                   "caption" if text.startswith("Рисунок ") else
                   "center" if p.alignment == 1 else "body")
            story.append(Paragraph(escape(text), styles[key]))
        elif child.tag == qn("w:tbl"):
            story.append(table_flowable(DocTable(child, source)))
    doc = SimpleDocTemplate(str(PDF), pagesize=A4,
                            leftMargin=71, rightMargin=62,
                            topMargin=59, bottomMargin=57,
                            title="Проектирование и архитектура ResearchRadar MAS",
                            author="Коротаев Андрей Дмитриевич")
    doc.build(story)
    print(PDF)


if __name__ == "__main__":
    main()
