from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.help import content


class HelpContentTests(TestCase):
    def test_every_language_has_topics_terms_and_no_app_only_topics(self):
        for lang in ("uz", "ru"):
            cats = content.categories(lang)
            ids = [t["id"] for c in cats for t in c["topics"]]
            self.assertIn("an_overview", ids)
            self.assertIn("web_start", ids)
            self.assertNotIn("kitchen_printers", ids)  # cash-desk topic, app only
            self.assertTrue(content.terms(lang))

    def test_every_report_page_has_its_help_topic(self):
        from apps.reports.builder import PAGES
        for key in PAGES:
            self.assertIsNotNone(content.topic("an_" + key, "uz"), key)

    def test_markup_is_rendered_and_escaped(self):
        html = content.render("## T\n\n- a **b**\n- <x>\n\n1. one\n2. two\n> note")
        self.assertIn("<h2>T</h2>", html)
        self.assertIn("<ul>", html)
        self.assertIn("<b>b</b>", html)
        self.assertIn("&lt;x&gt;", html)
        self.assertIn("<ol>", html)
        self.assertIn('<div class="note">note</div>', html)

    def test_search_finds_by_word(self):
        self.assertTrue(content.search("smena", "uz") or content.search("foyda", "uz"))
        self.assertEqual(content.search("qwertyxyz", "uz"), [])


class HelpPagesTests(TestCase):
    def test_login_is_required(self):
        response = self.client.get(reverse("help:index"))
        self.assertEqual(response.status_code, 302)

    def test_logged_in_user_reads_topics(self):
        user = User.objects.create_user(phone="+998900000001", password="x12345678")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("help:index")).status_code, 200)
        page = self.client.get(reverse("help:topic", args=["an_overview"]))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(self.client.get(reverse("help:topic", args=["kitchen_printers"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("help:index") + "?q=foyda").status_code, 200)
