"""Render the reviewed DOCX report content to a standalone PDF."""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "deliverables/ResearchRadar_MAS_Reliability_Assessment.docx"
TARGET = SOURCE.with_suffix(".pdf")
FIG = ROOT / "deliverables/figures"
pdfmetrics.registerFont(TTFont("TimesRU", "C:/Windows/Fonts/times.ttf"))
pdfmetrics.registerFont(TTFont("TimesRUBold", "C:/Windows/Fonts/timesbd.ttf"))
styles = {
    "Normal": ParagraphStyle("NormalRU", fontName="TimesRU", fontSize=9.8,
                             leading=12.2, spaceAfter=5, alignment=TA_JUSTIFY),
    "Title": ParagraphStyle("TitleRU", fontName="TimesRUBold", fontSize=16.5,
                            leading=20, alignment=TA_CENTER, spaceAfter=18),
    "Heading 1": ParagraphStyle("HeadingRU", fontName="TimesRUBold", fontSize=13,
                                leading=16, spaceBefore=11, spaceAfter=7,
                                keepWithNext=True),
    "Heading 2": ParagraphStyle("SubheadingRU", fontName="TimesRUBold", fontSize=11,
                                leading=14, spaceBefore=10, spaceAfter=5,
                                keepWithNext=True),
    "Caption": ParagraphStyle("CaptionRU", fontName="TimesRU", fontSize=9,
                              leading=12, alignment=TA_CENTER, spaceAfter=8),
}
source = Document(SOURCE)
story = []
figure_index = 0
for child in source.element.body.iterchildren():
    if child.tag == qn("w:p"):
        item = DocxParagraph(child, source)
        if child.xpath('.//w:br[@w:type="page"]'):
            story.append(PageBreak())
            continue
        if child.xpath('.//w:drawing'):
            figures = [FIG / "trust_boundaries.png", FIG / "policy_violations.png"]
            if figure_index < len(figures):
                img = Image(str(figures[figure_index]), width=15.6*cm,
                            height=(15.6*cm * (460/1200 if figure_index == 0 else 700/1200)))
                story.append(img)
                figure_index += 1
            continue
        if not item.text.strip():
            continue
        style = styles.get(item.style.name, styles["Normal"])
        if item.text.startswith("Рисунок "):
            style = styles["Caption"]
        story.append(Paragraph(escape(item.text), style))
    elif child.tag == qn("w:tbl"):
        item = DocxTable(child, source)
        rows = [[Paragraph(escape(cell.text), ParagraphStyle("cell", fontName="TimesRU",
                            fontSize=7.5, leading=9.2)) for cell in row.cells]
                for row in item.rows]
        table = Table(rows, colWidths=[5.2*cm, 2.8*cm, 2.8*cm, 2.8*cm, 2.8*cm],
                      repeatRows=1, hAlign="CENTER")
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#64748b")),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f2f1")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 5),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                                   ("TOPPADDING", (0, 0), (-1, -1), 4),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        story.append(table)
        story.append(Spacer(1, 9))


def footer(canvas, document):
    canvas.setFont("TimesRU", 8)
    canvas.drawCentredString(10.5*cm, 1.25*cm,
                             f"ResearchRadar MAS · 2026                                      {document.page}")


pdf = SimpleDocTemplate(str(TARGET), pagesize=(21*cm, 29.7*cm),
                        leftMargin=2.25*cm, rightMargin=2.15*cm,
                        topMargin=2*cm, bottomMargin=1.8*cm,
                        title="Устойчивость многоагентной исследовательской системы",
                        author="Коротаев Андрей Дмитриевич")
pdf.build(story, onFirstPage=footer, onLaterPages=footer)
print(TARGET)
