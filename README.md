# SwedPos Cloud

The owner website for **SwedPos** restaurants: sales, waiters, waiter pay (percent), payments, tables, dishes,
customers, control and stock — from any phone or computer, in Uzbek and Russian. Read-only in version 1.

**Stack:** Django 5.2 · PostgreSQL · server-rendered pages with SVG charts · openpyxl for Excel · i18n UZ/RU.

The restaurant's **server PC** sends its data every minute (SwedPos desktop › Settings › SwedPos Cloud) to
`/api/sync`. Without internet nothing is lost; the next send catches up. PINs and passwords never leave the restaurant.

## How it fits together

```
SwedPos desktop (server PC)                         SwedPos Cloud (Django)
  CloudSyncAgent ── HTTPS POST /api/sync ──▶  apps/sync/receiver.py ─▶ tables in apps/sync/models.py
  (paid/cancelled orders, payments, shifts,     (every row: restaurant + the desktop's own id)
   stock, cash, menu, staff names)                         │
                                                            ▼
                         owner's browser ◀── apps/reports ◀── apps/analytics/services.py
```

- `apps/analytics/services.py` is a line-by-line port of the desktop's `AnalyticsService.cs`. The test
  `apps/analytics/tests/test_golden.py` loads a week produced by the desktop and compares **every field of every page**
  with the desktop's own results, so the website always shows the restaurant's numbers.
- Texts are the desktop's translations: `python tools/make_texts.py` (from `../src/SwedPos.App/Loc.cs`) then
  `python tools/compile_messages.py`. The compiled `.mo` files are committed.
- Restaurants, owners and sync keys are managed in `/admin/`. The key is shown once and stored only as a hash.

## Run it in VS Code

File > Open Folder > the `website` folder (or the `SwedPos.code-workspace` in the desktop folder, which shows both projects).
**F5** > "Django: runserver" then open http://127.0.0.1:8000. Terminal > Run Task: migrate, seed_demo, test, createsuperuser, texts.
Where is what: [docs/PROJECT_MAP.md](docs/PROJECT_MAP.md). To continue in a new chat: [HANDOFF.md](HANDOFF.md).

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements/dev.txt
copy .env.example .env            # optional: DATABASE_URL for PostgreSQL (without it a local SQLite file is used)
python manage.py migrate
python manage.py createsuperuser  # your login: phone number + password
python manage.py seed_demo        # demo restaurant with 60 days of sales up to today
python manage.py runserver
```

Open http://127.0.0.1:8000/ → "Demoni ochish", or log in with `+998 90 000 00 00` / `demo12345`.

PostgreSQL locally (as in the other projects, once in psql as the postgres superuser):
`CREATE ROLE swedpos_cloud LOGIN PASSWORD '...'; CREATE DATABASE swedpos_cloud OWNER swedpos_cloud;`
then `DATABASE_URL=postgres://swedpos_cloud:...@localhost:5432/swedpos_cloud` in `.env`.

## Tests

```bash
python manage.py test --settings=config.settings.test
```

## Deploy

Django Europe: see `deploy/DJANGOEUROPE_SETUP.md`.

## Regenerating the comparison data

`apps/analytics/tests/fixtures/*.json` and `apps/core/demo/demo_batch.json.gz` are written by a small tool that runs
the desktop's own code (fixed test week + expected reports, and the demo restaurant). Regenerate them when the
desktop's analytics change.

## Planned

- Changing settings from the website (menu prices, waiter percent), through a command queue the desktop pulls.
- Password reset by SMS (Eskiz.uz).
