"""
The restaurant's data as its server PC sends it (see the desktop's CloudSync.cs). Every row belongs to a restaurant
and keeps the desktop's own id in `sid`; links between rows are by those ids (`*_sid`), exactly as on the desktop.
Codes for choices are the desktop's enum numbers.
"""
from django.db import models

from apps.restaurants.models import Restaurant

MONEY = dict(max_digits=16, decimal_places=2)
QTY = dict(max_digits=16, decimal_places=3)
COST = dict(max_digits=16, decimal_places=4)
PCT = dict(max_digits=6, decimal_places=2)


class OrderStatus(models.IntegerChoices):
    OPEN = 0
    SENT_TO_KITCHEN = 1
    PAID = 2
    CANCELLED = 3


class OrderType(models.IntegerChoices):
    DINE_IN = 0, "DineIn"
    TAKEAWAY = 1, "Takeaway"
    DELIVERY = 2, "Delivery"


class PaymentMethod(models.IntegerChoices):
    CASH = 0, "Cash"
    CARD = 1, "Card"
    MIXED = 2, "Mixed"
    TRANSFER = 3, "Transfer"


class StockMovementType(models.IntegerChoices):
    RECEIPT = 0
    SALE = 1
    WASTE = 2
    ADJUSTMENT = 3


class Unit(models.IntegerChoices):
    PIECE = 0, "Piece"
    GRAM = 1, "Gram"
    MILLILITER = 2, "Milliliter"


class Synced(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    sid = models.IntegerField(help_text="Id in the restaurant's own database")

    class Meta:
        abstract = True
        constraints = []

    @classmethod
    def unique(cls, name):
        return models.UniqueConstraint(fields=["restaurant", "sid"], name=name)


class Role(Synced):
    name = models.CharField(max_length=60)

    class Meta:
        constraints = [Synced.unique("uniq_role")]


class Staff(Synced):
    full_name = models.CharField(max_length=120)
    role_sid = models.IntegerField()
    is_active = models.BooleanField(default=True)
    waiter_percent = models.DecimalField(default=0, **PCT)
    created_at = models.DateTimeField()

    class Meta:
        constraints = [Synced.unique("uniq_staff")]


class Hall(Synced):
    name = models.CharField(max_length=80)
    waiter_percent = models.DecimalField(null=True, **PCT)

    class Meta:
        constraints = [Synced.unique("uniq_hall")]


class DiningTable(Synced):
    hall_sid = models.IntegerField()
    name = models.CharField(max_length=40)
    seats = models.IntegerField(default=4)
    waiter_percent = models.DecimalField(null=True, **PCT)

    class Meta:
        constraints = [Synced.unique("uniq_table")]


class Category(Synced):
    name_uz = models.CharField(max_length=120)
    name_ru = models.CharField(max_length=120)
    sort_order = models.IntegerField(default=0)

    class Meta:
        constraints = [Synced.unique("uniq_category")]


class Dish(Synced):
    category_sid = models.IntegerField()
    name_uz = models.CharField(max_length=160)
    name_ru = models.CharField(max_length=160)
    price = models.DecimalField(**MONEY)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [Synced.unique("uniq_dish")]


class Ingredient(Synced):
    name = models.CharField(max_length=160)
    unit = models.IntegerField(choices=Unit.choices)
    quantity_on_hand = models.DecimalField(**QTY)
    min_quantity = models.DecimalField(**QTY)
    cost_per_unit = models.DecimalField(**COST)

    class Meta:
        constraints = [Synced.unique("uniq_ingredient")]


class RecipeLine(Synced):
    dish_sid = models.IntegerField()
    ingredient_sid = models.IntegerField()
    quantity_per_portion = models.DecimalField(**QTY)

    class Meta:
        constraints = [Synced.unique("uniq_recipe")]


class Customer(Synced):
    phone = models.CharField(max_length=20)
    name = models.CharField(max_length=160, blank=True)
    address = models.CharField(max_length=300, null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        constraints = [Synced.unique("uniq_customer")]


class Shift(Synced):
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True)
    opened_by_sid = models.IntegerField()
    closed_by_sid = models.IntegerField(null=True)
    opening_cash = models.DecimalField(**MONEY)
    counted_cash = models.DecimalField(null=True, **MONEY)
    note = models.TextField(null=True, blank=True)

    class Meta:
        constraints = [Synced.unique("uniq_shift")]


class Order(Synced):
    table_sid = models.IntegerField(null=True)
    waiter_sid = models.IntegerField()
    status = models.IntegerField(choices=OrderStatus.choices)
    created_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True)
    discount_percent = models.DecimalField(default=0, **PCT)
    payment_method = models.IntegerField(null=True, choices=PaymentMethod.choices)
    shift_sid = models.IntegerField(null=True)
    type = models.IntegerField(choices=OrderType.choices, default=OrderType.DINE_IN)
    customer_sid = models.IntegerField(null=True)
    delivery_fee = models.DecimalField(default=0, **MONEY)
    courier_sid = models.IntegerField(null=True)
    guests = models.IntegerField(null=True)
    waiter_percent = models.DecimalField(default=0, **PCT)
    waiter_earned = models.DecimalField(default=0, **MONEY)
    cancelled_at = models.DateTimeField(null=True)
    cancelled_by_sid = models.IntegerField(null=True)
    cancel_reason = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        constraints = [Synced.unique("uniq_order")]
        indexes = [
            models.Index(fields=["restaurant", "status", "paid_at"], name="order_paid_idx"),
            models.Index(fields=["restaurant", "status", "cancelled_at"], name="order_cancel_idx"),
        ]


class OrderLine(Synced):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    dish_sid = models.IntegerField()
    quantity = models.IntegerField()
    unit_price = models.DecimalField(**MONEY)
    sent_to_kitchen = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True)
    ready_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [Synced.unique("uniq_line")]


class Payment(Synced):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    method = models.IntegerField(choices=PaymentMethod.choices)
    amount = models.DecimalField(**MONEY)
    created_at = models.DateTimeField()
    shift_sid = models.IntegerField(null=True)

    class Meta:
        constraints = [Synced.unique("uniq_payment")]
        indexes = [models.Index(fields=["restaurant", "shift_sid"], name="payment_shift_idx")]


class StockMovement(Synced):
    ingredient_sid = models.IntegerField()
    quantity = models.DecimalField(**QTY)
    type = models.IntegerField(choices=StockMovementType.choices)
    unit_cost = models.DecimalField(**COST)
    created_at = models.DateTimeField()
    order_sid = models.IntegerField(null=True)

    class Meta:
        constraints = [Synced.unique("uniq_stock")]
        indexes = [models.Index(fields=["restaurant", "type", "order_sid"], name="stock_order_idx")]


class CashMovement(Synced):
    shift_sid = models.IntegerField()
    amount = models.DecimalField(**MONEY)
    created_at = models.DateTimeField()

    class Meta:
        constraints = [Synced.unique("uniq_cash")]


class KitchenNotice(Synced):
    order_sid = models.IntegerField()
    name_uz = models.CharField(max_length=160)
    name_ru = models.CharField(max_length=160)
    quantity = models.IntegerField()
    created_at = models.DateTimeField()

    class Meta:
        constraints = [Synced.unique("uniq_notice")]
