#!/bin/sh
set -e

echo "Applying migrations..."
python manage.py migrate --noinput

if [ "${COLLECTSTATIC:-1}" = "1" ]; then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

echo "Creating admin and demo data..."
python manage.py bootstrap

echo "Starting Gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120
