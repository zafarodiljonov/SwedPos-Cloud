"""
The website must show exactly the numbers the restaurant sees. The fixtures were written by the desktop app itself:
golden_batch.json is a fixed week as the restaurant's server PC sends it, golden_expected.json is what the desktop's
AnalyticsService reports for it with several filters. Every field of every page is compared.
"""
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from django.test import TestCase

from apps.analytics.services import Analytics, Filter, abc
from apps.restaurants.models import Restaurant
from apps.sync.models import OrderType
from apps.sync.receiver import apply_batch, parse

FIXTURES = Path(__file__).parent / "fixtures"
TYPES = {"DineIn": OrderType.DINE_IN, "Takeaway": OrderType.TAKEAWAY, "Delivery": OrderType.DELIVERY}


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def compare(expected, actual, path, problems):
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            problems.append(f"{path}: expected an object, got {actual!r}")
            return
        for key, value in expected.items():
            k = snake(key)
            if k not in actual:
                problems.append(f"{path}.{k}: missing")
                continue
            compare(value, actual[k], f"{path}.{k}", problems)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            problems.append(f"{path}: expected {len(expected)} items, got {len(actual) if isinstance(actual, list) else actual!r}")
            return
        for i, (e, a) in enumerate(zip(expected, actual)):
            compare(e, a, f"{path}[{i}]", problems)
    elif isinstance(expected, bool) or expected is None:
        if expected != actual:
            problems.append(f"{path}: expected {expected!r}, got {actual!r}")
    elif isinstance(expected, (int, Decimal)):
        if actual is None or isinstance(actual, bool) or Decimal(str(expected)) != Decimal(str(actual)):
            problems.append(f"{path}: expected {expected}, got {actual!r}")
    elif isinstance(expected, str):
        if isinstance(actual, datetime):
            exp = datetime.fromisoformat(expected.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            ok = exp == actual
        elif isinstance(actual, date):
            ok = expected == actual.isoformat()
        else:
            ok = expected == actual
        if not ok:
            problems.append(f"{path}: expected {expected!r}, got {actual!r}")
    else:
        problems.append(f"{path}: cannot compare {expected!r}")


class GoldenTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.restaurant = Restaurant.objects.create(name="Golden", key_hash="x" * 64, key_prefix="x")
        apply_batch(cls.restaurant, parse((FIXTURES / "golden_batch.json").read_bytes()))
        cls.expected = json.loads((FIXTURES / "golden_expected.json").read_text(encoding="utf-8"), parse_float=Decimal)

    def check(self, name, expected, actual):
        problems = []
        compare(expected, actual, name, problems)
        self.assertEqual(problems, [], "\n" + "\n".join(problems[:40]))

    def filter_for(self, raw):
        return Filter(date.fromisoformat(raw["from"]), date.fromisoformat(raw["to"]), raw["hall"], raw["waiter"],
                      None if raw["type"] is None else TYPES[raw["type"]])

    def test_every_page_matches_the_desktop(self):
        a = Analytics(self.restaurant)
        for name, block in self.expected.items():
            if not isinstance(block, dict) or "filter" not in block:
                continue
            f = self.filter_for(block["filter"])
            with self.subTest(filter=name):
                self.check(f"{name}.overview", block["overview"], a.overview(f))
                self.check(f"{name}.sales", block["sales"], a.sales(f))
                self.check(f"{name}.payments", block["payments"], a.payments(f))
                self.check(f"{name}.waiters", block["waiters"], a.waiters(f))
                for waiter, rows in block["waiter_tables"].items():
                    self.check(f"{name}.waiter_tables.{waiter}", rows, a.waiter_tables(f, int(waiter)))
                self.check(f"{name}.tables", block["tables"], a.tables(f))
                self.check(f"{name}.products", block["products"], a.products(f))
                self.check(f"{name}.customers", block["customers"], a.customers(f))
                self.check(f"{name}.control", block["control"], a.control(f))
                stock = {k: block["stock"][k] for k in ("Stock", "WasteCost", "StockValue")}
                self.check(f"{name}.stock", stock, a.stock(f))

    def test_payroll_matches_the_desktop(self):
        a = Analytics(self.restaurant)
        self.check("payroll_2026_11", self.expected["payroll_2026_11"], a.payroll(2026, 11))
        self.check("payroll_2026_10", self.expected["payroll_2026_10"], a.payroll(2026, 10))

    def test_abc_matches_the_desktop(self):
        result = abc([(1, Decimal(50)), (2, Decimal(30)), (3, Decimal(10)), (4, Decimal(6)), (5, Decimal(4)), (6, Decimal(0))])
        self.assertEqual({str(k): v for k, v in result.items()}, self.expected["abc"])

    def test_sending_the_same_batch_again_changes_nothing(self):
        before = Analytics(self.restaurant).overview(Filter(date(2026, 11, 2), date(2026, 11, 8)))
        apply_batch(self.restaurant, parse((FIXTURES / "golden_batch.json").read_bytes()))
        after = Analytics(self.restaurant).overview(Filter(date(2026, 11, 2), date(2026, 11, 8)))
        self.assertEqual(before, after)
