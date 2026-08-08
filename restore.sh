#!/bin/bash
set -e

echo "========================================="
echo "  Coffee Shop - Restore Script"
echo "========================================="

# Check arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup_path>"
    echo "Example: $0 ./backups/db_20240101_120000.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Stop services
echo "Stopping services..."
docker compose down

# Restore database
echo "Restoring database..."
gunzip -c "$BACKUP_FILE" | docker compose exec -T psql -U coffee_shop -d coffee_shop_dev

echo "Database restored from: $BACKUP_FILE"

# Start services
echo "Starting services..."
docker compose up -d --build

# Run migrations
echo "Applying migrations..."
docker compose exec -T web python manage.py migrate --noinput

echo ""
echo "Restore complete!"
echo "Server: http://localhost:8000"
