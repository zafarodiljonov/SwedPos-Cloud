# Deploy SwedPos Cloud on Django Europe (X10): step by step

Same method as the other sites on this account (`indref`, `erpwms`, `homenet`): `git clone` + its **own** virtualenv +
gunicorn on a **reserved local port**, started by a script in `~/init/`, and the panel **Website** proxying the domain to that port.

`$` = type it over SSH in Git Bash · **[panel]** = Django Europe web panel · `<LIKE_THIS>` = replace with your value.
Git Bash: paste with **right-click** or **Shift+Insert** (Ctrl+V does nothing). Selecting text with the mouse copies it.

Account `fastfreezing` · server `s20.wservices.ch` · Python on the server is **3.13** (there is no `python3.12`).

> ## Three other sites live on this account: do not disturb them
> | | indref | erpwms | homenet | **swedpos (this one)** |
> |---|---|---|---|---|
> | Folder | `~/indref` | `~/erpwms` | `~/homenet` | `~/swedpos` |
> | Venv | `~/venv` | `~/venv_erpwms` | `~/venv_homenet` | `~/venv_swedpos` |
> | Port | 63278 | 63250 | 63180 | **63503** (given by the panel) |
> | Init script | `~/init/indref` | `~/init/erpwms` | `~/init/homenet` | `~/init/swedpos` |
> | PID file | `~/run/gunicorn.pid` | `~/run/gunicorn_erpwms.pid` | `~/run/gunicorn_homenet.pid` | `~/run/gunicorn_swedpos.pid` |
> | Database | `fastfreezing_indref` | `fastfreezing_erpwms` | `fastfreezing_homenet` | `fastfreezing_swedpos` |
>
> Nothing below changes the other sites. The only thing read from them is the shared database password (step 4), and it is only read.

## 0. On your Windows PC, before the server

1. Everything is merged into `main` and pushed (`git status` clean, `git push`). The server gets the code with `git pull` from GitHub.
2. The site has **no demo content**. The first thing in the database will be your own login.

## 1. [panel] Database

**Databases → Add**, type PostgreSQL: name `fastfreezing_swedpos`, user `fastfreezing` (the existing user), extensions: none.
All sites on the account share the database user `fastfreezing`, so they share its password; step 4 reads it from the server without printing it.

## 2. [panel] Reserve a port

**Ports → Add**: IP `127.0.0.1`, local port `63503`, remote port empty, description `swedpos gunicorn`.

## 3. [panel] Subdomain

**Domains / Websites → Add**: `swedpos.django.group` (keep "DNS hosting" ticked). The wildcard `*.django.group` certificate covers it,
so HTTPS works at once. A real domain can be added later (step 11).

## 4. Clone and install (SSH)

```bash
$ ssh fastfreezing@s20.wservices.ch
$ git clone https://github.com/zafarodiljonov/SwedPos-Cloud.git ~/swedpos
```
If git asks for a user and password: user `zafarodiljonov`, password = a GitHub **personal access token** (never type it in a chat, and do not put it in the URL).

```bash
$ cd ~/swedpos
$ python3 --version                                   # expect 3.13.x
$ python3 -m venv ~/venv_swedpos
$ ~/venv_swedpos/bin/pip install --upgrade pip
$ ~/venv_swedpos/bin/pip install -r requirements/prod.txt
$ mkdir -p ~/run ~/init
```
If `pip install` fails on a package, copy the error to Claude; the code was tested on Python 3.12.

## 5. Create `~/swedpos/.env` (on the server, never on Windows)

A `.env` made on Windows carries invisible CR characters that break values. Create it here. This block reads the shared database password
from `~/erpwms/.env` (read only), makes a fresh secret key, and writes the file without ever showing the password:

```bash
$ DBPASS=$(grep '^DATABASE_URL' ~/erpwms/.env | sed -E 's#.*://[^:]+:([^@]+)@.*#\1#')
$ SECRET=$(~/venv_swedpos/bin/python -c "import secrets; print(secrets.token_urlsafe(50))")
$ cat > ~/swedpos/.env <<EOF
SECRET_KEY=$SECRET
DEBUG=False
ALLOWED_HOSTS=swedpos.django.group
CSRF_TRUSTED_ORIGINS=https://swedpos.django.group
DATABASE_URL=postgres://fastfreezing:$DBPASS@127.0.0.1:5432/fastfreezing_swedpos
EOF
$ chmod 600 ~/swedpos/.env
$ sed -E 's#(://[^:]+:)[^@]+@#\1*****@#' ~/swedpos/.env      # shows the file with the password hidden: check the five lines
```
`.env` is git-ignored. `manage.py` uses the development settings unless told otherwise, so **every `manage.py` command below carries
`--settings=config.settings.prod`** (gunicorn already uses production settings).

## 6. Build the site

```bash
$ cd ~/swedpos
$ ~/venv_swedpos/bin/python manage.py migrate --settings=config.settings.prod
$ ~/venv_swedpos/bin/python manage.py createsuperuser --settings=config.settings.prod      # YOUR login: phone number + password
$ ~/venv_swedpos/bin/python manage.py collectstatic --noinput --settings=config.settings.prod
```
Translations ship as compiled `.mo` files (the host has no gettext). There is no demo data to load.

## 7. Start gunicorn

```bash
$ cp ~/swedpos/deploy/gunicorn-init.sh ~/init/swedpos
$ sed -i 's/^PORT=.*/PORT=63503/' ~/init/swedpos
$ chmod +x ~/init/swedpos
$ ~/init/swedpos start
$ curl -s http://127.0.0.1:63503/api/ping                # expect {"service": "SwedPos Cloud", "protocol": 1}
```
The script loads `gunicorn.conf.py` (trusts only `X-Forwarded-Proto`); without it the host answers "Contradictory scheme headers".
It also sets `TZ=Asia/Samarkand`, so days and hours in the reports are counted in the restaurant's time.

## 8. [panel] Point the domain at the port

**Websites** → `swedpos.django.group` → proxy to `127.0.0.1:63503`. WhiteNoise serves `/static/`, no other mapping is needed.

## 9. Check the live site

- `https://swedpos.django.group/api/ping` shows the JSON above (HTTPS, no certificate warning).
- `https://swedpos.django.group/admin/` opens; log in with the phone number and password from step 6.
- The three other sites still work (`homenet`, `erpwms`, `indref`).

## 10. Connect a restaurant (this is how the restaurant's data reaches the site)

1. `/admin/` → **Users → Add**: the owner's phone number and a password (this is the owner's login to see the reports).
2. **Restaurants → Add**: name (for example `Marokand`), choose the owner under *Users*, Save. A yellow message shows the **sync key once**. Copy it now
   (it is stored only as a hash). Lost key: select the restaurant → action **Renew sync key**.
3. On the restaurant's **server PC**: SwedPos → **Sozlamalar → SwedPos Cloud** → address `https://swedpos.django.group`, paste the key → Save.
4. From then on it is automatic: every minute the server PC sends new orders, payments, shifts, stock and the menu. No PINs are sent.
   The status line in Settings shows the last send; the site shows the time of the last data. If the internet is down, the PC keeps the rest and sends it later.
5. The owner opens `https://swedpos.django.group`, logs in with the phone and password, and sees the analytics.

## 11. A real domain later

1. Panel → **Domains**: add it, point its DNS at Django Europe; Panel → **SSL**: Let's Encrypt for it.
2. In `~/swedpos/.env` add it to both lines and restart (`~/init/swedpos restart`):
   ```
   ALLOWED_HOSTS=swedpos.django.group,yourdomain.uz
   CSRF_TRUSTED_ORIGINS=https://swedpos.django.group,https://yourdomain.uz
   ```
3. Change the address in the restaurant's SwedPos (Settings → SwedPos Cloud).

## 12. Updating later

On Windows: merge to `main` and push. Then on the server:

```bash
$ cd ~/swedpos && git pull
$ ~/venv_swedpos/bin/pip install -r requirements/prod.txt
$ ~/venv_swedpos/bin/python manage.py migrate --settings=config.settings.prod
$ ~/venv_swedpos/bin/python manage.py collectstatic --noinput --settings=config.settings.prod
$ ~/init/swedpos restart
```
This release (1.4.0) adds two migrations (`restaurants 0002` and `0003`): `migrate` applies them.

## 13. Backups (do this before the first real restaurant)

```bash
$ mkdir -p ~/backups
$ PGPASSWORD="$(grep '^DATABASE_URL' ~/swedpos/.env | sed -E 's#.*://[^:]+:([^@]+)@.*#\1#')" \
    pg_dump -h 127.0.0.1 -U fastfreezing fastfreezing_swedpos | gzip > ~/backups/swedpos-$(date +%F).sql.gz
```
Add the same to panel → **Cron** (daily) and download a copy off the server from time to time.
The restaurant's own PC also keeps all data, so the site is a copy, not the only place.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "Bad Request: Contradictory scheme headers" | `gunicorn.conf.py` not used: init script must have `--config` (the repo's script has it) |
| 500 on every page, admin without styles | `collectstatic` not run |
| `DisallowedHost` | host missing in `ALLOWED_HOSTS` in `.env` → edit, `~/init/swedpos restart` |
| CSRF error at login | `CSRF_TRUSTED_ORIGINS` must start with `https://` |
| Everything looks like development (no HTTPS redirect) | a `manage.py` command without `--settings=config.settings.prod`, or gunicorn not restarted |
| `password authentication failed` | the shared password was copied wrongly; repeat step 5 |
| Port already in use | choose another free number in step 2 and 7 (not 63278, 63250, 63180) |
| Restaurant's "last send" stays empty | wrong address or key in the desktop; check `https://…/api/ping` from the restaurant PC's browser |

## Quick reference

| Thing | Value |
|---|---|
| Code | `~/swedpos` · venv `~/venv_swedpos` |
| Start / stop / restart | `~/init/swedpos start`, `stop`, `restart` |
| Secrets | `~/swedpos/.env` (never committed) |
| Site / admin | `https://swedpos.django.group/` and `/admin/` |
| Port / pid file | `127.0.0.1:63503` · `~/run/gunicorn_swedpos.pid` |
