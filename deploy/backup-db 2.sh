#!/usr/bin/env bash
# Nightly DB + media backup. Cron as the ttr user:
#   15 2 * * * /srv/ttr/app/deploy/backup-db.sh >> /srv/ttr/backups/backup.log 2>&1
# Needs ~ttr/.my.cnf (chmod 600) with a [client] user/password so no secret is on the command line.
# Copy /srv/ttr/backups off the server as well (rclone/scp); a backup on the same disk is not a backup.
set -euo pipefail

DEST=/srv/ttr/backups
DB=ttr_v2
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$DEST"

mysqldump --single-transaction --routines --default-character-set=utf8mb4 "$DB" | gzip > "$DEST/db-$STAMP.sql.gz"
tar -czf "$DEST/media-$STAMP.tar.gz" -C /srv/ttr/app media

find "$DEST" -name 'db-*.sql.gz' -mtime +14 -delete
find "$DEST" -name 'media-*.tar.gz' -mtime +14 -delete
echo "$(date -Is) backup ok: $STAMP"
