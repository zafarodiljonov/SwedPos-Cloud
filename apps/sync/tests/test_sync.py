from pathlib import Path

from django.conf import settings
from django.test import TestCase

from apps.accounts.models import User, normalize_phone
from apps.restaurants.models import Restaurant
from apps.sync import models as m

GOLDEN = Path(__file__).resolve().parent.parent.parent / "analytics" / "tests" / "fixtures" / "golden_batch.json"


class SyncApiTests(TestCase):
    def setUp(self):
        self.restaurant = Restaurant(name="Marokand")
        self.key = self.restaurant.renew_key()
        self.restaurant.save()

    def post(self, body, key=None):
        return self.client.post("/api/sync", data=body, content_type="application/json", HTTP_X_SWEDPOS_KEY=key or self.key)

    def test_a_batch_with_the_right_key_is_stored(self):
        response = self.post(GOLDEN.read_bytes())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["orders"], 27)
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.last_app_version, "1.3.0")
        self.assertIsNotNone(self.restaurant.last_sync_at)
        self.assertEqual(m.Staff.objects.filter(restaurant=self.restaurant).exclude(full_name="").count(), 3)

    def test_wrong_key_old_key_and_bad_batches_are_refused(self):
        self.assertEqual(self.post(GOLDEN.read_bytes(), key="spk_wrong").status_code, 401)
        old = self.key
        self.restaurant.renew_key()
        self.restaurant.save()
        self.assertEqual(self.post(GOLDEN.read_bytes(), key=old).status_code, 401)
        new_key = self.restaurant.renew_key()
        self.restaurant.save()
        self.assertEqual(self.post(b"not json", key=new_key).status_code, 400)
        self.assertEqual(self.post(b'{"Protocol": 99}', key=new_key).status_code, 400)
        self.assertEqual(m.Order.objects.count(), 0)

    def test_the_key_is_stored_only_as_a_hash(self):
        self.assertNotIn(self.key, self.restaurant.key_hash)
        self.assertEqual(Restaurant.by_key(self.key), self.restaurant)

    def test_a_new_reset_id_deletes_the_old_data_once(self):
        import json
        self.assertEqual(self.post(GOLDEN.read_bytes()).status_code, 200)
        self.assertGreater(m.Order.objects.filter(restaurant=self.restaurant).count(), 0)
        dishes = m.Dish.objects.filter(restaurant=self.restaurant).count()

        # "clear sales": orders and shifts go, the menu stays
        empty = {"Protocol": 1, "AppVersion": "1.4.0", "Reset": {"Id": "r1", "Kind": "sales"}}
        self.assertEqual(self.post(json.dumps(empty)).status_code, 200)
        self.assertEqual(m.Order.objects.filter(restaurant=self.restaurant).count(), 0)
        self.assertEqual(m.Shift.objects.filter(restaurant=self.restaurant).count(), 0)
        self.assertEqual(m.Dish.objects.filter(restaurant=self.restaurant).count(), dishes)

        # the same reset id again (the next batches) deletes nothing
        self.assertEqual(self.post(GOLDEN.read_bytes()).status_code, 200)
        self.assertEqual(self.post(json.dumps(empty)).status_code, 200)
        self.assertGreater(m.Order.objects.filter(restaurant=self.restaurant).count(), 0)

        # "factory reset": the menu goes too
        everything = {"Protocol": 1, "AppVersion": "1.4.0", "Reset": {"Id": "r2", "Kind": "all"}}
        self.assertEqual(self.post(json.dumps(everything)).status_code, 200)
        self.assertEqual(m.Order.objects.filter(restaurant=self.restaurant).count(), 0)
        self.assertEqual(m.Dish.objects.filter(restaurant=self.restaurant).count(), 0)
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.last_reset_id, "r2")

    def test_ping(self):
        self.assertEqual(self.client.get("/api/ping").json()["protocol"], 1)


class PagesTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("+998 90 111 22 33", "secret-pass-1", full_name="Owner")
        self.other = User.objects.create_user("998901112244", "secret-pass-2", full_name="Other")
        self.restaurant = Restaurant(name="Marokand")
        key = self.restaurant.renew_key()
        self.restaurant.save()
        self.restaurant.users.add(self.owner)
        self.client.post("/api/sync", data=GOLDEN.read_bytes(), content_type="application/json", HTTP_X_SWEDPOS_KEY=key)

    def test_phone_numbers_are_stored_as_digits(self):
        self.assertEqual(normalize_phone("+998 90 123-45-67"), "998901234567")
        self.assertEqual(normalize_phone("901234567"), "998901234567")
        self.assertIsNone(normalize_phone("12345"))
        self.assertEqual(self.owner.phone, "998901112233")

    def test_owner_logs_in_with_phone_and_sees_every_page_in_both_languages(self):
        response = self.client.post("/login/", {"username": "90 111 22 33", "password": "secret-pass-1"})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/"), f"/r/{self.restaurant.pk}/overview/", fetch_redirect_response=False)
        week = "?from=2026-11-02&to=2026-11-08"
        for lang in ("uz", "ru"):
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = lang
            for page in ("overview", "sales", "payments", "waiters", "payroll", "tables", "products", "customers", "control", "stock"):
                with self.subTest(lang=lang, page=page):
                    response = self.client.get(f"/r/{self.restaurant.pk}/{page}/{week}&month=2026-11-01")
                    self.assertEqual(response.status_code, 200)
            response = self.client.get(f"/r/{self.restaurant.pk}/overview/{week}")
            self.assertContains(response, "1 577 000")   # the week's revenue, same as the desktop
        export = self.client.get(f"/r/{self.restaurant.pk}/waiters/export/{week}")
        self.assertEqual(export["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        waiter = m.Staff.objects.get(restaurant=self.restaurant, full_name="Aziz").sid
        self.assertContains(self.client.get(f"/r/{self.restaurant.pk}/detail/waiter/{waiter}/{week}"), "Aziz")

    def test_wrong_password_and_other_peoples_restaurants(self):
        response = self.client.post("/login/", {"username": "998901112233", "password": "wrong-pass"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertRedirects(self.client.get(f"/r/{self.restaurant.pk}/overview/"), f"/login/?next=/r/{self.restaurant.pk}/overview/",
                             fetch_redirect_response=False)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f"/r/{self.restaurant.pk}/overview/").status_code, 404)
        self.assertEqual(self.client.get(f"/r/{self.restaurant.pk}/overview/export/").status_code, 404)

    def test_language_switch_stays_on_this_site(self):
        response = self.client.get("/lang/ru/?next=https://evil.example/")
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, "ru")
