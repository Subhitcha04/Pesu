"""Static checks for the front end (F17): every JS module parses (node --check) and no inline
event-handler attributes exist anywhere (they would break the CSP script-src 'self')."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
INLINE = re.compile(r"""<[^>]*\son[a-z]+\s*=\s*["']""", re.IGNORECASE)


def main() -> int:
    bad = 0
    files = sorted(STATIC.rglob("*.js")) + sorted(STATIC.rglob("*.html"))
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if INLINE.search(line):
                print(f"inline handler: {f.relative_to(STATIC)}:{n}: {line.strip()[:90]}")
                bad += 1
    node = shutil.which("node")
    if node:
        for f in sorted(STATIC.rglob("*.js")):
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
            if r.returncode:
                print(f"syntax: {f.relative_to(STATIC)}\n{r.stderr}")
                bad += 1
    else:
        print("node not found: skipped syntax check")
    print(f"checked {len(files)} files, {bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
