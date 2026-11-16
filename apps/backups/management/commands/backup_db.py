from django.core.management.base import BaseCommand, CommandError

from apps.backups import service
from apps.backups.models import BackupSettings


class Command(BaseCommand):
    help = "Backs up the database. With --if-due only when the schedule (/admin/ > Database backup) says so: run this every day from cron."

    def add_arguments(self, parser):
        parser.add_argument("--if-due", action="store_true", help="make a backup only when the schedule says it is due")

    def handle(self, *args, **options):
        cfg = BackupSettings.load()
        if options["if_due"] and not service.is_due(cfg):
            self.stdout.write(f"Not due yet (schedule: {cfg.frequency}). Nothing done.")
            return
        try:
            path = service.run_backup()
        except service.BackupError as error:
            raise CommandError(str(error))
        self.stdout.write(self.style.SUCCESS(f"Backup written: {path}"))
