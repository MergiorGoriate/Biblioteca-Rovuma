#!/bin/sh
set -eu
if [ -n "${ROVUMA_PROCESSOR_URL:-}" ]; then
    python manage.py dispatch_documents &
    dispatcher=$!
else
    dispatcher=
fi
gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 90 rovuma.wsgi:application &
web=$!
stop() {
    kill "$web" 2>/dev/null || true
    if [ -n "$dispatcher" ]; then kill "$dispatcher" 2>/dev/null || true; fi
    wait || true
}
trap 'stop; exit 0' INT TERM
while kill -0 "$web" 2>/dev/null; do
    if [ -n "$dispatcher" ] && ! kill -0 "$dispatcher" 2>/dev/null; then
        stop
        exit 1
    fi
    sleep 3
done
stop
exit 1
