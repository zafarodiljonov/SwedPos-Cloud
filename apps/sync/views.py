"""The address the restaurant's server PC sends to (SwedPos › Settings › SwedPos Cloud)."""
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.restaurants.models import Restaurant

from .receiver import PROTOCOL, BatchError, apply_batch, parse

log = logging.getLogger("apps.sync")


@require_GET
def ping(request):
    return JsonResponse({"service": "SwedPos Cloud", "protocol": PROTOCOL})


@csrf_exempt
@require_POST
def sync(request):
    restaurant = Restaurant.by_key(request.headers.get("X-SwedPos-Key"))
    if restaurant is None:
        return JsonResponse({"error": "unknown key"}, status=401)
    try:
        orders = apply_batch(restaurant, parse(request.body))
    except BatchError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception:
        log.exception("Sync from restaurant %s failed", restaurant.pk)
        return JsonResponse({"error": "could not store the batch"}, status=500)
    return JsonResponse({"ok": True, "orders": orders})
