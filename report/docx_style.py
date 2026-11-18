"""Formatting helpers that enforce the AML Lab IEEE template rules.

Rules (from AML_Lab_Project_Research_Paper_Format.docx):
  Times New Roman everywhere | Title 14 pt bold centred | Authors/affiliation 10 pt centred
  Section headings 11 pt bold | Subsection headings 10 pt bold | Body 10 pt, single spacing
  Abstract 9-10 pt | Figure/Table captions 9 pt centred | References 9-10 pt
  Margins >= 0.75 inch on all sides
"""

from __future__ import annotations

import re

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

FONT = "Times New Roman"
BLACK = RGBColor(0, 0, 0)


def set_run_font(run, size=10, bold=None, italic=None, sub=False, sup=False, highlight=None):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.color.rgb = BLACK
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if sub:
        run.font.subscript = True
    if sup:
        run.font.superscript = True
    if highlight is not None:
        run.font.highlight_color = highlight
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for k in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(k), FONT)
    return run


def style_document(doc: Document):
    """Make every style Times New Roman, black, single spaced; set Letter page + 0.75" margins."""
    for st in doc.styles:
        try:
            f = st.font
        except AttributeError:
            continue
        f.name = FONT
        f.color.rgb = BLACK
        rpr = st.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.insert(0, rfonts)
        for k in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rfonts.set(qn(k), FONT)
        for k in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
            if rfonts.get(qn(k)) is not None:
                del rfonts.attrib[qn(k)]
    normal = doc.styles["Normal"]
    normal.font.size = Pt(10)
    pf = normal.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    pf.space_before = Pt(0)
    pf.space_after = Pt(3)
    # document defaults (docDefaults) -> Times New Roman as well
    rpr_default = doc.styles.element.find(qn("w:docDefaults"))
    if rpr_default is not None:
        for rf in rpr_default.iter(qn("w:rFonts")):
            for k in list(rf.attrib):
                del rf.attrib[k]
            for k in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
                rf.set(qn(k), FONT)
    # heading styles used for navigation pane
    for name, size in (("Heading 1", 11), ("Heading 2", 10)):
        h = doc.styles[name]
        h.font.size = Pt(size)
        h.font.bold = True
        h.font.italic = False
        h.font.color.rgb = BLACK
        h.paragraph_format.space_before = Pt(8 if size == 11 else 5)
        h.paragraph_format.space_after = Pt(3)
        h.paragraph_format.keep_with_next = True
        h.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Inches(0.75))
    sec.header_distance = Inches(0.4)
    sec.footer_distance = Inches(0.4)


# ---------------------------------------------------------------------------- inline markup
# Supported inline markup inside text strings:
#   **bold**   *italic*   _{subscript}   ^{superscript}   [[HL: text]] yellow-highlighted placeholder
TOKEN = re.compile(r"(\*\*.+?\*\*|\*.+?\*|_\{.+?\}|\^\{.+?\}|\[\[HL:.+?\]\])")


def add_rich(par, text, size=10, bold=False, italic=False):
    from docx.enum.text import WD_COLOR_INDEX
    for part in TOKEN.split(text):
        if not part:
            continue
        if part.startswith("**"):
            set_run_font(par.add_run(part[2:-2]), size, bold=True, italic=italic)
        elif part.startswith("*") and len(part) > 1:
            set_run_font(par.add_run(part[1:-1]), size, bold=bold, italic=True)
        elif part.startswith("_{"):
            set_run_font(par.add_run(part[2:-1]), size, bold=bold, italic=italic, sub=True)
        elif part.startswith("^{"):
            set_run_font(par.add_run(part[2:-1]), size, bold=bold, italic=italic, sup=True)
        elif part.startswith("[[HL:"):
            set_run_font(par.add_run(part[5:-2].strip()), size, bold=bold, italic=italic,
                         highlight=WD_COLOR_INDEX.YELLOW)
        else:
            set_run_font(par.add_run(part), size, bold=bold, italic=italic)
    return par


def para(doc, text="", size=10, align="justify", bold=False, italic=False, space_after=3,
         space_before=0, indent_first=0.0, left_indent=0.0, keep_next=False):
    p = doc.add_paragraph()
    p.alignment = {"justify": WD_ALIGN_PARAGRAPH.JUSTIFY, "center": WD_ALIGN_PARAGRAPH.CENTER,
                   "left": WD_ALIGN_PARAGRAPH.LEFT}[align]
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(space_before)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    if indent_first:
        pf.first_line_indent = Inches(indent_first)
    if left_indent:
        pf.left_indent = Inches(left_indent)
    pf.keep_with_next = keep_next
    add_rich(p, text, size=size, bold=bold, italic=italic)
    return p


def heading(doc, text, level=1):
    p = doc.add_paragraph(style="Heading 1" if level == 1 else "Heading 2")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_run_font(p.add_run(text), 11 if level == 1 else 10, bold=True, italic=False)
    return p


_bullet_counter = {"n": 0}


def bullet(doc, text, size=10, symbol="•"):
    """Bullet with hanging indent (bullet character U+2022 exists in Times New Roman)."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf = p.paragraph_format
    pf.left_indent = Inches(0.25)
    pf.first_line_indent = Inches(-0.15)
    pf.space_after = Pt(1.5)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    add_rich(p, f"{symbol}  " + text, size=size)
    return p


def caption(doc, text, space_after=6, space_before=2, keep_next=False):
    p = para(doc, text, size=9, align="center", space_after=space_after, space_before=space_before,
             keep_next=keep_next)
    return p


def _cell_margins(table, top=20, bottom=20, left=60, right=60):
    tblPr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for side, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:w"), str(val))
        e.set(qn("w:type"), "dxa")
        mar.append(e)
    tblPr.append(mar)


def _borders(table, inner=True):
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{side}")
        if side in ("left", "right", "insideV") or (side == "insideH" and not inner):
            e.set(qn("w:val"), "nil")
        else:
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), "4")
            e.set(qn("w:color"), "000000")
        b.append(e)
    tblPr.append(b)


def table(doc, header, rows, widths_in, size=9, align_cols=None, bold_header=True, inner_h=False,
          header_shade=True):
    """IEEE-style table: horizontal rules, 9 pt Times New Roman, fixed column widths."""
    t = doc.add_table(rows=1 + len(rows), cols=len(header))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    _borders(t, inner=inner_h)
    _cell_margins(t)
    for column, width in zip(t.columns, widths_in, strict=True):
        column.width = Inches(width)
    align_cols = align_cols or ["left"] * len(header)
    amap = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right": WD_ALIGN_PARAGRAPH.RIGHT}
    for r_i, row in enumerate([header] + rows):
        tr = t.rows[r_i]
        trPr = tr._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        trPr.append(cant)
        if r_i == 0:
            th = OxmlElement("w:tblHeader")
            trPr.append(th)
        for c_i, val in enumerate(row):
            cell = tr.cells[c_i]
            cell.width = Inches(widths_in[c_i])
            if r_i == 0 and header_shade:
                tcPr = cell._tc.get_or_add_tcPr()
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), "E7E7E7")
                tcPr.append(shd)
            p = cell.paragraphs[0]
            p.alignment = amap[align_cols[c_i]] if r_i else WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
            p.paragraph_format.keep_with_next = r_i == 0   # keep the header with its first data row
            add_rich(p, str(val), size=size, bold=(bold_header and r_i == 0))
    # header bottom rule
    for cell in t.rows[0].cells:
        tcPr = cell._tc.get_or_add_tcPr()
        tb = OxmlElement("w:tcBorders")
        e = OxmlElement("w:bottom")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:color"), "000000")
        tb.append(e)
        tcPr.append(tb)
    return t


def picture(doc, path, width_in):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(path), width=Inches(width_in))
    return p


def pictures_row(doc, paths_widths):
    row = doc.add_table(rows=1, cols=len(paths_widths))
    row.alignment = WD_TABLE_ALIGNMENT.CENTER
    row.autofit = False
    _borders(row, inner=False)
    borders = row._tbl.tblPr.find(qn("w:tblBorders"))
    for border in borders:
        border.set(qn("w:val"), "nil")
    _cell_margins(row, top=0, bottom=0, left=0, right=0)
    row.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
    for index, (path, width) in enumerate(paths_widths):
        row.columns[index].width = Inches(width + 0.1)
        cell = row.cell(0, index)
        cell.width = row.columns[index].width
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.keep_with_next = True
        p.add_run().add_picture(str(path), width=Inches(width))


def page_number_footer(doc):
    sec = doc.sections[0]
    p = sec.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run()
    set_run_font(r, 9)
    for tag, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if tag:
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), tag)
            r._element.append(fc)
        else:
            it = OxmlElement("w:instrText")
            it.set(qn("xml:space"), "preserve")
            it.text = text
            r._element.append(it)


def set_core(doc, title, author, subject, keywords):
    cp = doc.core_properties
    cp.title, cp.author, cp.subject, cp.keywords = title, author, subject, keywords
    cp.comments = "Generated by report/build_report.py from results/results.json"
