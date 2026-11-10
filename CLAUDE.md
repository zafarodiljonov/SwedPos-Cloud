# SwedPos Cloud (Claude Code project memory)

Owner website for the SwedPos restaurant POS: Django 5.2 + PostgreSQL, Uzbek + Russian, hosted on Django Europe.
The owner (Zafar) works in VS Code and manages this project himself: keep the code readable like hand-written code and explain where things are.

@HANDOFF.md
@docs/PROJECT_MAP.md

## Quick commands (always with UTF-8)
- Run: `PYTHONUTF8=1 ./.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000` (or F5 "Django: runserver").
- Tests: `PYTHONUTF8=1 ./.venv/Scripts/python.exe manage.py test --settings=config.settings.test`.
- Texts: `tools/make_texts.py ../src/SwedPos.App/Loc.cs` then `tools/compile_messages.py`.
- The desktop app lives in the parent folder (`..`), a separate repo; `apps/analytics/services.py` must stay equal to its `AnalyticsService.cs` (see `docs/PROJECT_MAP.md`).
- Never touch `erp_wms`, `homnet`, `ind_ref_pro`; never open the account/token files on the Desktop.
