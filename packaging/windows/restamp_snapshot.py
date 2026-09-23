"""Re-stamp a snapshot fixture's fetch time to "now" while copying it into place.

Why this exists instead of just refreshing the committed fixture's timestamp: a timestamp
baked into a *committed* file is a bomb with a fuse equal to MAX_DATA_AGE_HOURS (24h,
fridgesheet/runner.py). Whatever value we commit will be "now" for at most a day, and then
every smoke run -- on every PR, on every tag push -- fails again with the exact same "snapshot
is stale" error, on a schedule nobody is watching. The fixture's age is not what the smoke
test is proving (it proves that a PDF builds from a snapshot); so the fix is to make the age
irrelevant by re-stamping it fresh at the moment it is copied into the throwaway smoke home,
every time, rather than trying to keep a committed value perpetually current.

fridgesheet.runner.data_as_of() takes the *minimum* of the top-level `fetched_at_epoch` and
every `stale[*]["fetched_at_epoch"]` (runner.py:176-181) -- "stale" entries are sources that
were carried forward from an earlier pull, and by definition are older than the rest of the
snapshot. If we only bumped the top-level timestamp, a snapshot with a non-empty `stale`
section would still compute an old `data_as_of` from its stale entries and this fix would
silently do nothing for it. So every stale entry's `fetched_at`/`fetched_at_epoch` gets moved
to "now" too, exactly like the top-level pair.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def restamp(snapshot: dict, now: datetime | None = None) -> dict:
    """Return a copy of `snapshot` with every fetch timestamp set to `now` (default: current
    UTC time). Nothing else in the document -- students, sources, reasons, etc. -- is touched."""
    now = now or datetime.now(timezone.utc)
    fetched_at = now.isoformat()
    fetched_at_epoch = now.timestamp()

    out = dict(snapshot)
    out["fetched_at"] = fetched_at
    out["fetched_at_epoch"] = fetched_at_epoch

    stale = snapshot.get("stale") or {}
    if stale:
        new_stale = {}
        for src, meta in stale.items():
            new_meta = dict(meta)
            new_meta["fetched_at"] = fetched_at
            new_meta["fetched_at_epoch"] = fetched_at_epoch
            new_stale[src] = new_meta
        out["stale"] = new_stale

    return out


def restamp_file(src: Path, dst: Path, now: datetime | None = None) -> None:
    snapshot = json.loads(src.read_text(encoding="utf-8"))
    restamped = restamp(snapshot, now)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(restamped, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("usage: restamp_snapshot.py <src.json> <dst.json>", file=sys.stderr)
        return 2
    src, dst = Path(argv[0]), Path(argv[1])
    if not src.is_file():
        print(f"restamp_snapshot.py: no such file: {src}", file=sys.stderr)
        return 1
    restamp_file(src, dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
