"""Check the README against the repo (section 9.1 rule 7).

- every relative link / image path exists
- every `make <target>` mentioned exists in the Makefile
- every env var in app/config.py is documented in README and .env.example, and vice versa
- every API route appears in the README API table
- every table-of-contents anchor resolves to a heading
Usage: python scripts/verify_readme.py  (exit 1 on any problem)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.config import ENV_VARS  # noqa: E402
from app.main import app  # noqa: E402


def slug(heading: str) -> str:
    s = heading.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def main() -> int:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    problems: list[str] = []

    for target in re.findall(r"\]\(((?!https?:|#|mailto:)[^)\s]+)\)", readme) + re.findall(r'src="((?!https?:)[^"]+)"', readme):
        if not (ROOT / target.split("#")[0]).exists():
            problems.append(f"missing file: {target}")

    makefile = (ROOT / "Makefile").read_text()
    targets = set(re.findall(r"^([a-z][\w-]*):", makefile, re.M))
    for t in set(re.findall(r"`make ([a-z][\w-]*)", readme)):
        if t not in targets:
            problems.append(f"make target not in Makefile: {t}")

    env_example = (ROOT / ".env.example").read_text()
    for name in ENV_VARS:
        if name not in readme:
            problems.append(f"env var not in README: {name}")
        if name not in env_example:
            problems.append(f"env var not in .env.example: {name}")
    for name in set(re.findall(r"\bPESU_[A-Z_]+\b", readme)):
        if name not in ENV_VARS and name not in {"PESU_E2E_CHROME"}:
            problems.append(f"README mentions unknown env var: {name}")

    for path in app.openapi()["paths"]:
        if f"`{path}`" not in readme:
            problems.append(f"API route not in README: {path}")

    anchors = {slug(h) for h in re.findall(r"^#{1,4} (.+)$", readme, re.M)}
    for a in re.findall(r"\]\(#([^)]+)\)", readme):
        if a not in anchors:
            problems.append(f"broken anchor: #{a}")

    for p in problems:
        print("FAIL", p)
    print(f"verify_readme: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
