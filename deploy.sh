#!/bin/bash
set -e

echo "========================================="
echo "  Coffee Shop - Deploy Script"
echo "========================================="

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker not installed"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo "ERROR: Docker Compose not installed"
    exit 1
fi

echo "OK: Docker $(docker --version)"
echo "OK: Docker Compose $(docker compose version)"

# Check .env
if [ ! -f .env ]; then
    echo "WARN: .env not found. Copying from .env.example..."
    cp .env.example .env
    echo "WARN: Edit .env before starting!"
fi

echo ""
echo "Launching docker compose..."
docker compose up -d --build

echo ""
echo "Waiting for database..."
for i in $(seq 1 30); do
    if docker compose exec -T db pg_isready 2>/dev/null; then
        echo "OK: Database ready"
        break
    fi
    echo "   Waiting... ($i/30)"
    sleep 2
done

echo ""
echo "Applying migrations..."
docker compose exec -T web python manage.py migrate --noinput

echo ""
echo "Collecting static files..."
docker compose exec -T web python manage.py collectstatic --noinput --clear

echo ""
echo "Deploy complete!"
echo "Server: http://localhost:8000"
echo "Admin:  http://localhost:8000/admin/"
