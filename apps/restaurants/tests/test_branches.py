"""One owner, several restaurants (branches): the switcher, the remembered branch, and who sees what."""
from django.test import TestCase

from apps.accounts.models import User
from apps.restaurants.models import Restaurant


class BranchSwitcherTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(phone="998901234567", password="owner-pass-1", full_name="Owner")
        self.other = User.objects.create_user(phone="998909999999", password="other-pass-1", full_name="Other")
        self.a = Restaurant.objects.create(name="Maroqand", address="Registon 5", key_hash="A" * 64, key_prefix="spk_a")
        self.b = Restaurant.objects.create(name="Maroqand 2", address="Amir Temur 12", key_hash="B" * 64, key_prefix="spk_b")
        self.c = Restaurant.objects.create(name="Somebody else", key_hash="C" * 64, key_prefix="spk_c")
        self.a.users.add(self.owner)
        self.b.users.add(self.owner)
        self.c.users.add(self.other)
        self.client.force_login(self.owner)

    def test_the_owner_sees_both_branches_with_addresses_and_never_the_others(self):
        page = self.client.get(f"/r/{self.a.pk}/overview/?from=2026-11-01&to=2026-11-07")
        self.assertContains(page, "Maroqand 2")
        self.assertContains(page, "Amir Temur 12")
        self.assertContains(page, 'class="branches"')
        self.assertNotContains(page, "Somebody else")

        self.assertEqual(self.client.get(f"/r/{self.c.pk}/overview/").status_code, 404)

    def test_switching_keeps_the_period_but_drops_hall_and_waiter(self):
        page = self.client.get(f"/r/{self.a.pk}/sales/?from=2026-11-01&to=2026-11-07&hall=3&waiter=9")
        self.assertContains(page, f'href="/r/{self.b.pk}/sales/?from=2026-11-01&amp;to=2026-11-07&amp;month=2026-11-01"')
        self.assertNotContains(page, f'href="/r/{self.b.pk}/sales/?from=2026-11-01&amp;to=2026-11-07&amp;hall')
        self.assertNotContains(page, f'href="/r/{self.b.pk}/sales/?from=2026-11-01&amp;to=2026-11-07&amp;waiter')

    def test_the_last_branch_is_opened_next_time(self):
        self.client.get(f"/r/{self.b.pk}/overview/")
        home = self.client.get("/")
        self.assertRedirects(home, f"/r/{self.b.pk}/overview/", fetch_redirect_response=False)

        # A branch that is no longer his is forgotten.
        self.b.users.remove(self.owner)
        home = self.client.get("/")
        self.assertRedirects(home, f"/r/{self.a.pk}/overview/", fetch_redirect_response=False)

    def test_an_owner_with_one_restaurant_gets_no_switcher(self):
        self.client.force_login(self.other)
        page = self.client.get(f"/r/{self.c.pk}/overview/")
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'class="branches"')
        self.assertContains(page, "Somebody else")

    def test_a_branch_is_added_in_the_admin_for_the_same_owner(self):
        admin = User.objects.create_superuser(phone="998884945054", password="admin-pass-1", full_name="Zafar")
        self.client.force_login(admin)
        response = self.client.post("/admin/restaurants/restaurant/add/", {
            "name": "Maroqand 3", "address": "Sharof Rashidov 40", "users": [self.owner.pk], "is_active": "on"}, follow=True)
        self.assertEqual(response.status_code, 200)
        third = Restaurant.objects.get(name="Maroqand 3")
        self.assertEqual(third.address, "Sharof Rashidov 40")
        self.assertEqual(list(third.users.all()), [self.owner])
        self.assertContains(response, "spk_")          # its own sync key, shown once

        self.client.force_login(self.owner)
        page = self.client.get(f"/r/{self.a.pk}/overview/")
        self.assertContains(page, "Maroqand 3")
        self.assertContains(page, "Sharof Rashidov 40")

        listing = self.client.force_login(admin) or self.client.get("/admin/restaurants/restaurant/")
        self.assertContains(listing, "Owner")           # the "Owners" column
