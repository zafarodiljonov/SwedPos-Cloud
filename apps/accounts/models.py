"""People who log in to the website: restaurant owners and managers (and SwedPos staff as superusers)."""
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def normalize_phone(value: str | None) -> str | None:
    """"+998 90 123-45-67" / "901234567" -> "998901234567". None when it cannot be a phone number."""
    digits = "".join(ch for ch in (value or "") if ch.isascii() and ch.isdigit())
    if len(digits) == 9:
        digits = "998" + digits
    return digits if 11 <= len(digits) <= 15 else None


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, phone, password, **extra):
        number = normalize_phone(phone)
        if not number:
            raise ValidationError("phone_invalid")
        user = self.model(phone=number, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(phone, password, **extra)

    def create_superuser(self, phone, password=None, **extra):
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._create(phone, password, **extra)

    def get_by_natural_key(self, phone):
        return self.get(phone=normalize_phone(phone) or phone)


class User(AbstractBaseUser, PermissionsMixin):
    phone = models.CharField("phone", max_length=20, unique=True,
                             help_text="Digits with country code, e.g. 998901234567")
    full_name = models.CharField("name", max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="SwedPos staff: can open /admin/")
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        return f"{self.full_name or self.phone} (+{self.phone})"

    def clean(self):
        super().clean()
        number = normalize_phone(self.phone)
        if not number:
            raise ValidationError({"phone": "Enter a phone number with country code, e.g. +998 90 123 45 67"})
        self.phone = number
