"""The steps done at a new restaurant (USB guide, section 11): owner login, restaurant, key, first sync, owner sees it."""
import re
from pathlib import Path

from django.contrib.messages import get_messages
from django.test import TestCase

from apps.accounts.models import User
from apps.restaurants.models import Restaurant

GOLDEN = Path(__file__).resolve().parent.parent.parent / "analytics" / "tests" / "fixtures" / "golden_batch.json"


class NewRestaurantInTheAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(phone="998884945054", password="admin-pass-1", full_name="Zafar")
        self.client.force_login(self.admin)

    def add_owner(self):
        response = self.client.post("/admin/accounts/user/add/",
                                    {"phone": "+998 90 123-45-67", "full_name": "Owner", "password1": "owner-pass-1"})
        self.assertEqual(response.status_code, 302, response.content[:2000])
        return User.objects.get(phone="998901234567")

    def add_restaurant(self, owner):
        response = self.client.post("/admin/restaurants/restaurant/add/",
                                    {"name": "Maroqand", "users": [owner.pk], "is_active": "on"}, follow=True)
        self.assertEqual(response.status_code, 200)
        text = " ".join(str(m) for m in get_messages(response.wsgi_request)) or response.content.decode()
        key = re.search(r"spk_[A-Za-z0-9_\-]+", text).group(0)
        return Restaurant.objects.get(name="Maroqand"), key

    def test_owner_restaurant_key_sync_and_the_owner_sees_only_his_restaurant(self):
        owner = self.add_owner()
        self.assertTrue(owner.check_password("owner-pass-1"))
        self.assertFalse(owner.is_staff or owner.is_superuser)

        restaurant, key = self.add_restaurant(owner)
        test_restaurant = Restaurant(name="TEST - Zafar PC")
        test_restaurant.renew_key()
        test_restaurant.save()

        # SwedPos on the server PC sends with the key.
        response = self.client.post("/api/sync", data=GOLDEN.read_bytes(), content_type="application/json",
                                    HTTP_X_SWEDPOS_KEY=key)
        self.assertEqual(response.status_code, 200, response.content)
        restaurant.refresh_from_db()
        self.assertIsNotNone(restaurant.last_sync_at)

        # The owner logs in with the phone written any way and sees Maroqand, not the test restaurant.
        self.client.logout()
        response = self.client.post("/login/", {"username": "+998 90 123 45 67",
                                                "password": "owner-pass-1"})
        self.assertEqual(response.status_code, 302, response.content[:2000])
        self.assertEqual(list(Restaurant.visible_to(owner)), [restaurant])
        home = self.client.get("/", follow=True)
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "Maroqand")
        self.assertNotContains(home, "TEST - Zafar PC")
        self.assertEqual(self.client.get(f"/r/{test_restaurant.pk}/overview/").status_code, 404)
        self.assertEqual(self.client.get(f"/r/{restaurant.pk}/overview/").status_code, 200)

        # The owner cannot open the admin.
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_renewing_the_key_in_the_admin_stops_the_old_one(self):
        owner = self.add_owner()
        restaurant, old_key = self.add_restaurant(owner)
        response = self.client.post("/admin/restaurants/restaurant/",
                                    {"action": "renew_keys", "_selected_action": [restaurant.pk]}, follow=True)
        new_key = re.search(r"spk_[A-Za-z0-9_\-]+", " ".join(str(m) for m in get_messages(response.wsgi_request))).group(0)
        self.assertNotEqual(old_key, new_key)
        self.assertIsNone(Restaurant.by_key(old_key))
        self.assertEqual(Restaurant.by_key(new_key), restaurant)

    def test_the_admin_can_set_a_new_password_for_the_owner(self):
        owner = self.add_owner()
        response = self.client.post(f"/admin/accounts/user/{owner.pk}/password/",
                                    {"password1": "new-owner-pass-2", "password2": "new-owner-pass-2", "usable_password": "true"})
        self.assertEqual(response.status_code, 302, response.content[:2000])
        owner.refresh_from_db()
        self.assertTrue(owner.check_password("new-owner-pass-2"))
