# SwedPos Cloud: where is what

The owner website for SwedPos restaurants (Python Django + PostgreSQL). Read-only analytics in Uzbek and Russian, fed by the restaurant's server PC.

## Folders

| Folder | What is in it |
|---|---|
| `config/` | Django project: `settings/` (`base.py`, `dev.py`, `prod.py`, `test.py`), `urls.py`, `wsgi.py` |
| `apps/accounts` | Owner login: `models.py` (User with phone number), `forms.py` (phone login form), `admin.py` |
| `apps/restaurants` | `models.py` (Restaurant, sync key stored as hash, who may see it), `admin.py` (shows the key once) |
| `apps/sync` | What the restaurant sends: `models.py` (the copied data), `receiver.py` (stores a batch), `views.py` (`/api/sync`, `/api/ping`) |
| `apps/analytics` | `services.py` = the report calculations (port of the desktop's `AnalyticsService.cs`), `tests/` |
| `apps/reports` | The pages: `views.py`, `builder.py` (page content), `charts.py` (SVG), `excel.py`, `templatetags/`, `urls.py` |
| `apps/core` | `management/commands/seed_demo.py`, `demo/demo_batch.json.gz`, `context_processors.py` |
| `templates/`, `static/` | HTML (`reports/page.html`, `block.html`, `table.html`, `registration/login.html`), `css/app.css`, `js/app.js` |
| `locale/uz`, `locale/ru` | Texts (`django.po` generated from the desktop's `Loc.cs`, compiled `django.mo` committed) |
| `tools/` | `make_texts.py`, `compile_messages.py` (no gettext needed) |
| `deploy/` | `DJANGOEUROPE_SETUP.md`, `gunicorn-init.sh`; also `gunicorn.conf.py` in the root |

## Feature > files

| Feature | Files |
|---|---|
| Login with phone + password | `apps/accounts/models.py`, `forms.py`, `config/urls.py`, `templates/registration/login.html` |
| Add a restaurant, get its sync key | `apps/restaurants/admin.py` (Admin > Restaurants > Add), `models.py` |
| Receiving data from the desktop | `apps/sync/views.py` > `receiver.py` > `models.py` |
| Revenue, profit, waiters, payroll, payments, tables, dishes (ABC), customers, control, stock | `apps/analytics/services.py` (methods `overview`, `sales`, `payments`, `waiters`, `payroll`, `tables`, `products`, `customers`, `control`, `stock`) |
| What each page shows (tiles, charts, tables) | `apps/reports/builder.py` |
| Drawing charts | `apps/reports/charts.py` (line, bars), `templates/reports/block.html` (heat map, shares) |
| Filters, language switch, demo entry, Excel link | `apps/reports/views.py`, `templates/reports/page.html` |
| Excel download | `apps/reports/excel.py` (writes the same tables as the page) |
| Sorting a table, opening a waiter's tables | `static/js/app.js`, `apps/reports/views.py` (`detail`) |
| Look and phone layout | `static/css/app.css` |
| Uzbek / Russian texts | `locale/*/LC_MESSAGES/django.po` (do not edit by hand; run `tools/make_texts.py`) |
| Demo restaurant | `apps/core/management/commands/seed_demo.py` |

## Why the numbers equal the restaurant's
`apps/analytics/tests/test_golden.py` loads `fixtures/golden_batch.json` (a week written by the desktop) and compares every field of every page with `golden_expected.json` (what the desktop's C# code reports). Rounding follows C# (`Math.Round`, halves to even). If the desktop's analytics or sync format change: regenerate the files with `tools/CloudFixtures` in the desktop repo, copy them here, run the tests.

## Add a report page (example)
1. Add a method in `apps/analytics/services.py` (and the same in the desktop's `AnalyticsService.cs`).
2. Add `def mypage(self, f)` in `apps/reports/builder.py` and its name in `PAGES`, an icon in `ICONS`.
3. Add texts (`an_page_mypage`, `an_hint_mypage`) in the desktop's `Loc.cs`, run **texts: rebuild** task.
4. Regenerate the comparison data and run the tests.

## Run and debug in VS Code
- **F5** (Run and Debug > "Django: runserver") then open http://127.0.0.1:8000. Terminal > Run Task: **migrate**, **seed_demo**, **test**, **createsuperuser**, **texts: rebuild**.
- From a terminal: `.venv\Scripts\activate`, `python manage.py runserver`.
- Login: `+998 90 000 00 00` / `demo12345` after `seed_demo`, or your own superuser.
