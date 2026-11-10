"""
Stores one batch from a restaurant (the JSON the desktop's CloudSyncBuilder sends). Applying the same batch twice
changes nothing: rows are matched on (restaurant, desktop id) and updated in place.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal

from django.db import transaction
from django.utils import timezone as dj_tz

from . import models as m

PROTOCOL = 1


class BatchError(ValueError):
    """The batch cannot be stored (wrong protocol, malformed)."""


def parse(raw: bytes | str) -> dict:
    try:
        data = json.loads(raw, parse_float=Decimal)
    except (ValueError, UnicodeDecodeError) as exc:
        raise BatchError("bad json") from exc
    if not isinstance(data, dict):
        raise BatchError("bad batch")
    return data


def _dt(value):
    """ISO time from the desktop (UTC, with or without "Z", up to 7 fraction digits)."""
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    if "." in text:
        head, rest = text.split(".", 1)
        digits = "".join(ch for ch in rest if ch.isdigit())
        tail = rest[len(digits):]
        text = f"{head}.{digits[:6]}{tail}"
    result = datetime.fromisoformat(text)
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def _d(value, default=Decimal(0)):
    return default if value is None else Decimal(str(value))


def _upsert(model, restaurant, rows, fields):
    """Insert new rows and update existing ones (matched on restaurant + desktop id)."""
    if not rows:
        return
    objs = [model(restaurant=restaurant, **row) for row in rows]
    model.objects.bulk_create(objs, update_conflicts=True, unique_fields=["restaurant", "sid"], update_fields=fields,
                              batch_size=1000)


def _fields(rows):
    return [k for k in rows[0] if k != "sid"] if rows else []


@transaction.atomic
def apply_batch(restaurant, data: dict) -> int:
    if data.get("Protocol") != PROTOCOL:
        raise BatchError("sync_protocol")

    ref = data.get("Reference")
    if ref:
        _apply_reference(restaurant, ref)

    customers = [dict(sid=c["Id"], phone=c.get("Phone", ""), name=c.get("Name", ""), address=c.get("Address"),
                      created_at=_dt(c["CreatedAt"])) for c in data.get("Customers") or []]
    _upsert(m.Customer, restaurant, customers, _fields(customers))

    shifts = [dict(sid=s["Id"], opened_at=_dt(s["OpenedAt"]), closed_at=_dt(s.get("ClosedAt")), opened_by_sid=s["OpenedById"],
                   closed_by_sid=s.get("ClosedById"), opening_cash=_d(s.get("OpeningCash")),
                   counted_cash=None if s.get("CountedCash") is None else _d(s["CountedCash"]), note=s.get("Note"))
              for s in data.get("Shifts") or []]
    _upsert(m.Shift, restaurant, shifts, _fields(shifts))

    orders = data.get("Orders") or []
    rows = [dict(sid=o["Id"], table_sid=o.get("TableId"), waiter_sid=o["WaiterId"], status=o["Status"],
                 created_at=_dt(o["CreatedAt"]), paid_at=_dt(o.get("PaidAt")), discount_percent=_d(o.get("DiscountPercent")),
                 payment_method=o.get("PaymentMethod"), shift_sid=o.get("ShiftId"), type=o.get("Type", 0),
                 customer_sid=o.get("CustomerId"), delivery_fee=_d(o.get("DeliveryFee")), courier_sid=o.get("CourierId"),
                 guests=o.get("Guests"), waiter_percent=_d(o.get("WaiterPercent")), waiter_earned=_d(o.get("WaiterEarned")),
                 cancelled_at=_dt(o.get("CancelledAt")), cancelled_by_sid=o.get("CancelledById"), cancel_reason=o.get("CancelReason"))
            for o in orders]
    _upsert(m.Order, restaurant, rows, _fields(rows))

    # An order arrives with all its lines and payments: replace what was stored.
    if orders:
        ids = dict(m.Order.objects.filter(restaurant=restaurant, sid__in=[o["Id"] for o in orders]).values_list("sid", "id"))
        m.OrderLine.objects.filter(restaurant=restaurant, order_id__in=ids.values()).delete()
        m.Payment.objects.filter(restaurant=restaurant, order_id__in=ids.values()).delete()
        m.OrderLine.objects.bulk_create([
            m.OrderLine(restaurant=restaurant, sid=line["Id"], order_id=ids[o["Id"]], dish_sid=line["DishId"],
                        quantity=line["Quantity"], unit_price=_d(line["UnitPrice"]), sent_to_kitchen=line.get("SentToKitchen", False),
                        sent_at=_dt(line.get("SentAt")), ready_at=_dt(line.get("ReadyAt")))
            for o in orders for line in o.get("Lines") or []], batch_size=1000)
        m.Payment.objects.bulk_create([
            m.Payment(restaurant=restaurant, sid=p["Id"], order_id=ids[o["Id"]], method=p["Method"], amount=_d(p["Amount"]),
                      created_at=_dt(p["CreatedAt"]), shift_sid=p.get("ShiftId"))
            for o in orders for p in o.get("Payments") or []], batch_size=1000)

    stock = [dict(sid=s["Id"], ingredient_sid=s["IngredientId"], quantity=_d(s["Quantity"]), type=s["Type"],
                  unit_cost=_d(s.get("UnitCost")), created_at=_dt(s["CreatedAt"]), order_sid=s.get("OrderId"))
             for s in data.get("StockMovements") or []]
    _upsert(m.StockMovement, restaurant, stock, _fields(stock))
    cash = [dict(sid=c["Id"], shift_sid=c["ShiftId"], amount=_d(c["Amount"]), created_at=_dt(c["CreatedAt"]))
            for c in data.get("CashMovements") or []]
    _upsert(m.CashMovement, restaurant, cash, _fields(cash))
    notices = [dict(sid=n["Id"], order_sid=n["OrderId"], name_uz=n.get("NameUz", ""), name_ru=n.get("NameRu", ""),
                    quantity=n["Quantity"], created_at=_dt(n["CreatedAt"])) for n in data.get("KitchenNotices") or []]
    _upsert(m.KitchenNotice, restaurant, notices, _fields(notices))

    restaurant.last_sync_at = dj_tz.now()
    restaurant.last_app_version = (data.get("AppVersion") or "")[:20]
    restaurant.save(update_fields=["last_sync_at", "last_app_version"])
    return len(orders)


def _apply_reference(restaurant, ref):
    roles = [dict(sid=r["Id"], name=r["Name"]) for r in ref.get("Roles") or []]
    staff = [dict(sid=u["Id"], full_name=u.get("FullName", ""), role_sid=u.get("RoleId", 0), is_active=u.get("IsActive", True),
                  waiter_percent=_d(u.get("WaiterPercent")), created_at=_dt(u.get("CreatedAt")) or dj_tz.now())
             for u in ref.get("Users") or []]
    halls = [dict(sid=h["Id"], name=h["Name"], waiter_percent=None if h.get("WaiterPercent") is None else _d(h["WaiterPercent"]))
             for h in ref.get("Halls") or []]
    tables = [dict(sid=t["Id"], hall_sid=t["HallId"], name=t["Name"], seats=t.get("Seats", 4),
                   waiter_percent=None if t.get("WaiterPercent") is None else _d(t["WaiterPercent"]))
              for t in ref.get("Tables") or []]
    categories = [dict(sid=c["Id"], name_uz=c.get("NameUz", ""), name_ru=c.get("NameRu", ""), sort_order=c.get("SortOrder", 0))
                  for c in ref.get("Categories") or []]
    dishes = [dict(sid=d["Id"], category_sid=d["CategoryId"], name_uz=d.get("NameUz", ""), name_ru=d.get("NameRu", ""),
                   price=_d(d.get("Price")), is_active=d.get("IsActive", True)) for d in ref.get("Dishes") or []]
    ingredients = [dict(sid=i["Id"], name=i["Name"], unit=i.get("Unit", 0), quantity_on_hand=_d(i.get("QuantityOnHand")),
                        min_quantity=_d(i.get("MinQuantity")), cost_per_unit=_d(i.get("CostPerUnit")))
                   for i in ref.get("Ingredients") or []]
    for model, rows in ((m.Role, roles), (m.Staff, staff), (m.Hall, halls), (m.DiningTable, tables),
                        (m.Category, categories), (m.Dish, dishes), (m.Ingredient, ingredients)):
        _upsert(model, restaurant, rows, _fields(rows))

    # Recipes are sent whole: replace them.
    m.RecipeLine.objects.filter(restaurant=restaurant).delete()
    m.RecipeLine.objects.bulk_create([
        m.RecipeLine(restaurant=restaurant, sid=r["Id"], dish_sid=r["DishId"], ingredient_sid=r["IngredientId"],
                     quantity_per_portion=_d(r["QuantityPerPortion"])) for r in ref.get("RecipeLines") or []])

    # Tables, halls, dishes and categories deleted in the restaurant (only possible while unused) go here too.
    keep = {t["sid"] for t in tables}
    used = set(m.Order.objects.filter(restaurant=restaurant, table_sid__isnull=False).values_list("table_sid", flat=True))
    m.DiningTable.objects.filter(restaurant=restaurant).exclude(sid__in=keep | used).delete()
    keep = {d["sid"] for d in dishes}
    used = set(m.OrderLine.objects.filter(restaurant=restaurant).values_list("dish_sid", flat=True))
    m.Dish.objects.filter(restaurant=restaurant).exclude(sid__in=keep | used).delete()
    keep = {h["sid"] for h in halls}
    used = set(m.DiningTable.objects.filter(restaurant=restaurant).values_list("hall_sid", flat=True))
    m.Hall.objects.filter(restaurant=restaurant).exclude(sid__in=keep | used).delete()
    keep = {c["sid"] for c in categories}
    used = set(m.Dish.objects.filter(restaurant=restaurant).values_list("category_sid", flat=True))
    m.Category.objects.filter(restaurant=restaurant).exclude(sid__in=keep | used).delete()
