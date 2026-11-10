from datetime import date, datetime
from decimal import Decimal

from django import template

from apps.reports import charts
from apps.reports.builder import DATE, DATETIME, INT, MONEY, NUMBER, PERCENT, cell, money, percent

register = template.Library()

NUMERIC = {INT, MONEY, PERCENT, NUMBER}


@register.simple_tag
def chart(block):
    return charts.line_chart(block["points"]) if block["kind"] == "line" else charts.bar_chart(block["points"])


@register.filter
def numeric(kind):
    return kind in NUMERIC


@register.simple_tag
def show(value, kind):
    return cell(value, kind)


@register.simple_tag
def sort_value(value, kind):
    """What the table sorts by when a column header is clicked."""
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if kind in NUMERIC:
        return str(Decimal(value))
    return str(value).lower()


@register.filter
def rows_with_keys(table):
    return zip(table.rows, table.keys)


@register.filter
def columns_with_values(row, table):
    return zip(table.columns, row)


@register.simple_tag
def share(parts):
    """Parts that have an amount, with their colour index."""
    return [(i % 6, label, money(amount), percent(pct), max(float(pct), 0.5)) for i, (label, amount, pct) in enumerate(p for p in parts if p[1] > 0)]
