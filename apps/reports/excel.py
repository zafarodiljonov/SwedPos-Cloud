"""The page's tables as an .xlsx file: one sheet per table, title and period on top, numbers kept as numbers."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .builder import DATE, DATETIME, INT, MONEY, NUMBER, PERCENT, local

BRASS = PatternFill("solid", fgColor="D6A33A")
FORMATS = {INT: "0", MONEY: "#,##0", PERCENT: '0.0"%"', NUMBER: "0.0", DATE: "dd.mm.yyyy", DATETIME: "dd.mm.yyyy hh:mm"}


def workbook(title: str, period: str, tables) -> bytes:
    book = Workbook()
    book.remove(book.active)
    used = set()
    for table in tables:
        sheet = book.create_sheet(_sheet_name(table.title, used))
        sheet.cell(1, 1, f"{title} — {table.title}").font = Font(bold=True, size=13)
        sheet.cell(2, 1, period)
        header = 4
        for c, (caption, _) in enumerate(table.columns, start=1):
            cell = sheet.cell(header, c, caption)
            cell.font = Font(bold=True)
            cell.fill = BRASS
        for r, row in enumerate(table.rows, start=header + 1):
            for c, ((_, kind), value) in enumerate(zip(table.columns, row), start=1):
                if value is None:
                    continue
                if kind == DATETIME:
                    value = local(value).replace(tzinfo=None)
                cell = sheet.cell(r, c, float(value) if kind in (MONEY, PERCENT, NUMBER) else value)
                if kind in FORMATS:
                    cell.number_format = FORMATS[kind]
        sheet.freeze_panes = sheet.cell(header + 1, 1)
        for c, (caption, _) in enumerate(table.columns, start=1):
            longest = max([len(str(caption))] + [len(str(row[c - 1])) for row in table.rows if row[c - 1] is not None])
            sheet.column_dimensions[get_column_letter(c)].width = min(48, longest + 3)
    if not book.sheetnames:
        book.create_sheet("-")
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def _sheet_name(title, used):
    clean = "".join(ch for ch in title if ch not in "[]:*?/\\").strip()[:28] or "Sheet"
    name, i = clean, 2
    while name.lower() in used:
        name, i = f"{clean} {i}", i + 1
    used.add(name.lower())
    return name
