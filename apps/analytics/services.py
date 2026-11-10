"""
Restaurant analytics, a faithful port of the desktop's AnalyticsService.cs (same rules, same rounding), so the website
shows exactly the numbers the restaurant sees. tests/test_golden.py checks every page against numbers produced by the
desktop itself for a fixed week.

Results are plain dicts with the same field names as the desktop records (in snake_case).
"Revenue" is what guests paid, delivery fees included; the waiter's share is counted on food only.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from functools import cached_property
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q

from apps.sync import models as m

ZERO = Decimal(0)
OVERLAP_NONE = None


def tz() -> ZoneInfo:
    return ZoneInfo(settings.TIME_ZONE)


def rnd(value, places: int = 0) -> Decimal:
    """C# Math.Round(decimal, places): halves go to the even neighbour."""
    return Decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)


def dec_from_double(value: float) -> Decimal:
    """C# (decimal)double conversion: about 15 significant digits."""
    return Decimal(format(value, ".15g"))


def avg(total: Decimal, count: int) -> Decimal:
    return ZERO if count == 0 else rnd(total / count, 0)


def pct(part: Decimal, whole: Decimal) -> Decimal:
    return ZERO if whole == 0 else rnd(part / whole * 100, 1)


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    y, mth = divmod(d.month - 1 + n, 12)
    return date(d.year + y, mth + 1, 1) if d.day == 1 else date(d.year + y, mth + 1, d.day)


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def method_name(code) -> str:
    return m.PaymentMethod(code).label


def type_name(code) -> str:
    return m.OrderType(code).label


# ============================== filter ==============================

@dataclass(frozen=True)
class Filter:
    """Local days (both ends included) and optional hall, waiter and order type (desktop AnalyticsFilter)."""
    from_: date
    to: date
    hall_id: int | None = None
    waiter_id: int | None = None
    type: int | None = None

    @property
    def days(self) -> int:
        return (self.to - self.from_).days + 1

    def previous(self) -> "Filter":
        return replace(self, from_=self.from_ - timedelta(days=self.days), to=self.from_ - timedelta(days=1))

    def as_dict(self):
        return {"from": self.from_, "to": self.to, "hall_id": self.hall_id, "waiter_id": self.waiter_id,
                "type": None if self.type is None else type_name(self.type), "days": self.days}

    def window(self):
        zone = tz()
        start = datetime.combine(self.from_, time.min, zone)
        end = datetime.combine(self.to + timedelta(days=1), time.min, zone)
        return start, end


def kpi(value, previous):
    value, previous = Decimal(value), Decimal(previous)
    change = None if previous == 0 else rnd((value - previous) / abs(previous) * 100, 1)
    return {"value": value, "previous": previous, "change_percent": change}


# ============================== data ==============================

@dataclass
class OrderFact:
    id: int
    paid_at: datetime
    created_at: datetime
    table_id: int | None
    waiter_id: int
    type: int
    customer_id: int | None
    courier_id: int | None
    guests: int | None
    subtotal: Decimal
    discount_percent: Decimal
    delivery_fee: Decimal
    waiter_percent: Decimal
    waiter_earned: Decimal

    @cached_property
    def food(self) -> Decimal:
        return rnd(self.subtotal * (1 - self.discount_percent / Decimal(100)), 0)

    @property
    def total(self) -> Decimal:
        return self.food + self.delivery_fee

    @property
    def discount(self) -> Decimal:
        return self.subtotal - self.food

    @cached_property
    def paid_local(self) -> datetime:
        return self.paid_at.astimezone(tz())

    @property
    def day(self) -> date:
        return self.paid_local.date()


@dataclass
class LineFact:
    order_id: int
    dish_id: int
    quantity: int
    unit_price: Decimal
    sent_at: datetime | None
    ready_at: datetime | None


@dataclass
class PaymentFact:
    order_id: int
    method: int
    amount: Decimal


@dataclass
class Data:
    filter: Filter
    orders: list[OrderFact]
    lines: list[LineFact]
    payments: list[PaymentFact]
    cost: dict[int, Decimal] = field(default_factory=dict)

    @property
    def revenue(self) -> Decimal:
        return sum((o.total for o in self.orders), ZERO)

    @property
    def cost_of_goods(self) -> Decimal:
        return rnd(sum((self.cost.get(o.id, ZERO) for o in self.orders), ZERO), 0)

    @property
    def profit(self) -> Decimal:
        return self.revenue - self.cost_of_goods


def _minutes(delta: timedelta) -> float:
    return delta.total_seconds() / 60


class Analytics:
    """All report pages for one restaurant."""

    def __init__(self, restaurant):
        self.r = restaurant

    # ---------- loading ----------

    def _filtered(self, f: Filter):
        qs = m.Order.objects.filter(restaurant=self.r)
        if f.hall_id is not None:
            tables = m.DiningTable.objects.filter(restaurant=self.r, hall_sid=f.hall_id).values_list("sid", flat=True)
            qs = qs.filter(table_sid__in=list(tables))
        if f.waiter_id is not None:
            qs = qs.filter(waiter_sid=f.waiter_id)
        if f.type is not None:
            qs = qs.filter(type=f.type)
        return qs

    def _paid_in(self, f: Filter):
        start, end = f.window()
        return self._filtered(f).filter(status=m.OrderStatus.PAID, paid_at__gte=start, paid_at__lt=end)

    def _cancelled_in(self, f: Filter):
        start, end = f.window()
        return self._filtered(f).filter(status=m.OrderStatus.CANCELLED).filter(
            Q(cancelled_at__gte=start, cancelled_at__lt=end) | Q(cancelled_at__isnull=True, created_at__gte=start, created_at__lt=end))

    def load(self, f: Filter) -> Data:
        orders = list(self._paid_in(f).order_by("sid").values(
            "id", "sid", "paid_at", "created_at", "table_sid", "waiter_sid", "type", "customer_sid", "courier_sid", "guests",
            "discount_percent", "delivery_fee", "waiter_percent", "waiter_earned"))
        pk_to_sid = {o["id"]: o["sid"] for o in orders}
        lines = [LineFact(pk_to_sid[l["order_id"]], l["dish_sid"], l["quantity"], l["unit_price"], l["sent_at"], l["ready_at"])
                 for l in m.OrderLine.objects.filter(order_id__in=pk_to_sid.keys()).order_by("order__sid", "sid")
                 .values("order_id", "dish_sid", "quantity", "unit_price", "sent_at", "ready_at")]
        subtotal = defaultdict(lambda: ZERO)
        for l in lines:
            subtotal[l.order_id] += l.unit_price * l.quantity
        payments = [PaymentFact(pk_to_sid[p["order_id"]], p["method"], p["amount"])
                    for p in m.Payment.objects.filter(order_id__in=pk_to_sid.keys()).order_by("order__sid", "sid")
                    .values("order_id", "method", "amount")]
        cost = defaultdict(lambda: ZERO)
        for s in m.StockMovement.objects.filter(restaurant=self.r, type=m.StockMovementType.SALE,
                                                order_sid__in=list(pk_to_sid.values())).values("order_sid", "quantity", "unit_cost"):
            cost[s["order_sid"]] += -s["quantity"] * s["unit_cost"]
        facts = [OrderFact(o["sid"], o["paid_at"], o["created_at"], o["table_sid"], o["waiter_sid"], o["type"], o["customer_sid"],
                           o["courier_sid"], o["guests"], subtotal[o["sid"]], o["discount_percent"], o["delivery_fee"],
                           o["waiter_percent"], o["waiter_earned"]) for o in orders]
        return Data(f, facts, lines, payments, dict(cost))

    def user_names(self) -> dict[int, str]:
        return dict(m.Staff.objects.filter(restaurant=self.r).values_list("sid", "full_name"))

    def places(self) -> dict[int, dict]:
        halls = dict(m.Hall.objects.filter(restaurant=self.r).values_list("sid", "name"))
        return {t.sid: {"table_id": t.sid, "table": t.name, "hall_id": t.hall_sid, "hall": halls.get(t.hall_sid, "?"), "seats": t.seats}
                for t in m.DiningTable.objects.filter(restaurant=self.r).order_by("sid")}

    def dishes(self) -> dict[int, dict]:
        cats = {c.sid: c for c in m.Category.objects.filter(restaurant=self.r)}
        result = {}
        for d in m.Dish.objects.filter(restaurant=self.r).order_by("sid"):
            c = cats.get(d.category_sid)
            result[d.sid] = {"id": d.sid, "name_uz": d.name_uz, "name_ru": d.name_ru, "category_id": d.category_sid,
                             "category_uz": c.name_uz if c else "?", "category_ru": c.name_ru if c else "?", "is_active": d.is_active}
        return result

    # ================= overview =================

    def overview(self, f: Filter) -> dict:
        now, before = self.load(f), self.load(f.previous())
        now_c, now_ca = self._cancelled_totals(f)
        prev_c, prev_ca = self._cancelled_totals(f.previous())

        def guests(d: Data):
            return sum((o.guests or 0 for o in d.orders), 0)

        def per_guest(d: Data):
            with_guests = [o for o in d.orders if (o.guests or 0) > 0]
            g = sum(o.guests for o in with_guests)
            return ZERO if g == 0 else rnd(sum((o.total for o in with_guests), ZERO) / g, 0)

        kpis = {
            "revenue": kpi(now.revenue, before.revenue),
            "orders": kpi(len(now.orders), len(before.orders)),
            "guests": kpi(guests(now), guests(before)),
            "average_check": kpi(avg(now.revenue, len(now.orders)), avg(before.revenue, len(before.orders))),
            "average_per_guest": kpi(per_guest(now), per_guest(before)),
            "profit": kpi(now.profit, before.profit),
            "margin_percent": kpi(pct(now.profit, now.revenue), pct(before.profit, before.revenue)),
            "discounts": kpi(sum((o.discount for o in now.orders), ZERO), sum((o.discount for o in before.orders), ZERO)),
            "delivery_fees": kpi(sum((o.delivery_fee for o in now.orders), ZERO), sum((o.delivery_fee for o in before.orders), ZERO)),
            "cancelled": kpi(now_c, prev_c),
            "cancelled_amount": kpi(now_ca, prev_ca),
            "waiter_earned": kpi(sum((o.waiter_earned for o in now.orders), ZERO), sum((o.waiter_earned for o in before.orders), ZERO)),
        }
        granularity = "Day" if f.days <= 31 else "Week" if f.days <= 184 else "Month"
        series = self._series(now, before, granularity)

        total_pay = sum((p.amount for p in now.payments), ZERO)
        by_method = _group(now.payments, lambda p: p.method)
        payments = sorted(({"key": method_name(k), "count": len(v), "amount": sum((p.amount for p in v), ZERO),
                            "percent": pct(sum((p.amount for p in v), ZERO), total_pay)} for k, v in by_method.items()),
                          key=lambda r: r["amount"], reverse=True)
        revenue = now.revenue
        by_type = _group(now.orders, lambda o: o.type)
        types = sorted(({"key": type_name(k), "count": len(v), "amount": sum((o.total for o in v), ZERO),
                         "percent": pct(sum((o.total for o in v), ZERO), revenue)} for k, v in by_type.items()),
                       key=lambda r: r["amount"], reverse=True)

        dishes = self.dishes()
        factor = {o.id: 1 - o.discount_percent / Decimal(100) for o in now.orders}
        by_dish = _group(now.lines, lambda l: l.dish_id)
        top_dishes = sorted(({"dish_id": k, "name_uz": dishes.get(k, {}).get("name_uz", "?"), "name_ru": dishes.get(k, {}).get("name_ru", "?"),
                              "quantity": sum(l.quantity for l in v),
                              "revenue": rnd(sum((l.quantity * l.unit_price * factor[l.order_id] for l in v), ZERO), 0)}
                             for k, v in by_dish.items()), key=lambda r: r["revenue"], reverse=True)[:5]
        users = self.user_names()
        by_waiter = _group(now.orders, lambda o: o.waiter_id)
        top_waiters = sorted(({"waiter_id": k, "name": users.get(k, "?"), "orders": len(v), "revenue": sum((o.total for o in v), ZERO)}
                              for k, v in by_waiter.items()), key=lambda r: r["revenue"], reverse=True)[:5]
        return {"filter": f.as_dict(), "kpis": kpis, "granularity": granularity, "series": series, "payments": payments,
                "order_types": types, "top_dishes": top_dishes, "top_waiters": top_waiters}

    @staticmethod
    def _series(now: Data, before: Data, g: str):
        def bucket(d: date):
            return week_start(d) if g == "Week" else month_start(d) if g == "Month" else d

        def step(d: date):
            return d + timedelta(days=7) if g == "Week" else add_months(d, 1) if g == "Month" else d + timedelta(days=1)

        def buckets(f: Filter):
            out, d = [], bucket(f.from_)
            while d <= f.to:
                out.append(d)
                d = step(d)
            return out

        current = _group(now.orders, lambda o: bucket(o.day))
        previous = {k: sum((o.total for o in v), ZERO) for k, v in _group(before.orders, lambda o: bucket(o.day)).items()}
        prev_buckets = buckets(before.filter)
        points = []
        for i, start in enumerate(buckets(now.filter)):
            orders = current.get(start, [])
            revenue = sum((o.total for o in orders), ZERO)
            cost = rnd(sum((now.cost.get(o.id, ZERO) for o in orders), ZERO), 0)
            prev = previous.get(prev_buckets[i], ZERO) if i < len(prev_buckets) else ZERO
            points.append({"start": start, "orders": len(orders), "revenue": revenue, "profit": revenue - cost, "previous_revenue": prev})
        return points

    def _cancelled_totals(self, f: Filter):
        rows = list(self._cancelled_in(f).values_list("id", flat=True))
        amounts = defaultdict(lambda: ZERO)
        for l in m.OrderLine.objects.filter(order_id__in=rows).values("order_id", "quantity", "unit_price"):
            amounts[l["order_id"]] += l["unit_price"] * l["quantity"]
        return len(rows), sum((amounts[r] for r in rows), ZERO)

    # ================= sales =================

    def sales(self, f: Filter) -> dict:
        d = self.load(f)
        heat = _group(d.orders, lambda o: (o.paid_local.weekday(), o.paid_local.hour))
        heatmap = [{"weekday": k[0], "hour": k[1], "orders": len(v), "revenue": sum((o.total for o in v), ZERO)}
                   for k, v in sorted(heat.items())]
        by_hour = _group(d.orders, lambda o: o.paid_local.hour)
        hours = [{"hour": h, "orders": len(by_hour.get(h, [])), "revenue": sum((o.total for o in by_hour.get(h, [])), ZERO)} for h in range(24)]
        day_count = [0] * 7
        day = f.from_
        while day <= f.to:
            day_count[day.weekday()] += 1
            day += timedelta(days=1)
        by_wd = _group(d.orders, lambda o: o.paid_local.weekday())
        weekdays = []
        for w in range(7):
            revenue = sum((o.total for o in by_wd.get(w, [])), ZERO)
            weekdays.append({"weekday": w, "orders": len(by_wd.get(w, [])), "revenue": revenue,
                             "average_per_day": ZERO if day_count[w] == 0 else rnd(revenue / day_count[w], 0)})
        pays = _group(d.payments, lambda p: p.order_id)
        by_day = _group(d.orders, lambda o: o.day)
        daily = [self._period_row(f.from_ + timedelta(days=i), by_day.get(f.from_ + timedelta(days=i), []), pays, d.cost) for i in range(f.days)]
        by_month = _group(d.orders, lambda o: month_start(o.day))
        monthly, mth = [], month_start(f.from_)
        while mth <= f.to:
            monthly.append(self._period_row(mth, by_month.get(mth, []), pays, d.cost))
            mth = add_months(mth, 1)
        return {"filter": f.as_dict(), "heatmap": heatmap, "hours": hours, "weekdays": weekdays, "daily": daily, "monthly": monthly}

    @staticmethod
    def _period_row(start, orders, pays, costs):
        ps = [p for o in orders for p in pays.get(o.id, [])]
        revenue = sum((o.total for o in orders), ZERO)
        cost = rnd(sum((costs.get(o.id, ZERO) for o in orders), ZERO), 0)

        def by(method):
            return sum((p.amount for p in ps if p.method == method), ZERO)

        return {"start": start, "orders": len(orders), "guests": sum((o.guests or 0 for o in orders), 0), "revenue": revenue,
                "average_check": avg(revenue, len(orders)), "discounts": sum((o.discount for o in orders), ZERO),
                "cash": by(m.PaymentMethod.CASH), "card": by(m.PaymentMethod.CARD), "transfer": by(m.PaymentMethod.TRANSFER),
                "profit": revenue - cost}

    # ================= payments =================

    def payments(self, f: Filter) -> dict:
        d = self.load(f)
        total = sum((p.amount for p in d.payments), ZERO)
        methods = []
        for method in (m.PaymentMethod.CASH, m.PaymentMethod.CARD, m.PaymentMethod.TRANSFER):
            rows = [p for p in d.payments if p.method == method]
            amount = sum((p.amount for p in rows), ZERO)
            methods.append({"method": method.label, "payments": len(rows), "amount": amount, "percent": pct(amount, total)})
        split = sum(1 for v in _group(d.payments, lambda p: p.order_id).values() if len(v) > 1)
        day_of = {o.id: o.day for o in d.orders}
        by_day = _group(d.payments, lambda p: day_of[p.order_id])
        by_month = _group(d.payments, lambda p: month_start(day_of[p.order_id]))

        def row(start, rows):
            cash = sum((p.amount for p in rows if p.method == m.PaymentMethod.CASH), ZERO)
            card = sum((p.amount for p in rows if p.method == m.PaymentMethod.CARD), ZERO)
            transfer = sum((p.amount for p in rows if p.method == m.PaymentMethod.TRANSFER), ZERO)
            return {"start": start, "cash": cash, "card": card, "transfer": transfer, "total": cash + card + transfer}

        daily = [row(f.from_ + timedelta(days=i), by_day.get(f.from_ + timedelta(days=i), [])) for i in range(f.days)]
        monthly, mth = [], month_start(f.from_)
        while mth <= f.to:
            monthly.append(row(mth, by_month.get(mth, [])))
            mth = add_months(mth, 1)
        return {"filter": f.as_dict(), "methods": methods, "split_bills": split, "daily": daily, "monthly": monthly,
                "shifts": self._shift_rows(f)}

    def _shift_rows(self, f: Filter):
        start, end = f.window()
        users = self.user_names()
        rows = []
        for s in m.Shift.objects.filter(restaurant=self.r, opened_at__gte=start, opened_at__lt=end).order_by("opened_at"):
            order_ids = list(m.Order.objects.filter(restaurant=self.r, shift_sid=s.sid, status=m.OrderStatus.PAID).values_list("id", flat=True))
            subtotals, discounts, fees = defaultdict(lambda: ZERO), {}, {}
            for o in m.Order.objects.filter(id__in=order_ids).values("id", "discount_percent", "delivery_fee"):
                discounts[o["id"]], fees[o["id"]] = o["discount_percent"], o["delivery_fee"]
            for l in m.OrderLine.objects.filter(order_id__in=order_ids).values("order_id", "quantity", "unit_price"):
                subtotals[l["order_id"]] += l["unit_price"] * l["quantity"]
            sales = sum((rnd(subtotals[i] * (1 - discounts[i] / Decimal(100)), 0) + fees[i] for i in order_ids), ZERO)
            cash = sum((p.amount for p in m.Payment.objects.filter(restaurant=self.r, shift_sid=s.sid, method=m.PaymentMethod.CASH)), ZERO)
            moves = list(m.CashMovement.objects.filter(restaurant=self.r, shift_sid=s.sid).values_list("amount", flat=True))
            cash_in = sum((a for a in moves if a > 0), ZERO)
            cash_out = -sum((a for a in moves if a < 0), ZERO)
            expected = s.opening_cash + cash + cash_in - cash_out
            rows.append({"shift_id": s.sid, "opened_at_utc": s.opened_at, "closed_at_utc": s.closed_at, "opened_by": users.get(s.opened_by_sid, "?"),
                         "sales": sales, "cash": cash, "expected_cash": expected, "counted_cash": s.counted_cash,
                         "difference": None if s.counted_cash is None else s.counted_cash - expected})
        return rows

    # ================= waiters =================

    def waiters(self, f: Filter) -> dict:
        d = self.load(f)
        users = self.user_names()
        cancelled = {}
        for w in self._cancelled_in(f).order_by("sid").values_list("waiter_sid", flat=True):
            cancelled[w] = cancelled.get(w, 0) + 1
        rows = []
        for w, orders in _group(d.orders, lambda o: o.waiter_id).items():
            revenue = sum((o.total for o in orders), ZERO)
            food = sum((o.food for o in orders), ZERO)
            earned = sum((o.waiter_earned for o in orders), ZERO)
            minutes = sum(_minutes(o.paid_at - o.created_at) for o in orders) / len(orders)
            rows.append({"waiter_id": w, "name": users.get(w, "?"), "orders": len(orders), "guests": sum((o.guests or 0 for o in orders), 0),
                         "tables": len({o.table_id for o in orders if o.table_id is not None}), "revenue": revenue,
                         "average_check": avg(revenue, len(orders)), "discounts": sum((o.discount for o in orders), ZERO),
                         "cancelled": cancelled.get(w, 0), "average_service_minutes": rnd(dec_from_double(minutes), 0),
                         "food_paid": food, "earned": earned, "effective_percent": ZERO if food == 0 else rnd(earned / food * 100, 2)})
        for w, count in cancelled.items():
            if all(r["waiter_id"] != w for r in rows):
                rows.append({"waiter_id": w, "name": users.get(w, "?"), "orders": 0, "guests": 0, "tables": 0, "revenue": ZERO,
                             "average_check": ZERO, "discounts": ZERO, "cancelled": count, "average_service_minutes": ZERO,
                             "food_paid": ZERO, "earned": ZERO, "effective_percent": ZERO})
        return {"filter": f.as_dict(), "waiters": sorted(rows, key=lambda r: r["revenue"], reverse=True)}

    def waiter_tables(self, f: Filter, waiter_id: int) -> list:
        d = self.load(replace(f, waiter_id=waiter_id))
        return self._table_breakdown(d.orders, self.places())

    @staticmethod
    def _table_breakdown(orders, places):
        rows = []
        for table_id, group in _group(orders, lambda o: o.table_id).items():
            place = places.get(table_id) if table_id is not None else None
            food = sum((o.food for o in group), ZERO)
            earned = sum((o.waiter_earned for o in group), ZERO)
            rows.append({"table_id": table_id, "table": place["table"] if place else "-", "hall": place["hall"] if place else "-",
                         "orders": len(group), "food_paid": food, "percent": ZERO if food == 0 else rnd(earned / food * 100, 2), "earned": earned})
        rows.sort(key=lambda r: r["table"])
        rows.sort(key=lambda r: r["earned"], reverse=True)
        return rows

    def payroll(self, year: int, month: int) -> dict:
        start = date(year, month, 1)
        f = Filter(start, add_months(start, 1) - timedelta(days=1))
        d = self.load(f)
        users, places = self.user_names(), self.places()
        rows = [{"waiter_id": w, "name": users.get(w, "?"), "orders": len(g), "food_paid": sum((o.food for o in g), ZERO),
                 "earned": sum((o.waiter_earned for o in g), ZERO), "tables": self._table_breakdown(g, places)}
                for w, g in _group(d.orders, lambda o: o.waiter_id).items()]
        rows.sort(key=lambda r: r["name"])
        rows.sort(key=lambda r: r["earned"], reverse=True)
        return {"year": year, "month": month, "rows": rows, "total_earned": sum((r["earned"] for r in rows), ZERO)}

    # ================= tables =================

    def tables(self, f: Filter) -> dict:
        d = self.load(f)
        by_table = _group([o for o in d.orders if o.table_id is not None], lambda o: o.table_id)
        rows = []
        for p in self.places().values():
            if f.hall_id is not None and p["hall_id"] != f.hall_id:
                continue
            orders = by_table.get(p["table_id"], [])
            revenue = sum((o.total for o in orders), ZERO)
            minutes = ZERO if not orders else rnd(dec_from_double(sum(_minutes(o.paid_at - o.created_at) for o in orders) / len(orders)), 0)
            rows.append({"table_id": p["table_id"], "table": p["table"], "hall_id": p["hall_id"], "hall": p["hall"], "seats": p["seats"],
                         "orders": len(orders), "guests": sum((o.guests or 0 for o in orders), 0), "revenue": revenue,
                         "average_check": avg(revenue, len(orders)), "average_minutes": minutes,
                         "orders_per_day": rnd(Decimal(len(orders)) / f.days, 1),
                         "revenue_per_seat": ZERO if p["seats"] == 0 else rnd(revenue / p["seats"], 0)})
        rows.sort(key=lambda r: r["table"])
        rows.sort(key=lambda r: r["hall"])
        rows.sort(key=lambda r: r["revenue"], reverse=True)
        halls = []
        for (hall_id, hall), g in _group(rows, lambda r: (r["hall_id"], r["hall"])).items():
            revenue = sum((r["revenue"] for r in g), ZERO)
            orders = sum(r["orders"] for r in g)
            halls.append({"hall_id": hall_id, "hall": hall, "tables": len(g), "orders": orders, "revenue": revenue, "average_check": avg(revenue, orders)})
        halls.sort(key=lambda h: h["revenue"], reverse=True)
        return {"filter": f.as_dict(), "tables": rows, "halls": halls}

    # ================= products =================

    def products(self, f: Filter) -> dict:
        d = self.load(f)
        dishes = self.dishes()
        factor = {o.id: 1 - o.discount_percent / Decimal(100) for o in d.orders}
        sold = list(dict.fromkeys(l.dish_id for l in d.lines))
        costs = dict(m.Ingredient.objects.filter(restaurant=self.r).values_list("sid", "cost_per_unit"))
        portion = defaultdict(lambda: ZERO)
        for r in m.RecipeLine.objects.filter(restaurant=self.r, dish_sid__in=sold):
            portion[r.dish_sid] += r.quantity_per_portion * costs.get(r.ingredient_sid, ZERO)

        raw = []
        for dish_id, lines in _group(d.lines, lambda l: l.dish_id).items():
            qty = sum(l.quantity for l in lines)
            prep = [_minutes(l.ready_at - l.sent_at) for l in lines if l.sent_at and l.ready_at]
            raw.append({"dish_id": dish_id, "quantity": qty,
                        "revenue": rnd(sum((l.quantity * l.unit_price * factor[l.order_id] for l in lines), ZERO), 0),
                        "cost": rnd(qty * portion.get(dish_id, ZERO), 0),
                        "prep": None if not prep else rnd(dec_from_double(sum(prep) / len(prep)), 1)})
        total = sum((r["revenue"] for r in raw), ZERO)
        by_revenue = abc([(r["dish_id"], r["revenue"]) for r in raw])
        by_profit = abc([(r["dish_id"], r["revenue"] - r["cost"]) for r in raw])
        rows = []
        for r in raw:
            info = dishes.get(r["dish_id"], {})
            profit = r["revenue"] - r["cost"]
            rows.append({"dish_id": r["dish_id"], "name_uz": info.get("name_uz", "?"), "name_ru": info.get("name_ru", "?"),
                         "category_id": info.get("category_id", 0), "category_uz": info.get("category_uz", "?"), "category_ru": info.get("category_ru", "?"),
                         "quantity": r["quantity"], "revenue": r["revenue"], "cost": r["cost"], "share_percent": pct(r["revenue"], total),
                         "by_revenue": by_revenue[r["dish_id"]], "by_profit": by_profit[r["dish_id"]], "average_prep_minutes": r["prep"],
                         "profit": profit, "margin_percent": ZERO if r["revenue"] == 0 else rnd(profit / r["revenue"] * 100, 1)})
        rows.sort(key=lambda r: r["revenue"], reverse=True)
        categories = []
        for (cid, uz, ru), g in _group(rows, lambda r: (r["category_id"], r["category_uz"], r["category_ru"])).items():
            revenue = sum((r["revenue"] for r in g), ZERO)
            cost = sum((r["cost"] for r in g), ZERO)
            categories.append({"category_id": cid, "name_uz": uz, "name_ru": ru, "quantity": sum(r["quantity"] for r in g), "revenue": revenue,
                               "cost": cost, "share_percent": pct(revenue, total), "profit": revenue - cost})
        categories.sort(key=lambda c: c["revenue"], reverse=True)
        sold_set = set(sold)
        not_sold = sorted(({"dish_id": x["id"], "name_uz": x["name_uz"], "name_ru": x["name_ru"], "quantity": 0, "revenue": ZERO}
                           for x in dishes.values() if x["is_active"] and x["id"] not in sold_set), key=lambda x: x["name_uz"])
        prep_all = [_minutes(l.ready_at - l.sent_at) for l in d.lines if l.sent_at and l.ready_at]
        return {"filter": f.as_dict(), "dishes": rows, "categories": categories, "not_sold": not_sold,
                "average_prep_minutes": None if not prep_all else rnd(dec_from_double(sum(prep_all) / len(prep_all)), 1)}

    # ================= customers =================

    def customers(self, f: Filter) -> dict:
        d = self.load(f)
        start, _ = f.window()
        with_customer = [o for o in d.orders if o.customer_id is not None]
        ids = list(dict.fromkeys(o.customer_id for o in with_customer))
        earlier = set(m.Order.objects.filter(restaurant=self.r, status=m.OrderStatus.PAID, customer_sid__in=ids, paid_at__lt=start)
                      .values_list("customer_sid", flat=True))
        customers = {c.sid: c for c in m.Customer.objects.filter(restaurant=self.r, sid__in=ids)}
        rows = []
        for cid, g in _group(with_customer, lambda o: o.customer_id).items():
            c = customers.get(cid)
            revenue = sum((o.total for o in g), ZERO)
            rows.append({"customer_id": cid, "name": c.name if c else "?", "phone": c.phone if c else "", "orders": len(g), "revenue": revenue,
                         "average_check": avg(revenue, len(g)), "last_order_utc": max(o.paid_at for o in g), "is_new": cid not in earlier})
        rows.sort(key=lambda r: r["revenue"], reverse=True)
        delivery = [o for o in d.orders if o.type == m.OrderType.DELIVERY]
        users = self.user_names()
        couriers = sorted(({"courier_id": k, "name": users.get(k, "?") if k is not None else "-", "orders": len(g),
                            "revenue": sum((o.total for o in g), ZERO), "delivery_fees": sum((o.delivery_fee for o in g), ZERO)}
                           for k, g in _group(delivery, lambda o: o.courier_id).items()), key=lambda c: c["orders"], reverse=True)
        delivery_revenue = sum((o.total for o in delivery), ZERO)
        return {"filter": f.as_dict(), "customers": len(rows), "new_customers": sum(1 for r in rows if r["is_new"]),
                "returning_customers": sum(1 for r in rows if not r["is_new"]), "top": rows[:50], "delivery_orders": len(delivery),
                "delivery_revenue": delivery_revenue, "delivery_average_check": avg(delivery_revenue, len(delivery)), "couriers": couriers}

    # ================= control =================

    def control(self, f: Filter) -> dict:
        start, end = f.window()
        users, places = self.user_names(), self.places()
        cancelled_orders = list(self._cancelled_in(f).order_by("sid"))
        pks = [o.id for o in cancelled_orders]
        amounts, sent = defaultdict(lambda: ZERO), set()
        for l in m.OrderLine.objects.filter(order_id__in=pks).values("order_id", "quantity", "unit_price", "sent_to_kitchen"):
            amounts[l["order_id"]] += l["unit_price"] * l["quantity"]
            if l["sent_to_kitchen"]:
                sent.add(l["order_id"])
        noticed = set(m.KitchenNotice.objects.filter(restaurant=self.r, order_sid__in=[o.sid for o in cancelled_orders]).values_list("order_sid", flat=True))
        cancelled = []
        for o in cancelled_orders:
            at = o.cancelled_at or o.created_at
            cancelled.append({"order_id": o.sid, "cancelled_at_utc": at,
                              "table": (places.get(o.table_sid, {}).get("table", "?") if o.table_sid is not None else "-"),
                              "waiter": users.get(o.waiter_sid, "?"),
                              "cancelled_by": None if o.cancelled_by_sid is None else users.get(o.cancelled_by_sid, "?"),
                              "reason": o.cancel_reason, "amount": amounts[o.id], "was_sent_to_kitchen": o.id in sent or o.sid in noticed})
        cancelled.sort(key=lambda r: r["cancelled_at_utc"], reverse=True)

        d = self.load(f)
        discounts = sorted(({"waiter_id": w, "waiter": users.get(w, "?"), "orders": len(g), "discounts": sum((o.discount for o in g), ZERO)}
                            for w, g in _group([o for o in d.orders if o.discount > 0], lambda o: o.waiter_id).items()),
                           key=lambda r: r["discounts"], reverse=True)
        order_sids = list(self._filtered(f).values_list("sid", flat=True))
        removed = [{"order_id": n.order_sid, "created_at_utc": n.created_at, "name_uz": n.name_uz, "name_ru": n.name_ru, "quantity": n.quantity}
                   for n in m.KitchenNotice.objects.filter(restaurant=self.r, created_at__gte=start, created_at__lt=end, order_sid__in=order_sids)
                   .order_by("-created_at", "sid")]
        shifts = [s for s in self._shift_rows(f) if s["difference"] is not None and s["difference"] != 0]
        return {"filter": f.as_dict(), "cancelled": cancelled, "discounts": discounts, "removed_dishes": removed, "shift_differences": shifts}

    # ================= stock =================

    def stock(self, f: Filter) -> dict:
        start, end = f.window()
        rows = []
        for i in m.Ingredient.objects.filter(restaurant=self.r).order_by("name"):
            rows.append({"name": i.name, "unit": m.Unit(i.unit).label, "on_hand": i.quantity_on_hand, "min": i.min_quantity,
                         "cost_per_unit": i.cost_per_unit, "value": max(i.quantity_on_hand, ZERO) * i.cost_per_unit,
                         "is_low": i.quantity_on_hand <= i.min_quantity})
        waste = sum((-s.quantity * s.unit_cost for s in m.StockMovement.objects.filter(
            restaurant=self.r, type=m.StockMovementType.WASTE, created_at__gte=start, created_at__lt=end)), ZERO)
        return {"stock": rows, "waste_cost": rnd(waste, 0), "stock_value": sum((r["value"] for r in rows), ZERO)}


def abc(items) -> dict:
    """Sorted by value: the items making the first 80 % are A, the next 15 % B, the rest C (an item counts by where its share starts)."""
    ordered = sorted(items, key=lambda x: (-x[1], x[0]))
    total = sum((v for _, v in ordered if v > 0), ZERO)
    result, before = {}, ZERO
    for item_id, value in ordered:
        if value <= 0 or total == 0:
            result[item_id] = "C"
            continue
        start = before / total
        result[item_id] = "A" if start < Decimal("0.80") else "B" if start < Decimal("0.95") else "C"
        before += value
    return result


def _group(items, key) -> dict:
    """Like LINQ GroupBy: groups in order of first appearance."""
    groups: dict = {}
    for item in items:
        groups.setdefault(key(item), []).append(item)
    return groups
