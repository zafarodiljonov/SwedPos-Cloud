"""
Loads the demo restaurant: 60 days of made-up sales, produced by the desktop app itself and stored exactly as a
restaurant would send them (apps/core/demo/demo_batch.json.gz). The days are moved so the last one is today.
Log in with phone +998 90 000 00 00 and password demo12345, or open /demo/.

    python manage.py seed_demo
"""
import gzip
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from apps.accounts.models import User
from apps.reports.views import DEMO_PASSWORD, DEMO_PHONE
from apps.restaurants.models import Restaurant
from apps.sync import models as m
from apps.sync.receiver import apply_batch, parse

DEMO_FILE = Path(__file__).resolve().parent.parent.parent / "demo" / "demo_batch.json.gz"
DATE_FIELDS = {
    m.Staff: ["created_at"], m.Customer: ["created_at"], m.Shift: ["opened_at", "closed_at"],
    m.Order: ["created_at", "paid_at", "cancelled_at"], m.OrderLine: ["sent_at", "ready_at"], m.Payment: ["created_at"],
    m.StockMovement: ["created_at"], m.CashMovement: ["created_at"], m.KitchenNotice: ["created_at"],
}


class Command(BaseCommand):
    help = "Load (or reload) the demo restaurant with 60 days of sales up to today."

    @transaction.atomic
    def handle(self, *args, **options):
        Restaurant.objects.filter(is_demo=True).delete()
        restaurant = Restaurant(name="Marokand (demo)", is_demo=True)
        restaurant.renew_key()
        restaurant.save()
        apply_batch(restaurant, parse(gzip.decompress(DEMO_FILE.read_bytes())))

        last = m.Order.objects.filter(restaurant=restaurant).aggregate(last=Max("paid_at"))["last"]
        shift = timedelta(days=(timezone.localdate() - timezone.localtime(last).date()).days)
        if shift:
            for model, fields in DATE_FIELDS.items():
                model.objects.filter(restaurant=restaurant).update(**{f: F(f) + shift for f in fields})
        restaurant.last_sync_at = timezone.now()
        restaurant.save(update_fields=["last_sync_at"])

        user = User.objects.filter(phone=DEMO_PHONE).first() or User.objects.create_user(DEMO_PHONE, DEMO_PASSWORD, full_name="Demo")
        user.set_password(DEMO_PASSWORD)
        user.save()
        restaurant.users.add(user)
        orders = m.Order.objects.filter(restaurant=restaurant).count()
        self.stdout.write(self.style.SUCCESS(f"Demo restaurant {restaurant.pk} loaded: {orders} orders, moved {shift.days} days. "
                                             f"Log in: +998 90 000 00 00 / {DEMO_PASSWORD}  (or /demo/)"))
