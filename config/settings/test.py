"""Tests: an in-memory SQLite database, so they run anywhere without PostgreSQL rights."""
from .base import *  # noqa: F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]   # fast tests only
