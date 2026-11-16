"""Making, listing and pruning the database backups (pg_dump into a compressed file in the backup folder)."""
import gzip
import os
import re
import shutil
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import BackupSettings

# A month is 30 days and a year 365: "about that often" is all a backup schedule needs.
PERIODS = {"daily": timedelta(days=1), "weekly": timedelta(days=7), "monthly": timedelta(days=30), "yearly": timedelta(days=365)}
# The cron job runs once a day at about the same time; a few hours of slack stop a backup being skipped by a few minutes.
SLACK = timedelta(hours=4)
NAME = re.compile(r"^swedpos-\d{8}-\d{6}\.sql\.gz$")


class BackupError(Exception):
    pass


def backup_dir() -> Path:
    return Path(getattr(settings, "BACKUP_DIR", Path.home() / "backups"))


def is_due(cfg: BackupSettings, now=None) -> bool:
    """True when the schedule says a backup should be made now (never made yet counts as due)."""
    period = PERIODS.get(cfg.frequency)
    if period is None:
        return False
    if cfg.last_success_at is None:
        return True
    return (now or timezone.now()) - cfg.last_success_at >= period - SLACK


def list_backups():
    """[(name, size in bytes, time)] newest first."""
    folder = backup_dir()
    if not folder.is_dir():
        return []
    files = [p for p in folder.iterdir() if NAME.match(p.name)]
    files.sort(key=lambda p: p.name, reverse=True)
    return [(p.name, p.stat().st_size, timezone.datetime.fromtimestamp(p.stat().st_mtime, timezone.get_current_timezone())) for p in files]


def prune(keep: int) -> int:
    """Deletes the oldest backups beyond the newest <keep>. Returns how many were deleted."""
    names = [name for name, _, _ in list_backups()]
    removed = 0
    for name in names[max(keep, 1):]:
        (backup_dir() / name).unlink(missing_ok=True)
        removed += 1
    return removed


def _pg_dump(out) -> None:
    """Writes the SQL dump of this site's PostgreSQL database to the binary file <out>."""
    db = settings.DATABASES["default"]
    if "postgresql" not in db["ENGINE"]:
        raise BackupError("Backups need the PostgreSQL database; this site runs on " + db["ENGINE"].rsplit(".", 1)[-1] + ".")
    command = ["pg_dump", "-h", db.get("HOST") or "127.0.0.1", "-U", db["USER"], "-d", db["NAME"]]
    if db.get("PORT"):
        command += ["-p", str(db["PORT"])]
    env = dict(os.environ, PGPASSWORD=db.get("PASSWORD") or "")
    with tempfile.TemporaryFile() as errors:
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, env=env)
        except FileNotFoundError:
            raise BackupError("pg_dump was not found on this server.")
        shutil.copyfileobj(process.stdout, out)
        process.wait(timeout=900)
        if process.returncode != 0:
            errors.seek(0)
            raise BackupError("pg_dump failed: " + errors.read().decode("utf-8", "replace").strip()[:200])


def run_backup(dump=None, now=None) -> Path:
    """
    Makes one backup file now, keeps only the newest <keep>, and records the result in the settings.
    <dump> (for tests) writes the dump into the file it is given; by default pg_dump does.
    """
    cfg = BackupSettings.load()
    now = now or timezone.now()
    folder = backup_dir()
    stamp = now
    while (folder / f"swedpos-{timezone.localtime(stamp):%Y%m%d-%H%M%S}.sql.gz").exists():
        stamp += timedelta(seconds=1)              # two backups in the same second never overwrite each other
    final = folder / f"swedpos-{timezone.localtime(stamp):%Y%m%d-%H%M%S}.sql.gz"
    part = final.with_name(final.name + ".part")
    cfg.last_run_at = now
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with gzip.open(part, "wb") as out:
            (dump or _pg_dump)(out)
        part.replace(final)
    except BackupError as error:
        part.unlink(missing_ok=True)
        cfg.last_message = str(error)[:300]
        cfg.save()
        raise
    except Exception as error:      # disk full, no rights on the folder ...
        part.unlink(missing_ok=True)
        cfg.last_message = f"{type(error).__name__}: {error}"[:300]
        cfg.save()
        raise BackupError(cfg.last_message) from error

    removed = prune(cfg.keep)
    cfg.last_success_at = now
    cfg.last_message = f"OK: {final.name}" + (f" (deleted {removed} old)" if removed else "")
    cfg.save()
    return final
