# Deploy SwedPos Cloud on Django Europe (SSH + gunicorn + PostgreSQL)

Same method as the other sites on the account: `git clone` + its own venv + gunicorn on a reserved local port,
started by a `~/init/` script, with the panel **Website** proxying the domain to that port.

`$` = run over SSH · **[panel]** = Django Europe web panel · replace every `<PLACEHOLDER>`.

---

## 1. [panel]
- **Databases → Add**: PostgreSQL database `<ACCOUNT>_swedpos` (user `<ACCOUNT>`, host `127.0.0.1:5432`).
- **Subdomain**: e.g. `swedpos.django.group` (wildcard SSL `*.django.group` → HTTPS automatic), or your own domain.
- **Ports → Add**: note the number. This is `<PORT>`; put it into `deploy/gunicorn-init.sh` (`PORT=`).

## 2. Clone on the server
```bash
$ ssh <ACCOUNT>@<SERVER>
$ git clone https://github.com/zafarodiljonov/SwedPos-Cloud.git ~/swedpos     # GitHub username + a fresh token when asked
$ cd ~/swedpos
$ python3.12 -m venv ~/venv_swedpos
$ ~/venv_swedpos/bin/pip install --upgrade pip
$ ~/venv_swedpos/bin/pip install -r requirements/prod.txt
```

## 3. `~/swedpos/.env`
```
SECRET_KEY=<long-random-string>
DEBUG=False
DJANGO_SETTINGS_MODULE=config.settings.prod
ALLOWED_HOSTS=swedpos.django.group
CSRF_TRUSTED_ORIGINS=https://swedpos.django.group
DATABASE_URL=postgres://<ACCOUNT>:<DBPASSWORD>@127.0.0.1:5432/<ACCOUNT>_swedpos
```
Secret key: `~/venv_swedpos/bin/python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"`

## 4. Build
```bash
$ cd ~/swedpos
$ ~/venv_swedpos/bin/python manage.py migrate --settings=config.settings.prod
$ ~/venv_swedpos/bin/python manage.py createsuperuser --settings=config.settings.prod   # YOUR login: phone + password
$ ~/venv_swedpos/bin/python manage.py collectstatic --noinput --settings=config.settings.prod
$ ~/venv_swedpos/bin/python manage.py seed_demo --settings=config.settings.prod          # optional: demo restaurant for showing clients
# translations ship as compiled .mo files (the host has no gettext)
```

## 5. Run
```bash
$ mkdir -p ~/run
$ nano ~/swedpos/deploy/gunicorn-init.sh       # PORT=<PORT>
$ cp ~/swedpos/deploy/gunicorn-init.sh ~/init/swedpos && chmod +x ~/init/swedpos
$ ~/init/swedpos start
```

## 6. [panel] Point the domain at the port
**Websites → Add** → host `swedpos.django.group`, proxy to `127.0.0.1:<PORT>`. WhiteNoise serves `/static/`.

## 7. Connect a restaurant
1. `https://swedpos.django.group/admin/` → **Users → Add**: the owner's phone and a password.
2. **Restaurants → Add**: name, choose the owner under *Users*, Save. A yellow message shows the **sync key once** — copy it.
3. On the restaurant's **server PC**: SwedPos › Settings › SwedPos Cloud › address `https://swedpos.django.group`, paste the key, Save.
   The status line shows the last send; the website shows "Oxirgi ma'lumot" with the time.
4. Lost key: select the restaurant → action **Renew sync key**, paste the new key on the server PC.

## 8. Verify
- `https://swedpos.django.group/api/ping` → `{"service": "SwedPos Cloud", "protocol": 1}`
- Log in as the owner → the restaurant's overview; switch UZ/RU; download Excel.

## 9. Updating later
```bash
$ cd ~/swedpos && git pull
$ ~/venv_swedpos/bin/pip install -r requirements/prod.txt
$ ~/venv_swedpos/bin/python manage.py migrate --settings=config.settings.prod
$ ~/venv_swedpos/bin/python manage.py collectstatic --noinput --settings=config.settings.prod
$ ~/init/swedpos restart
```

| Thing | Value |
|---|---|
| Code | `~/swedpos` |
| Virtualenv | `~/venv_swedpos` |
| Settings | `config.settings.prod` |
| gunicorn | `127.0.0.1:<PORT>`, pidfile `~/run/gunicorn_swedpos.pid`, init `~/init/swedpos` |
| Secrets | `~/swedpos/.env` (never commit) |
| Time zone | `TZ=Asia/Samarkand` (set by the init script; days and hours are counted in it) |
