from datetime import date, timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import get_language
from django.utils.translation import gettext as T
from django.views.decorators.http import require_GET

from apps.analytics.services import Filter
from apps.restaurants.models import Restaurant
from apps.sync import models as m

from . import excel
from .builder import ICONS, PAGES, Builder

TYPES = {"dinein": m.OrderType.DINE_IN, "takeaway": m.OrderType.TAKEAWAY, "delivery": m.OrderType.DELIVERY}


def _presets(today: date):
    month = today.replace(day=1)
    last_month = (month - timedelta(days=1)).replace(day=1)
    return [("today", "report_today", today, today), ("yesterday", "report_yesterday", today - timedelta(days=1), today - timedelta(days=1)),
            ("7d", "report_7days", today - timedelta(days=6), today), ("30d", "an_30days", today - timedelta(days=29), today),
            ("month", "report_month", month, today), ("lastmonth", "an_last_month", last_month, month - timedelta(days=1)),
            ("year", "an_year", today.replace(month=1, day=1), today)]


def _date(text):
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def _int(text):
    return int(text) if text and text.isdigit() else None


def _state(request):
    """The filter in the address: ?p=7d or ?from=…&to=…, plus hall, waiter, type and the payroll month."""
    q = request.GET
    today = timezone.localdate()
    presets = _presets(today)
    preset = q.get("p") if q.get("p") in {p[0] for p in presets} else None
    start, end = _date(q.get("from")), _date(q.get("to"))
    if preset or not (start and end and start <= end):
        preset = preset or "7d"
        _, _, start, end = next(p for p in presets if p[0] == preset)
    month = _date(q.get("month")) or today.replace(day=1)
    f = Filter(start, end, _int(q.get("hall")), _int(q.get("waiter")), TYPES.get(q.get("type")))
    return {"filter": f, "preset": preset if not (q.get("from") and q.get("to") and not q.get("p")) else None,
            "month": month.replace(day=1), "presets": presets, "type": q.get("type", "")}


def _query(state, **changes):
    f = state["filter"]
    values = {"from": f.from_.isoformat(), "to": f.to.isoformat(), "hall": f.hall_id or "", "waiter": f.waiter_id or "",
              "type": state["type"], "month": state["month"].isoformat()}
    values.update(changes)
    return urlencode({k: v for k, v in values.items() if v not in ("", None)})


def _restaurant(request, rid):
    return get_object_or_404(Restaurant.visible_to(request.user), pk=rid)


@login_required
def home(request):
    first = Restaurant.visible_to(request.user).first()
    if first is None:
        return render(request, "reports/no_restaurant.html")
    return redirect("reports:page", rid=first.pk, page="overview")


@login_required
def page(request, rid, page="overview"):
    if page not in PAGES:
        raise Http404
    restaurant = _restaurant(request, rid)
    state = _state(request)
    f = state["filter"]
    builder = Builder(restaurant, get_language())
    blocks = builder.build(page, f, state["month"])

    halls = list(m.Hall.objects.filter(restaurant=restaurant).order_by("name").values_list("sid", "name"))
    waiter_ids = m.Order.objects.filter(restaurant=restaurant).values_list("waiter_sid", flat=True).distinct()
    waiters = list(m.Staff.objects.filter(restaurant=restaurant, sid__in=waiter_ids).order_by("full_name").values_list("sid", "full_name"))
    period = builder.month_name(state["month"]) if page == "payroll" else (
        f.from_.strftime("%d.%m.%Y") if f.from_ == f.to else
        f"{f.from_.strftime('%d.%m.%Y')} — {f.to.strftime('%d.%m.%Y')}  ({f.days} {T('an_days')})")
    sync_fresh = restaurant.last_sync_at is not None and timezone.now() - restaurant.last_sync_at < timedelta(minutes=10)
    return render(request, "reports/page.html", {
        "restaurant": restaurant, "restaurants": Restaurant.visible_to(request.user), "page": page,
        "pages": [(p, T("an_page_" + p), ICONS[p]) for p in PAGES], "blocks": blocks,
        "title": T("an_page_" + page), "hint": T("an_hint_" + page), "period": period, "sync_fresh": sync_fresh,
        "presets": [(key, T(label), f"?{_query(state, **{'from': s.isoformat(), 'to': e.isoformat()})}&p={key}") for key, label, s, e in state["presets"]],
        "preset": state["preset"], "f": f, "state": state, "halls": halls, "waiters": waiters,
        "export_url": f"export/?{_query(state)}", "query": _query(state),
    })


@login_required
def detail(request, rid, kind, key):
    """The table-by-table card for one waiter (opened by clicking a row)."""
    restaurant = _restaurant(request, rid)
    state = _state(request)
    builder = Builder(restaurant, get_language())
    block = builder.waiter_detail(state["filter"], key, state["month"] if kind == "payroll" else None)
    return render(request, "reports/block.html", {"block": block})


@login_required
def export(request, rid, page):
    if page not in PAGES:
        raise Http404
    restaurant = _restaurant(request, rid)
    state = _state(request)
    f = state["filter"]
    builder = Builder(restaurant, get_language())
    builder.build(page, f, state["month"])
    if page == "payroll":
        period, stamp = builder.month_name(state["month"]), state["month"].strftime("%Y-%m")
    else:
        period = f"{f.from_.strftime('%d.%m.%Y')} — {f.to.strftime('%d.%m.%Y')}"
        stamp = f"{f.from_.isoformat()}_{f.to.isoformat()}"
    data = excel.workbook(f"SwedPos · {T('an_page_' + page)}", period, builder.tables)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="SwedPos_{page}_{stamp}.xlsx"'
    return response


@require_GET
def language(request, code):
    """UZ / RU switch: remembers the choice and goes back to the same page."""
    target = request.GET.get("next") or "/"
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        target = "/"
    response = redirect(target)
    if code in dict(settings.LANGUAGES):
        response.set_cookie(settings.LANGUAGE_COOKIE_NAME, code, max_age=365 * 24 * 3600, samesite="Lax")
    return response

