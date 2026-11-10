# SwedPos Cloud

The owner website for **SwedPos** restaurants: sales, waiters, payroll (waiter percent), payments, tables, dishes, customers and control, from any phone or computer. Read-only in version 1. Uzbek and Russian.

The restaurant's **server PC** sends its data here every minute (SwedPos desktop › Settings › SwedPos Cloud). If the internet is down nothing is lost; the next send catches up. PINs and passwords never leave the restaurant.

## How it fits together

```
SwedPos desktop (server PC)                      SwedPos Cloud
  CloudSyncAgent ── HTTPS POST /api/sync ──▶  SyncReceiver ─▶ database "swedpos_cloud_r{id}" (one per restaurant)
  (paid/cancelled orders, payments, shifts,                     same schema as the desktop (same migrations)
   stock and cash movements, menu, staff names)                  │
                                                                 ▼
                                    owner's browser ◀── Blazor pages ◀── the desktop's own AnalyticsService
```

- `external/SwedPos` is the desktop repository as a **git submodule**. The website uses its domain, database schema, sync contract (`CloudSync.cs`) and analytics, so the numbers on the website are always the same as in the restaurant.
- `swedpos_cloud` (control database): restaurants, their sync key (stored only as a hash), owner accounts (phone + password).
- Days and hours are counted in **Tashkent time**. On a Linux server set `TZ=Asia/Tashkent` for the process.

## Run it

Demo mode (no database needed, made-up restaurant, 60 days of sales):

```
dotnet run --project src/SwedPos.Cloud --launch-profile http
```

Open http://localhost:5289 → "Open demo" (or phone `+998 90 000 00 00`, password `demo12345`).

With PostgreSQL (real mode): run `tools/setup-local-db.ps1` once (it asks for the `postgres` password itself and stores the site's own connection in user-secrets), then the same `dotnet run`.

## Connect a restaurant

```
dotnet run --project src/SwedPos.Cloud -- add-restaurant "Marokand"
dotnet run --project src/SwedPos.Cloud -- add-account 998901234567 "Owner name" "a-long-password" 1
dotnet run --project src/SwedPos.Cloud -- list
dotnet run --project src/SwedPos.Cloud -- renew-key 1
```

`add-restaurant` prints the sync key **once**. On the restaurant's server PC: Settings › SwedPos Cloud › address (e.g. `https://cloud.swedpos.uz`) and key › Save. The status line shows the last send.

## Tests

```
git submodule update --init
dotnet test
```

## Not done yet (planned)

- Hosting and a domain (HTTPS is required in production; the desktop only sends to the address entered).
- Changing settings from the website (menu prices, waiter percent) — version 2, through a command queue the desktop pulls.
- Password reset by SMS (Eskiz.uz), an admin page instead of the commands above.
