# Gunicorn configuration for SwedPos Cloud on Django Europe (wservices).
#
# The host's reverse proxy sends several "which scheme?" headers; trusting only X-Forwarded-Proto avoids
# "Contradictory scheme headers". Pairs with SECURE_PROXY_SSL_HEADER in config/settings/prod.py.
secure_scheme_headers = {"X-FORWARDED-PROTO": "https"}

# gunicorn binds to 127.0.0.1 only; the only client is the local panel proxy.
forwarded_allow_ips = "*"

# A first sync from a busy restaurant can take a while to store.
timeout = 120
