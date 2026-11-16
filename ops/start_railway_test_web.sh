#!/bin/sh
set -eu

exec python -m ops.railway_storage sh -ec '
    if [ "${RAILWAY_ENVIRONMENT_NAME:-}" = teste ]; then
        python manage.py seed_sample_books --confirm-test-environment
    fi
    exec gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 90 rovuma.wsgi:application
'
