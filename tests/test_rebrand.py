"""The rebrand is complete when nothing outside the district defaults still says the old name.

Fails the moment someone reintroduces `lakota_grades`, `Lakota Sheet`, `LAKOTA_*` and the
like into shipped source, tests, packaging or user docs. Historical plans and specs under
docs/superpowers are exempt: they describe what was true when they were written. The
migration module and its test are exempt because their job is to know the old names.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Files that legitimately carry the old name.
EXEMPT = {
    "fridgesheet/migrate.py",
    "tests/test_migrate.py",
    "tests/test_rebrand.py",
    "tests/conftest.py",                     # strips LAKOTA_* from the environment
    "packaging/windows/installer.iss",       # uninstalls the old AppId; names the old task
    "docs/release-checklist.md",             # the upgrade-from-Lakota-Sheet section
    "docs/windows.md",                       # tells a parent what happened to the old install
    "scripts/lakota-sheet-desktop.sh",       # the one-release wrapper
    "README.md",                             # the "old name" paragraph
    "pyproject.toml",                        # the `lakota-grades` shim entry point
    "fridgesheet/cli.py",                    # the shim's one-line notice
    "fridgesheet/host/scheduling_linux.py",  # refuses the household's pre-rename unit names
    "tests/test_host_scheduling_linux.py",
    "fridgesheet/config.py",                 # honours LAKOTA_* and moves the old home (comments)
    "fridgesheet/doctor.py",                 # the "old names" probe's docstring
    "fridgesheet/web/db.py",                 # renames lakota.db on open (comment)
    "tests/test_packaging.py",               # pins the installer's removal of the old AppId
}
#: Tokens that are the district, not the product.
DISTRICT = re.compile(r"lakota\.instructure\.com|hac\.lakotainline\.com|lakota\.onelogin\.com|Lakota's|Lakota Local Schools|Lakota board|Lakota OneLogin|\(Lakota, Sept 2026\)|loads Lakota")

OLD = re.compile(r"lakota", re.IGNORECASE)


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if p and not p.startswith("docs/superpowers/")]


def test_no_shipped_file_still_carries_the_old_name():
    offenders = []
    for rel in _tracked():
        if rel in EXEMPT or rel.endswith((".png", ".ico", ".db")):
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if OLD.search(DISTRICT.sub("", line)):
                offenders.append(f"{rel}:{n}: {line.strip()[:100]}")
    assert not offenders, "old name still present:\n" + "\n".join(offenders)


def test_no_tracked_path_is_named_after_the_old_brand():
    bad = [p for p in _tracked() if "lakota" in p.lower() and p != "scripts/lakota-sheet-desktop.sh"]
    assert bad == [], bad


def test_the_shipped_identity_is_consistent():
    from fridgesheet import host
    from fridgesheet.host import service
    from fridgesheet.web import db
    assert host.SERVICE == "fridgesheet" and service.SERVICE_NAME == "Fridge Sheet - web"
    assert db.DB_NAME == "fridgesheet.db" and host.task_name("open-work").startswith("Fridge Sheet - ")
    py = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "fridgesheet"' in py and 'fridgesheet = "fridgesheet.cli:main"' in py
    assert 'lakota-grades = "fridgesheet.cli:legacy_main"' in py     # the one-release shim
