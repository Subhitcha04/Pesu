"""Regenerate the README sections that must not drift from the code (section 9.1 rule 6).

Fills the blocks between <!-- BEGIN:name --> and <!-- END:name --> markers:
  env     - configuration table from app/config.py ENV_VARS
  api     - every route from the FastAPI app (method, path, auth, summary) + docs/openapi.json
  truth   - worked scoring examples, produced by running app.scoring.score()
  tests   - test inventory (collected test counts per file)
Usage: python scripts/gen_docs.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import ENV_VARS  # noqa: E402
from app.main import app  # noqa: E402
from app.scoring import score  # noqa: E402

README = ROOT / "README.md"


def env_table() -> str:
    rows = ["| Variable | Default | What it does |", "|---|---|---|"]
    for name, (default, desc) in ENV_VARS.items():
        shown = "`./data`" if name == "PESU_DATA_DIR" else f"`{default}`" if default else "(derived)"
        rows.append(f"| `{name}` | {shown} | {desc} |")
    return "\n".join(rows)


def api_table() -> str:
    spec = app.openapi()
    (ROOT / "docs" / "openapi.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    rows = ["| Method | Path | Auth | What it does |", "|---|---|---|---|"]
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            route = next(r for r in app.routes if getattr(r, "path", None) == path and method.upper() in r.methods)
            deps = [d.call.__name__ for d in route.dependant.dependencies]
            auth = "therapist" if "require_therapist" in deps else "open"
            doc = (route.endpoint.__doc__ or op.get("summary", "")).strip().splitlines()[0]
            rows.append(f"| {method.upper()} | `{path}` | {auth} | {doc} |")
    return "\n".join(rows)


EXAMPLES = [
    ("kaakka", ["காக்கா"], None, 0.01, "clear k"),
    ("kaakka", ["டாக்கா"], None, 0.01, "k replaced by ட"),
    ("kai", ["தை"], None, 0.01, "k replaced by த"),
    ("kaakka", ["taakka"], None, 0.01, "Roman spelling with t"),
    ("kozhi", ["கோலி"], None, 0.01, "dialect form accepted"),
    ("kaakka", ["crow"], None, 0.01, "English word"),
    ("kaakka", [], None, 0.01, "nothing heard"),
    ("kaakka", ["காக்கா"], None, 0.2, "room got noisy"),
    ("kaakka", ["காக்கா சொல்லு"], None, 0.01, "parent speaking along"),
    ("kaakka", ["டாக்கா காக்கா"], None, 0.01, "self-correction"),
    ("kaakka", ["காக்கா காக்கா"], None, 0.01, "child repeats the word"),
    ("kaakka", ["டாக்கா", "காக்கா"], None, 0.01, "autocorrected lower alternative ignored"),
    ("kaakka", ["பாப்பா", "காக்கா", "காக்கா"], None, 0.01, "top unclear, lower ones agree"),
    ("kaakka", ["காக்கா"], [0.2], 0.01, "low recogniser confidence"),
    ("kaakka", ["காக்கா"], [0.0], 0.01, "confidence 0 = not reported"),
]


def truth_table() -> str:
    rows = [
        "| Word | Recogniser alternatives | Conf. | Noise | Verdict | Reason | Pesu says | Case |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for word, alts, conf, noise, note in EXAMPLES:
        r = score(word, alts, noise, conf, min_conf=0.35)
        shown = ", ".join(f"`{a}`" for a in alts) or "(none)"
        rows.append(
            f"| {word} | {shown} | {conf[0] if conf else '–'} | {noise} | **{r['verdict']}** | {r['reason']} "
            f"| {r['say_ta']} | {note} |"
        )
    return "\n".join(rows)


def tests_table() -> str:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts=", "tests"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout
    counts: dict[str, int] = {}
    for line in out.splitlines():
        if "::" in line:
            f = line.split("::")[0]
            counts[f] = counts.get(f, 0) + 1
    what = {
        "tests/test_scoring.py": "original v0.1 scorer cases (unchanged)",
        "tests/test_scoring_golden.py": "128-case golden logic set + 3,000-input seeded fuzz + normalise stability",
        "tests/test_api.py": "auth on every therapist route, PIN lockout, uploads, audit trail, delete/export, stickers",
        "tests/test_time_and_migration.py": "IST midnight boundaries, v0.1 → v0.2 migration, audio retention",
        "tests/test_backup.py": "backup.sh → restore.sh round trip",
        "tests/e2e/test_practice_flow.py": "real browser: Judge Mode, stubbed recogniser, exit, record-only, override",
    }
    rows = ["| File | Tests | What it proves |", "|---|---|---|"]
    for f, n in sorted(counts.items()):
        rows.append(f"| `{f}` | {n} | {what.get(f, '')} |")
    rows.append(f"| **Total** | **{sum(counts.values())}** | |")
    return "\n".join(rows)


def main() -> None:
    text = README.read_text(encoding="utf-8")
    for name, fn in {"env": env_table, "api": api_table, "truth": truth_table, "tests": tests_table}.items():
        pattern = re.compile(rf"(<!-- BEGIN:{name} -->\n).*?(<!-- END:{name} -->)", re.S)
        if not pattern.search(text):
            raise SystemExit(f"README is missing the {name} markers")
        text = pattern.sub(lambda m, f=fn: m.group(1) + f() + "\n" + m.group(2), text)
    README.write_text(text, encoding="utf-8")
    print("README generated sections updated: env, api, truth, tests; docs/openapi.json written")


if __name__ == "__main__":
    main()
