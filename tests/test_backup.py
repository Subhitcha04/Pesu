"""F7: backup.sh -> restore.sh round trip keeps rows and audio."""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

from app.config import settings
from tests.conftest import WEBM

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def test_backup_restore_round_trip(client, tmp_path):
    client.post(
        "/api/attempts",
        data={
            "child_id": "kavin-sample",
            "word_id": "kai",
            "pesu_verdict": "correct",
            "verdict": "correct",
            "decided_by": "pesu",
        },
        files={"audio": ("t.webm", WEBM, "audio/webm")},
    )
    with sqlite3.connect(settings.db_path) as c:
        before = c.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    archive = tmp_path / "b.tar.gz"
    subprocess.run(["sh", str(SCRIPTS / "backup.sh"), str(settings.data_dir), str(archive)], check=True)
    target = tmp_path / "restored"
    subprocess.run(["sh", str(SCRIPTS / "restore.sh"), str(archive), str(target)], check=True)
    with sqlite3.connect(target / "pesu.db") as c:
        assert c.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == before
    assert list((target / "audio" / "kavin-sample" / "tries").glob("*.webm"))
