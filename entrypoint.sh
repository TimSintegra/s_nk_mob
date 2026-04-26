#!/bin/sh

set -e

.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput

exec .venv/bin/gunicorn config.wsgi:application --bind 0.0.0.0:8000
