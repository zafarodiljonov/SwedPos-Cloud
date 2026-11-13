"""A restaurant connected to SwedPos Cloud, its sync key and who may see it."""
import hashlib
import secrets

from django.conf import settings
from django.db import models


def new_sync_key() -> str:
    return "spk_" + secrets.token_urlsafe(30)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest().upper()


class Restaurant(models.Model):
    name = models.CharField(max_length=120)
    # The key itself is shown once (when created or renewed) and never stored.
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    key_prefix = models.CharField(max_length=12, editable=False, help_text="First characters of the key, to recognise it")
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="restaurants",
                                   help_text="Owners and managers who may see this restaurant")
    is_active = models.BooleanField(default=True)
    is_demo = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_sync_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_app_version = models.CharField(max_length=20, blank=True, editable=False)
    # The last "start from zero" done in the restaurant (SwedPos > Settings > Reset). A new id in a batch
    # makes the website delete the same data before storing the batch.
    last_reset_id = models.CharField(max_length=40, blank=True, editable=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def renew_key(self) -> str:
        """A new key; the old one stops working at once. Returns the key (show it once)."""
        key = new_sync_key()
        self.key_hash = hash_key(key)
        self.key_prefix = key[:10]
        return key

    @classmethod
    def by_key(cls, key: str | None):
        if not key or not key.strip():
            return None
        return cls.objects.filter(key_hash=hash_key(key), is_active=True).first()

    @classmethod
    def visible_to(cls, user):
        qs = cls.objects.filter(is_active=True)
        return qs if user.is_superuser else qs.filter(users=user)
