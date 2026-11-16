from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class BackupSettings(models.Model):
    """
    How often the site's database is backed up (one row, edited in /admin/ > Database backup).
    A cron job runs `manage.py backup_db --if-due` every day; the backup is only made when this schedule says it is due.
    """
    FREQUENCIES = [
        ("off", "Off (only when I press Back up now)"),
        ("daily", "Every day"),
        ("weekly", "Every week"),
        ("monthly", "Every month"),
        ("yearly", "Every year"),
    ]
    frequency = models.CharField(max_length=10, choices=FREQUENCIES, default="weekly")
    keep = models.PositiveSmallIntegerField(
        default=8, validators=[MinValueValidator(1), MaxValueValidator(200)],
        help_text="How many of the newest backups are kept; older ones are deleted when a new one is made.")
    last_run_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_success_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_message = models.CharField(max_length=300, blank=True, editable=False)

    class Meta:
        verbose_name = "database backup"
        verbose_name_plural = "database backup"

    def __str__(self):
        return "Database backup"

    def save(self, *args, **kwargs):
        self.pk = 1          # always the same single row
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]
