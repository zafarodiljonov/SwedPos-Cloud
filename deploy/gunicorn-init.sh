#!/bin/bash
# Start/stop SwedPos Cloud (gunicorn) on Django Europe / wservices.
# Copy to ~/init/swedpos:   cp ~/swedpos/deploy/gunicorn-init.sh ~/init/swedpos && chmod +x ~/init/swedpos
# Uses its own venv, pidfile and port so it never collides with the other sites on the account.
# IMPORTANT: set PORT to the port reserved in the panel (Ports).
PORT=00000
GUNICORN=$HOME/venv_swedpos/bin/gunicorn
PIDFILE=$HOME/run/gunicorn_swedpos.pid
APPDIR=$HOME/swedpos

case "$1" in
  start)
    cd "$APPDIR" || exit 1
    TZ=Asia/Samarkand "$GUNICORN" config.wsgi:application \
      --config "$APPDIR/gunicorn.conf.py" \
      --bind 127.0.0.1:$PORT --workers 2 \
      --pid "$PIDFILE" --daemon
    echo "swedpos started on 127.0.0.1:$PORT"
    ;;
  stop)
    [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" && echo "swedpos stopped" || echo "not running"
    ;;
  restart)
    "$0" stop; sleep 2; "$0" start
    ;;
  *)
    echo "usage: $0 {start|stop|restart}"
    ;;
esac
