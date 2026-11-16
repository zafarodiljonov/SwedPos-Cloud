import gzip
import shutil
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.backups import service
from apps.backups.models import BackupSettings


def fake_dump(out):
    out.write(b"-- fake dump\nCREATE TABLE t (id int);\n")


class BackupTests(TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        override = override_settings(BACKUP_DIR=self.folder)
        override.enable()
        self.addCleanup(override.disable)

    # ---- the schedule ----

    def test_the_default_is_weekly_and_the_schedule_decides_when_it_is_due(self):
        cfg = BackupSettings.load()
        self.assertEqual((cfg.frequency, cfg.keep), ("weekly", 8))
        now = timezone.now()

        self.assertTrue(service.is_due(cfg, now))                                   # never made: due
        cfg.last_success_at = now - timedelta(days=3)
        self.assertFalse(service.is_due(cfg, now))
        cfg.last_success_at = now - timedelta(days=6, hours=22)                     # the daily check is a bit early: still counts
        self.assertTrue(service.is_due(cfg, now))

        for frequency, days_ago, due in (("daily", 1, True), ("daily", 0, False), ("monthly", 29, False), ("monthly", 30, True),
                                         ("yearly", 300, False), ("yearly", 365, True), ("off", 9999, False)):
            cfg.frequency, cfg.last_success_at = frequency, now - timedelta(days=days_ago)
            self.assertEqual(service.is_due(cfg, now), due, (frequency, days_ago))

    # ---- making backups ----

    def test_a_backup_is_a_readable_gzip_file_and_the_result_is_recorded(self):
        path = service.run_backup(dump=fake_dump)

        self.assertEqual(path.parent, self.folder)
        self.assertRegex(path.name, r"^swedpos-\d{8}-\d{6}\.sql\.gz$")
        self.assertIn(b"CREATE TABLE", gzip.open(path).read())
        cfg = BackupSettings.load()
        self.assertIsNotNone(cfg.last_success_at)
        self.assertIn(path.name, cfg.last_message)
        self.assertEqual([p.name for p in self.folder.iterdir()], [path.name])      # no half-written ".part" left

    def test_only_the_newest_backups_are_kept(self):
        cfg = BackupSettings.load()
        cfg.keep = 3
        cfg.save()
        now = timezone.now()
        for i in range(5):
            service.run_backup(dump=fake_dump, now=now + timedelta(days=i))

        names = [name for name, _, _ in service.list_backups()]
        self.assertEqual(len(names), 3)
        self.assertEqual(names, sorted(names, reverse=True))                         # newest first
        self.assertIn(f"{timezone.localtime(now + timedelta(days=4)):%Y%m%d}", names[0])
        self.assertIn("deleted 1 old", BackupSettings.load().last_message)

    def test_a_failed_backup_leaves_nothing_behind_and_says_why(self):
        def broken(out):
            out.write(b"partial")
            raise service.BackupError("pg_dump failed: password authentication failed")

        with self.assertRaises(service.BackupError):
            service.run_backup(dump=broken)
        self.assertEqual(list(self.folder.iterdir()), [])
        cfg = BackupSettings.load()
        self.assertIsNone(cfg.last_success_at)
        self.assertIsNotNone(cfg.last_run_at)
        self.assertIn("password authentication failed", cfg.last_message)

    def test_without_postgresql_the_error_is_plain(self):
        with self.assertRaises(service.BackupError) as caught:
            service.run_backup()                                                      # the test database is SQLite
        self.assertIn("PostgreSQL", str(caught.exception))

    # ---- the daily check (cron) ----

    def test_the_daily_check_backs_up_only_when_due(self):
        out = StringIO()
        with mock.patch.object(service, "_pg_dump", fake_dump):
            call_command("backup_db", "--if-due", stdout=out)
            self.assertIn("Backup written", out.getvalue())
            self.assertEqual(len(service.list_backups()), 1)

            out = StringIO()
            call_command("backup_db", "--if-due", stdout=out)                         # a minute later: weekly, not due
            self.assertIn("Not due", out.getvalue())
            self.assertEqual(len(service.list_backups()), 1)

            cfg = BackupSettings.load()
            cfg.frequency = "daily"
            cfg.last_success_at = timezone.now() - timedelta(days=1, minutes=1)
            cfg.save()
            call_command("backup_db", "--if-due", stdout=StringIO())
            self.assertEqual(len(service.list_backups()), 2)

            cfg.frequency = "off"
            cfg.last_success_at = timezone.now() - timedelta(days=999)
            cfg.save()
            call_command("backup_db", "--if-due", stdout=StringIO())                   # off: never by schedule
            self.assertEqual(len(service.list_backups()), 2)
            call_command("backup_db", stdout=StringIO())                               # but by hand it works
            self.assertEqual(len(service.list_backups()), 3)

    def test_a_failure_in_the_command_is_an_error_for_cron(self):
        with self.assertRaises(CommandError):
            call_command("backup_db", stdout=StringIO())                               # SQLite: cannot dump


class BackupAdminTests(TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        override = override_settings(BACKUP_DIR=self.folder)
        override.enable()
        self.addCleanup(override.disable)
        self.admin = User.objects.create_superuser(phone="998884945054", password="admin-pass-1", full_name="Zafar")
        self.staff = User.objects.create_user(phone="998901112233", password="staff-pass-1", full_name="Staff", is_staff=True)
        self.client.force_login(self.admin)

    def test_the_settings_page_opens_and_saves_the_schedule(self):
        page = self.client.get("/admin/backups/backupsettings/", follow=True)
        self.assertContains(page, "Back up now")
        self.assertContains(page, "No backup yet.")

        response = self.client.post("/admin/backups/backupsettings/1/change/", {"frequency": "monthly", "keep": "12", "_save": "Save"}, follow=True)
        self.assertEqual(response.status_code, 200)
        cfg = BackupSettings.load()
        self.assertEqual((cfg.frequency, cfg.keep), ("monthly", 12))
        self.assertEqual(BackupSettings.objects.count(), 1)

    def test_back_up_now_makes_a_file_that_can_be_downloaded(self):
        with mock.patch.object(service, "_pg_dump", fake_dump):
            response = self.client.post("/admin/backups/backupsettings/run/", follow=True)
        self.assertContains(response, "Backup written")
        (name, _, _), = service.list_backups()
        self.assertContains(response, name)

        download = self.client.get(f"/admin/backups/backupsettings/download/{name}/")
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertIn(b"CREATE TABLE", gzip.decompress(b"".join(download.streaming_content)))

    def test_a_failed_backup_now_shows_the_reason(self):
        response = self.client.post("/admin/backups/backupsettings/run/", follow=True)   # SQLite in tests
        self.assertContains(response, "Backup failed")
        self.assertContains(response, "PostgreSQL")

    def test_only_real_backup_names_can_be_downloaded(self):
        (self.folder / "secret.txt").write_text("x")
        for name in ("secret.txt", "swedpos-20260101-000000.sql.gz"):
            self.assertEqual(self.client.get(f"/admin/backups/backupsettings/download/{name}/").status_code, 404, name)
        # A path that climbs out of the folder is not even a download address: nothing is served.
        climb = self.client.get("/admin/backups/backupsettings/download/..%2F..%2F.env/")
        self.assertIn(climb.status_code, (301, 302, 404))
        self.assertNotIn("Content-Disposition", climb)

    def test_other_staff_cannot_see_or_use_it(self):
        self.client.force_login(self.staff)
        self.assertNotIn(b"Database backup", self.client.get("/admin/").content)
        self.assertEqual(self.client.get("/admin/backups/backupsettings/1/change/").status_code, 403)
        with mock.patch.object(service, "_pg_dump", fake_dump):
            self.assertEqual(self.client.post("/admin/backups/backupsettings/run/").status_code, 404)
        self.assertEqual(service.list_backups(), [])
