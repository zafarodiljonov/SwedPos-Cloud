# SwedPos Cloud: session handoff

Paste everything below the line into a new Claude Code chat to continue with full context. Keep it up to date when the project state changes.

Last updated: 2026-11-10 · `main`

---

I'm continuing work on **SwedPos Cloud**, the owner website for my restaurant POS **SwedPos** (the desktop app lives in `C:\Users\odijo\Desktop\swedpos_restaurants`, separate repo). Stack: **Django 5.2 + PostgreSQL**, Python 3.12, hosted on my **Django Europe** plan. Read this whole message first, then `docs/PROJECT_MAP.md`.

### Hard rules
1. **Every Django command runs as** `PYTHONUTF8=1 ./.venv/Scripts/python.exe manage.py <cmd>` (Windows cp1252 crashes on Cyrillic otherwise). VS Code tasks already do this.
2. **I run the dev server myself** in VS Code at `127.0.0.1:8000` (F5 or `python manage.py runserver`). Check port 8000 before starting one; stop yours when done.
3. **Never modify my other projects** `erp_wms`, `homnet`, `ind_ref_pro` (reading for reference is fine; this project is set up like `erp_wms`: settings split, `.env`, gunicorn init script, WhiteNoise).
4. **Passwords/tokens:** never ask me to paste database passwords, GitHub tokens or account files in chat; do not open `djangoeurope_account.txt` or the `*_gittoken.txt` files on my Desktop.
5. **Numbers must equal the restaurant's.** `apps/analytics/services.py` is a port of the desktop's `AnalyticsService.cs`; `apps/analytics/tests/test_golden.py` compares every page with the desktop's own output. When the desktop's analytics or `CloudSync.cs` change: regenerate the fixtures with `tools/CloudFixtures` (desktop repo), copy them here, run tests. Rounding is C#'s (halves to even).
6. **Texts** come from the desktop's `Loc.cs` (`tools/make_texts.py`, then `tools/compile_messages.py`; `.mo` files are committed, the server has no gettext). Do not edit `django.po` by hand.
7. **Sync keys** are shown once and stored only as a SHA-256 hash; PINs never reach this site. HTTPS only in production.
8. **Design:** same as the desktop: graphite and brass, sharp corners, flat, phone-friendly. Check pages in a browser (screenshots) before showing.
9. Git: small commits on `main` are fine for docs; features on a branch; commit trailer `Co-Authored-By: Claude <model> <noreply@anthropic.com>`.

### State
Login with phone + password (owners/managers; SwedPos staff = superusers in `/admin/`), restaurants with sync keys, `/api/sync` receiver (idempotent), 10 report pages (overview, sales, payments, waiters, payroll, tables, dishes/ABC, customers, control, stock) with SVG charts, sortable tables, waiter drill-down, Excel export, UZ/RU, demo restaurant (`manage.py seed_demo`), Django Europe deploy guide. 12 tests. **Not deployed yet.**

### Next
1. Deploy on Django Europe (`deploy/DJANGOEUROPE_SETUP.md`), create the first restaurant, paste the key into the desktop (Settings > SwedPos Cloud), check the first sync.
2. Admin page for restaurants/accounts instead of Django admin; password reset (SMS via Eskiz.uz).
3. Version 2: change settings online (menu prices, waiter percent) through a command queue the desktop pulls.
4. Owner mobile view/notifications (shift closed), multi-restaurant comparison.
