#!/usr/bin/env sh
# Back up Pesu's data: a consistent SQLite copy (.backup) plus the audio folder, in one tar.gz.
# Usage: scripts/backup.sh [DATA_DIR] [OUT_FILE]
set -eu
DATA="${1:-${PESU_DATA_DIR:-./data}}"
OUT="${2:-pesu-backup-$(date +%Y%m%d-%H%M%S).tar.gz}"
TMP="$(mktemp -d)"
python3 - "$DATA/pesu.db" "$TMP/pesu.db" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
src.backup(dst)          # safe while the app is running (WAL-aware online backup)
dst.close(); src.close()
PY
[ -d "$DATA/audio" ] && cp -R "$DATA/audio" "$TMP/audio"
[ -f "$DATA/secret.key" ] && cp "$DATA/secret.key" "$TMP/secret.key"
tar -czf "$OUT" -C "$TMP" .
rm -rf "$TMP"
echo "backup written: $OUT"
