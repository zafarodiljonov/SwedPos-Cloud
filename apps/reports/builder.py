"""
A report page is a list of blocks (tiles, cards with charts or tables). The builder turns Analytics results into
blocks; templates/reports/block.html draws them. Every table is also kept for the Excel export, so the download is
exactly what is on screen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext as T

from apps.analytics.services import Analytics, Filter, add_months

PAGES = ["overview", "sales", "payments", "waiters", "payroll", "tables", "products", "customers", "control", "stock"]
ICONS = {
    "overview": "M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z",
    "sales": "M12 2a10 10 0 1 0 0 20 10 10 0 1 0 0-20zM12 6v6l4 2",
    "payments": "M1 4h22v16H1zM1 10h22",
    "waiters": "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1",
    "payroll": "M19 5L5 19M7 7h.01M17 17h.01",
    "tables": "M3 3h18v18H3zM3 9h18M3 15h18M9 3v18M15 3v18",
    "products": "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
    "customers": "M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z",
    "control": "M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
    "stock": "M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4a2 2 0 0 0 1-1.7z",
}

TEXT, INT, MONEY, PERCENT, NUMBER, DATE, DATETIME = "text", "int", "money", "percent", "number", "date", "datetime"


@dataclass
class Table:
    """A titled table; shown on the page and written to Excel unchanged."""
    title: str
    columns: list = field(default_factory=list)   # (caption, kind)
    rows: list = field(default_factory=list)
    drill: str | None = None                       # "waiter" / "payroll": rows open a detail
    keys: list = field(default_factory=list)       # one key per row for the drill

    def col(self, caption, kind=TEXT):
        self.columns.append((caption, kind))
        return self

    def row(self, *values, key=None):
        self.rows.append(list(values))
        self.keys.append(key)
        return self


# ---- formatting (as the desktop: "1 250 000", "12,5%", short axis "1,2 mln") ----

def money(v) -> str:
    return f"{Decimal(v):,.0f}".replace(",", " ")


def number(v) -> str:
    return f"{Decimal(v):.1f}".rstrip("0").rstrip(".").replace(".", ",")


def percent(v) -> str:
    return number(v) + "%"


def short(v) -> str:
    a = abs(Decimal(v))
    for size, key in ((Decimal(1_000_000_000), "an_bln"), (Decimal(1_000_000), "an_mln"), (Decimal(1000), "an_thousand")):
        if a >= size:
            return number(Decimal(v) / size) + " " + T(key)
    return f"{Decimal(v):.0f}"


def local(dt: datetime | None) -> datetime | None:
    return None if dt is None else timezone.localtime(dt)


def cell(value, kind) -> str:
    if value is None:
        return "—"
    if kind in (MONEY, INT):
        return money(value)
    if kind == PERCENT:
        return percent(value)
    if kind == NUMBER:
        return number(value)
    if kind == DATE:
        return value.strftime("%d.%m.%Y")
    if kind == DATETIME:
        return local(value).strftime("%d.%m.%Y %H:%M")
    return str(value)


# ---- blocks ----

def tiles(*items):
    return {"kind": "tiles", "tiles": list(items)}


def tile(label, value, change=None, higher_is_better=True, note=None, accent=False):
    good = None if change in (None, 0) else (change > 0) == higher_is_better
    return {"label": label, "value": value, "change": change, "change_text": None if change is None else
            ("▲ " if change > 0 else "▼ " if change < 0 else "") + percent(abs(change)), "good": good, "note": note, "accent": accent}


def columns(*items):
    return {"kind": "columns", "items": list(items)}


def card(title, content, note=None, legend=None):
    return {"kind": "card", "title": title, "content": content, "note": note, "legend": legend}


def table_block(t: Table):
    return {"kind": "table", "table": t}


def empty():
    return {"kind": "empty"}


class Builder:
    def __init__(self, restaurant, lang: str):
        self.a = Analytics(restaurant)
        self.lang = lang
        self.tables: list[Table] = []

    def pick(self, uz, ru):
        return ru if self.lang == "ru" else uz

    def keep(self, t: Table) -> Table:
        self.tables.append(t)
        return t

    @staticmethod
    def weekdays():
        return T("an_weekdays").split("|")

    @staticmethod
    def month_short(d: date):
        return T("an_months").split("|")[d.month - 1]

    def month_name(self, d: date):
        return f"{self.month_short(d)} {d.year}"

    @staticmethod
    def method_name(key):
        return {"Cash": T("btn_pay_cash"), "Card": T("btn_pay_card"), "Transfer": T("pay_transfer_short")}.get(key, T("an_mixed"))

    def key_name(self, key):
        return {"DineIn": T("report_dine_in"), "Takeaway": T("order_type_takeaway"), "Delivery": T("order_type_delivery")}.get(key) or self.method_name(key)

    def build(self, page: str, f: Filter, pay_month: date) -> list:
        return {
            "sales": lambda: self.sales(f), "payments": lambda: self.payments(f), "waiters": lambda: self.waiters(f),
            "payroll": lambda: self.payroll(pay_month), "tables": lambda: self.tables_page(f), "products": lambda: self.products(f),
            "customers": lambda: self.customers(f), "control": lambda: self.control(f), "stock": lambda: self.stock(f),
        }.get(page, lambda: self.overview(f))()

    # ================= overview =================

    def overview(self, f):
        o = self.a.overview(f)
        k = o["kpis"]
        out = [
            tiles(tile(T("an_revenue"), money(k["revenue"]["value"]), k["revenue"]["change_percent"], accent=True),
                  tile(T("an_orders"), money(k["orders"]["value"]), k["orders"]["change_percent"]),
                  tile(T("report_avg"), money(k["average_check"]["value"]), k["average_check"]["change_percent"]),
                  tile(T("recipe_profit"), money(k["profit"]["value"]), k["profit"]["change_percent"]),
                  tile(T("recipe_margin"), percent(k["margin_percent"]["value"]), note=T("an_previous") + ": " + percent(k["margin_percent"]["previous"]))),
            tiles(tile(T("an_guests"), money(k["guests"]["value"]), k["guests"]["change_percent"]),
                  tile(T("an_per_guest"), money(k["average_per_guest"]["value"]), k["average_per_guest"]["change_percent"]),
                  tile(T("shift_discounts"), money(k["discounts"]["value"]), k["discounts"]["change_percent"], higher_is_better=False),
                  tile(T("an_cancelled"), money(k["cancelled"]["value"]) + " · " + money(k["cancelled_amount"]["value"]),
                       k["cancelled"]["change_percent"], higher_is_better=False),
                  tile(T("an_waiter_earned"), money(k["waiter_earned"]["value"]), k["waiter_earned"]["change_percent"])),
        ]
        g = o["granularity"]

        def label(d):
            return self.month_short(d) if g == "Month" else d.strftime("%d.%m")
        points = [{"label": label(p["start"]), "value": p["revenue"], "previous": p["previous_revenue"],
                   "tip": f"{label(p['start'])}\n{money(p['revenue'])}\n{T('an_orders')}: {p['orders']}\n{T('an_previous')}: {money(p['previous_revenue'])}"}
                  for p in o["series"]]
        out.append(card(T("an_revenue_by_" + g.lower()), {"kind": "line", "points": points},
                        legend=[(T("an_this_period"), False), (T("an_previous_period"), True)]))
        out.append(columns(
            card(T("an_payments"), {"kind": "shares", "parts": [(self.key_name(p["key"]), p["amount"], p["percent"]) for p in o["payments"]]}),
            card(T("report_types"), {"kind": "shares", "parts": [(self.key_name(t["key"]), t["amount"], t["percent"]) for t in o["order_types"]]})))
        out.append(columns(
            card(T("an_top_dishes"), bars([(self.pick(d["name_uz"], d["name_ru"]), d["revenue"], f"{money(d['revenue'])} · {d['quantity']}") for d in o["top_dishes"]])),
            card(T("an_top_waiters"), bars([(w["name"], w["revenue"], money(w["revenue"])) for w in o["top_waiters"]]))))

        t = self.keep(Table(T("an_revenue")).col(T("an_period_start"), DATE).col(T("an_orders"), INT)
                      .col(T("an_revenue"), MONEY).col(T("an_previous_period"), MONEY))
        for p in o["series"]:
            t.row(p["start"], p["orders"], p["revenue"], p["previous_revenue"])
        kt = self.keep(Table(T("an_key_figures")).col(T("an_figure")).col(T("an_this_period"), NUMBER)
                       .col(T("an_previous_period"), NUMBER).col(T("an_change"), PERCENT))
        for key, name in (("revenue", "an_revenue"), ("orders", "an_orders"), ("average_check", "report_avg"), ("guests", "an_guests"),
                          ("average_per_guest", "an_per_guest"), ("profit", "recipe_profit"), ("margin_percent", "recipe_margin"),
                          ("discounts", "shift_discounts"), ("delivery_fees", "delivery_fee"), ("cancelled", "an_cancelled"),
                          ("cancelled_amount", "an_cancelled_amount"), ("waiter_earned", "an_waiter_earned")):
            kt.row(T(name), k[key]["value"], k[key]["previous"], k[key]["change_percent"])
        return out

    # ================= sales =================

    def sales(self, f):
        s = self.a.sales(f)
        days = self.weekdays()
        hours = s["hours"]
        while hours and hours[0]["orders"] == 0:
            hours = hours[1:]
        while hours and hours[-1]["orders"] == 0:
            hours = hours[:-1]
        cells = {(c["weekday"], c["hour"]): c for c in s["heatmap"]}
        top = max((c["revenue"] for c in s["heatmap"]), default=Decimal(0))
        grid = [{"day": days[d], "cells": [heat_cell(cells.get((d, h)), top, days[d], h) for h in range(24)]} for d in range(7)]
        out = [
            card(T("an_heatmap"), {"kind": "heat", "rows": grid, "hours": [f"{h:02d}" if h % 3 == 0 else "" for h in range(24)]}),
            columns(
                card(T("report_hours"), {"kind": "bar", "points": [{"label": f"{h['hour']:02d}", "value": h["revenue"],
                     "tip": f"{h['hour']:02d}:00\n{money(h['revenue'])}\n{T('an_orders')}: {h['orders']}"} for h in hours]} if hours else empty()),
                card(T("an_weekday_avg"), {"kind": "bar", "points": [{"label": days[w["weekday"]], "value": w["average_per_day"],
                     "tip": f"{days[w['weekday']]}\n{money(w['average_per_day'])} {T('an_per_day')}\n{T('an_orders')}: {w['orders']}"} for w in s["weekdays"]]})),
            card(T("report_daily"), table_block(self.keep(self.period_table(T("report_daily"), [d for d in s["daily"] if d["orders"] > 0 or f.days <= 31], False)))),
        ]
        if len(s["monthly"]) > 1:
            out.append(card(T("an_monthly"), table_block(self.keep(self.period_table(T("an_monthly"), s["monthly"], True)))))
        return out

    def period_table(self, title, rows, months):
        t = (Table(title).col(T("an_month") if months else T("an_day"), TEXT if months else DATE).col(T("an_orders"), INT)
             .col(T("an_guests"), INT).col(T("an_revenue"), MONEY).col(T("report_avg"), MONEY).col(T("shift_discounts"), MONEY)
             .col(T("btn_pay_cash"), MONEY).col(T("btn_pay_card"), MONEY).col(T("pay_transfer_short"), MONEY).col(T("recipe_profit"), MONEY))
        for r in rows:
            t.row(self.month_name(r["start"]) if months else r["start"], r["orders"], r["guests"], r["revenue"], r["average_check"],
                  r["discounts"], r["cash"], r["card"], r["transfer"], r["profit"])
        return t

    # ================= payments =================

    def payments(self, f):
        p = self.a.payments(f)
        ts = [tile(self.method_name(x["method"]), money(x["amount"]), note=f"{percent(x['percent'])} · {x['payments']} {T('an_payments_count')}",
                   accent=x["method"] == "Cash") for x in p["methods"]]
        ts.append(tile(T("an_split_bills"), money(p["split_bills"]), note=T("an_split_note")))
        by_month = len(p["daily"]) > 62
        rows = p["monthly"] if by_month else p["daily"]
        points = [{"label": self.month_short(d["start"]) if by_month else d["start"].strftime("%d.%m"), "value": d["total"],
                   "tip": f"{self.month_name(d['start']) if by_month else d['start'].strftime('%d.%m.%Y')}\n{money(d['total'])}\n"
                          f"{T('btn_pay_cash')}: {money(d['cash'])}\n{T('btn_pay_card')}: {money(d['card'])}\n{T('pay_transfer_short')}: {money(d['transfer'])}"}
                  for d in rows]

        def methods(title, items, months):
            t = (Table(title).col(T("an_month") if months else T("an_day"), TEXT if months else DATE).col(T("btn_pay_cash"), MONEY)
                 .col(T("btn_pay_card"), MONEY).col(T("pay_transfer_short"), MONEY).col(T("an_total"), MONEY))
            for r in items:
                t.row(self.month_name(r["start"]) if months else r["start"], r["cash"], r["card"], r["transfer"], r["total"])
            return t
        return [
            tiles(*ts),
            card(T("an_payments_by_" + ("month" if by_month else "day")), {"kind": "bar", "points": points}),
            columns(card(T("an_payments_by_day"), table_block(self.keep(methods(T("an_payments_by_day"), [d for d in p["daily"] if d["total"] > 0 or f.days <= 31], False)))),
                    card(T("an_monthly"), table_block(self.keep(methods(T("an_monthly"), p["monthly"], True))))),
            card(T("an_shifts_cash"), table_block(self.keep(self.shift_table(T("an_shifts_cash"), p["shifts"])))),
        ]

    def shift_table(self, title, rows):
        t = (Table(title).col("№").col(T("an_opened"), DATETIME).col(T("an_closed"), DATETIME).col(T("an_opened_by"))
             .col(T("an_revenue"), MONEY).col(T("btn_pay_cash"), MONEY).col(T("an_expected_cash"), MONEY)
             .col(T("an_counted_cash"), MONEY).col(T("an_difference"), MONEY))
        for s in rows:
            t.row(str(s["shift_id"]), s["opened_at_utc"], s["closed_at_utc"], s["opened_by"], s["sales"], s["cash"], s["expected_cash"],
                  s["counted_cash"], s["difference"])
        return t

    # ================= waiters =================

    def waiters(self, f):
        w = self.a.waiters(f)
        t = (Table(T("an_page_waiters"), drill="waiter").col(T("an_waiter")).col(T("an_orders"), INT).col(T("an_revenue"), MONEY)
             .col(T("report_avg"), MONEY).col(T("an_percent"), PERCENT).col(T("an_earned"), MONEY).col(T("an_guests"), INT)
             .col(T("an_tables"), INT).col(T("shift_discounts"), MONEY).col(T("an_cancelled_short"), INT).col(T("an_minutes_at_table"), INT))
        for x in w["waiters"]:
            t.row(x["name"], x["orders"], x["revenue"], x["average_check"], x["effective_percent"], x["earned"], x["guests"], x["tables"],
                  x["discounts"], x["cancelled"], x["average_service_minutes"], key=x["waiter_id"])
        return [
            columns(card(T("an_revenue"), bars([(x["name"], x["revenue"], money(x["revenue"])) for x in w["waiters"]])),
                    card(T("report_avg"), bars([(x["name"], x["average_check"], money(x["average_check"]))
                                                for x in sorted((x for x in w["waiters"] if x["orders"] > 0), key=lambda x: x["average_check"], reverse=True)]))),
            card(T("an_page_waiters"), table_block(self.keep(t)), note=T("an_pick_row")),
        ]

    def waiter_detail(self, f, waiter_id: int, month: date | None):
        if month is not None:
            row = next((r for r in self.a.payroll(month.year, month.month)["rows"] if r["waiter_id"] == waiter_id), None)
            name, rows = (row["name"], row["tables"]) if row else ("?", [])
        else:
            rows = self.a.waiter_tables(f, waiter_id)
            name = self.a.user_names().get(waiter_id, "?")
        return card(f"{name} — {T('an_by_table')}", table_block(self.waiter_table(T("an_by_table"), rows)))

    def waiter_table(self, title, rows):
        t = (Table(title).col(T("an_hall")).col(T("an_table")).col(T("an_orders"), INT).col(T("an_food_paid"), MONEY)
             .col(T("an_percent"), PERCENT).col(T("an_earned"), MONEY))
        for r in rows:
            t.row(T("an_no_table") if r["table_id"] is None else r["hall"], r["table"], r["orders"], r["food_paid"], r["percent"], r["earned"])
        return t

    # ================= payroll =================

    def payroll(self, month: date):
        p = self.a.payroll(month.year, month.month)
        t = (Table(f"{T('an_page_payroll')} {self.month_name(month)}", drill="payroll").col(T("an_waiter")).col(T("an_orders"), INT)
             .col(T("an_food_paid"), MONEY).col(T("an_percent"), PERCENT).col(T("an_earned"), MONEY))
        for r in p["rows"]:
            share = Decimal(0) if r["food_paid"] == 0 else round(r["earned"] / r["food_paid"] * 100, 2)
            t.row(r["name"], r["orders"], r["food_paid"], share, r["earned"], key=r["waiter_id"])
        all_rows = (Table(T("an_by_table")).col(T("an_waiter")).col(T("an_hall")).col(T("an_table")).col(T("an_orders"), INT)
                    .col(T("an_food_paid"), MONEY).col(T("an_percent"), PERCENT).col(T("an_earned"), MONEY))
        for r in p["rows"]:
            for x in r["tables"]:
                all_rows.row(r["name"], T("an_no_table") if x["table_id"] is None else x["hall"], x["table"], x["orders"], x["food_paid"], x["percent"], x["earned"])
        self.keep(t)
        self.keep(all_rows)
        return [
            {"kind": "month_nav", "label": self.month_name(month), "note": T("an_payroll_note"),
             "prev": add_months(month, -1).isoformat(), "next": add_months(month, 1).isoformat()},
            tiles(tile(T("an_payroll_total"), money(p["total_earned"]), note=self.month_name(month), accent=True),
                  tile(T("an_page_waiters"), money(len(p["rows"])), note=T("an_with_sales")),
                  tile(T("an_orders"), money(sum(r["orders"] for r in p["rows"])), note=f"{T('an_food_paid')}: {money(sum((r['food_paid'] for r in p['rows']), Decimal(0)))}")),
            card(T("an_page_payroll"), table_block(t), note=T("an_pick_row")),
        ]

    # ================= tables =================

    def tables_page(self, f):
        p = self.a.tables(f)
        halls = Table(T("an_halls")).col(T("an_hall")).col(T("an_tables"), INT).col(T("an_orders"), INT).col(T("an_revenue"), MONEY).col(T("report_avg"), MONEY)
        for h in p["halls"]:
            halls.row(h["hall"], h["tables"], h["orders"], h["revenue"], h["average_check"])
        t = (Table(T("nav_tables")).col(T("an_hall")).col(T("an_table")).col(T("f_seats"), INT).col(T("an_orders"), INT).col(T("an_guests"), INT)
             .col(T("an_revenue"), MONEY).col(T("report_avg"), MONEY).col(T("an_minutes_at_table"), INT).col(T("an_orders_per_day"), NUMBER)
             .col(T("an_revenue_per_seat"), MONEY))
        for x in p["tables"]:
            t.row(x["hall"], x["table"], x["seats"], x["orders"], x["guests"], x["revenue"], x["average_check"], x["average_minutes"],
                  x["orders_per_day"], x["revenue_per_seat"])
        return [
            columns(card(T("an_halls"), table_block(self.keep(halls))),
                    card(T("an_top_tables"), bars([(f"{x['hall']} · {x['table']}", x["revenue"], money(x["revenue"])) for x in p["tables"] if x["orders"] > 0][:8]))),
            card(T("nav_tables"), table_block(self.keep(t))),
        ]

    # ================= products =================

    def products(self, f):
        p = self.a.products(f)
        t = (Table(T("report_dishes")).col(T("order_dish")).col(T("an_category")).col(T("order_qty"), INT).col(T("an_revenue"), MONEY)
             .col(T("an_share"), PERCENT).col(T("an_abc_revenue")).col(T("shift_cogs"), MONEY).col(T("recipe_profit"), MONEY)
             .col(T("recipe_margin"), PERCENT).col(T("an_abc_profit")).col(T("an_prep_short"), NUMBER))
        for d in p["dishes"]:
            t.row(self.pick(d["name_uz"], d["name_ru"]), self.pick(d["category_uz"], d["category_ru"]), d["quantity"], d["revenue"],
                  d["share_percent"], d["by_revenue"], d["cost"], d["profit"], d["margin_percent"], d["by_profit"], d["average_prep_minutes"])
        not_sold = self.keep(Table(T("an_not_sold")).col(T("order_dish")))
        for d in p["not_sold"]:
            not_sold.row(self.pick(d["name_uz"], d["name_ru"]))
        prep = p["average_prep_minutes"]
        return [
            tiles(tile(T("an_dishes_sold"), money(sum(d["quantity"] for d in p["dishes"])), note=f"{len(p['dishes'])} {T('an_kinds')}"),
                  tile(T("an_abc_a"), money(sum(1 for d in p["dishes"] if d["by_profit"] == "A")), note=T("an_abc_by_profit")),
                  tile(T("an_not_sold"), money(len(p["not_sold"])), note=T("an_not_sold_note")),
                  tile(T("an_prep_time"), "—" if prep is None else f"{number(prep)} {T('kitchen_min')}", note=T("an_prep_note"))),
            columns(card(T("an_categories"), {"kind": "shares", "parts": [(self.pick(c["name_uz"], c["name_ru"]), c["revenue"], c["share_percent"]) for c in p["categories"]]}),
                    card(T("an_top_profit"), bars([(self.pick(d["name_uz"], d["name_ru"]), d["profit"], money(d["profit"]))
                                                   for d in sorted(p["dishes"], key=lambda d: d["profit"], reverse=True)][:8]))),
            card(T("report_dishes"), table_block(self.keep(t)), note=T("an_abc_note")),
            card(T("an_not_sold"), {"kind": "chips", "items": [self.pick(d["name_uz"], d["name_ru"]) for d in p["not_sold"]]} if p["not_sold"] else empty()),
        ]

    # ================= customers =================

    def customers(self, f):
        c = self.a.customers(f)
        t = (Table(T("an_top_customers")).col(T("an_customer")).col(T("an_phone")).col(T("an_orders"), INT).col(T("an_revenue"), MONEY)
             .col(T("report_avg"), MONEY).col(T("an_last_order"), DATETIME).col(T("an_new")))
        for r in c["top"]:
            t.row(r["name"], format_phone(r["phone"]), r["orders"], r["revenue"], r["average_check"], r["last_order_utc"], "✓" if r["is_new"] else "")
        couriers = Table(T("an_couriers")).col(T("an_courier")).col(T("an_orders"), INT).col(T("an_revenue"), MONEY).col(T("delivery_fee"), MONEY)
        for r in c["couriers"]:
            couriers.row(T("an_no_courier") if r["courier_id"] is None else r["name"], r["orders"], r["revenue"], r["delivery_fees"])
        return [
            tiles(tile(T("an_customers"), money(c["customers"]), note=T("an_with_phone")),
                  tile(T("an_new_customers"), money(c["new_customers"]), note=T("an_first_order")),
                  tile(T("an_returning"), money(c["returning_customers"]), note=T("an_ordered_before")),
                  tile(T("an_delivery_orders"), money(c["delivery_orders"]), note=money(c["delivery_revenue"])),
                  tile(T("an_delivery_avg"), money(c["delivery_average_check"]))),
            card(T("an_top_customers"), table_block(self.keep(t))),
            card(T("an_couriers"), table_block(self.keep(couriers))),
        ]

    # ================= control =================

    def control(self, f):
        c = self.a.control(f)
        t = (Table(T("an_cancelled_orders")).col("№").col(T("an_time"), DATETIME).col(T("an_table")).col(T("an_waiter"))
             .col(T("an_cancelled_by")).col(T("an_reason")).col(T("an_amount"), MONEY).col(T("an_after_kitchen")))
        for r in c["cancelled"]:
            t.row(str(r["order_id"]), r["cancelled_at_utc"], r["table"], r["waiter"], r["cancelled_by"] or "—", r["reason"] or "—", r["amount"],
                  "✓" if r["was_sent_to_kitchen"] else "")
        discounts = Table(T("an_discounts_by_waiter")).col(T("an_waiter")).col(T("an_orders"), INT).col(T("shift_discounts"), MONEY)
        for r in c["discounts"]:
            discounts.row(r["waiter"], r["orders"], r["discounts"])
        removed = Table(T("an_removed_dishes")).col(T("an_time"), DATETIME).col("№").col(T("order_dish")).col(T("order_qty"), INT)
        for r in c["removed_dishes"]:
            removed.row(r["created_at_utc"], str(r["order_id"]), self.pick(r["name_uz"], r["name_ru"]), r["quantity"])
        return [
            tiles(tile(T("an_cancelled"), money(len(c["cancelled"])), note=money(sum((r["amount"] for r in c["cancelled"]), Decimal(0)))),
                  tile(T("an_cancelled_after_kitchen"), money(sum(1 for r in c["cancelled"] if r["was_sent_to_kitchen"])), note=T("an_food_wasted")),
                  tile(T("shift_discounts"), money(sum((r["discounts"] for r in c["discounts"]), Decimal(0))),
                       note=f"{sum(r['orders'] for r in c['discounts'])} {T('an_orders_lower')}"),
                  tile(T("an_removed_dishes"), money(sum(r["quantity"] for r in c["removed_dishes"])), note=T("an_removed_note")),
                  tile(T("an_cash_differences"), money(sum((r["difference"] for r in c["shift_differences"]), Decimal(0))),
                       note=f"{len(c['shift_differences'])} {T('an_shifts_lower')}")),
            card(T("an_cancelled_orders"), table_block(self.keep(t))),
            columns(card(T("an_discounts_by_waiter"), table_block(self.keep(discounts))),
                    card(T("an_removed_dishes"), table_block(self.keep(removed)))),
            card(T("an_cash_differences"), table_block(self.keep(self.shift_table(T("an_cash_differences"), c["shift_differences"])))),
        ]

    # ================= stock =================

    def stock(self, f):
        s = self.a.stock(f)
        units = {"Gram": ("g", "kg", 1000), "Milliliter": ("ml", "l", 1000), "Piece": ("", "", 1)}

        def qty(v, unit):
            small, big, size = units.get(unit, ("", "", 1))
            if big and abs(v) >= size:
                return f"{number(Decimal(v) / size)} {big}"
            return f"{number(v)} {small}".strip()
        t = Table(T("nav_stock")).col(T("recipe_ingredient")).col(T("stock_onhand")).col(T("stock_min")).col(T("an_value"), MONEY).col(T("stock_low"))
        for r in sorted(s["stock"], key=lambda r: (not r["is_low"], r["name"])):
            t.row(r["name"], qty(r["on_hand"], r["unit"]), qty(r["min"], r["unit"]), round(r["value"]), "!" if r["is_low"] else "")
        return [
            tiles(tile(T("report_stock_value"), money(s["stock_value"]), note=T("an_now"), accent=True),
                  tile(T("stock_low"), money(sum(1 for r in s["stock"] if r["is_low"])), note=T("an_low_note")),
                  tile(T("op_waste"), money(s["waste_cost"]), note=T("an_in_period"))),
            card(T("nav_stock"), table_block(self.keep(t))),
        ]


def bars(rows):
    rows = rows[:10]
    top = max((r[1] for r in rows), default=Decimal(0))
    return {"kind": "bars", "rows": [{"label": label, "text": text, "width": 0 if top <= 0 else max(0, float(value / top * 100))}
                                     for label, value, text in rows]}


def heat_cell(c, top, day, hour):
    tip = f"{day} {hour:02d}:00–{(hour + 1) % 24:02d}:00\n{money(c['revenue'] if c else 0)}\n{T('an_orders')}: {c['orders'] if c else 0}"
    alpha = None if not c or top == 0 else round(0.16 + 0.84 * float(c["revenue"] / top), 2)
    return {"alpha": alpha, "tip": tip}


def format_phone(digits: str) -> str:
    if len(digits) == 12 and digits.startswith("998"):
        return f"+998 {digits[3:5]} {digits[5:8]} {digits[8:10]} {digits[10:12]}"
    return digits
