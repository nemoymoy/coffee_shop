#!/bin/bash
set -e

# Activate virtual environment
. /opt/venv/bin/activate

echo "Running migrations..."
python manage.py migrate --noinput

echo "Starting Celery worker..."
exec celery -A coffee_shop worker -l info -P solo
