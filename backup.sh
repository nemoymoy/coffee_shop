#!/bin/bash
set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="./backups"
MAX_BACKUPS=7

mkdir -p "$BACKUP_DIR"

echo "========================================="
echo "  Coffee Shop - Backup Script"
echo "========================================="

# Database backup
echo "Backing up database..."
DB_FILE="$BACKUP_DIR/db_$TIMESTAMP.sql.gz"
docker compose exec -T db pg_dump -U coffee_shop coffee_shop_dev | gzip > "$DB_FILE"
echo "Database backup: $DB_FILE"

# Media backup
echo "Backing up media files..."
MEDIA_FILE="$BACKUP_DIR/media_$TIMESTAMP.tar.gz"
docker compose cp coffee_shop_media_data:/app/media /tmp/media_tmp_$TIMESTAMP
tar -czf "$MEDIA_FILE" -C /tmp/media_tmp_$TIMESTAMP .
rm -rf /tmp/media_tmp_$TIMESTAMP
echo "Media backup: $MEDIA_FILE"

# Rotate old backups
echo "Rotating backups (keeping last $MAX_BACKUPS)..."
BACKUPS=($(ls -t "$BACKUP_DIR" | tail -n +$((MAX_BACKUPS + 1))))
for BACKUP in "${BACKUPS[@]}"; do
    rm -f "$BACKUP_DIR/$BACKUP"
    echo "  Removed: $BACKUP"
done

echo ""
echo "Backup complete!"
echo "DB:    $DB_FILE"
echo "Media: $MEDIA_FILE"
