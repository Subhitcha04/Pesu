#!/usr/bin/env sh
# Restore a backup made by backup.sh into DATA_DIR. Stop Pesu first.
# Usage: scripts/restore.sh BACKUP.tar.gz [DATA_DIR]
set -eu
ARCHIVE="$1"
DATA="${2:-${PESU_DATA_DIR:-./data}}"
mkdir -p "$DATA"
rm -f "$DATA/pesu.db" "$DATA/pesu.db-wal" "$DATA/pesu.db-shm"
rm -rf "$DATA/audio"
tar -xzf "$ARCHIVE" -C "$DATA"
echo "restored into: $DATA"
