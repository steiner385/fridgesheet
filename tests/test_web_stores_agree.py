"""The Changes feed and the Trends counts must describe the same history.

Both stores reduce the same change log, and a parent reads them within a minute of each
other: Trends says "3 grades posted this week", the feed is supposed to name those three.
They drifted once already -- `weekly_counts` counted an item's *first* observation while
`changes` skipped first observations entirely, so a one-refresh install showed grades posted
on one page and nothing but "New" on the other. Nothing in either store's own test file
could see that, because each was right about itself. This file is the one that looks across.

If this fails, do not relax the assertion: one of the two stores has changed what it counts
and the pages now contradict each other. Decide which is right, and fix the other.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from fridgesheet.web.stores import changes, trends
from tests.web_fixtures import NOW, history

WEEKS = 6


def _week_bounds(week_start, tz) -> tuple[datetime, datetime]:
    """`changes.since` takes a half-open (since, until]; `weekly_counts` buckets on the local
    week [Monday 00:00, next Monday 00:00). Nudge by a microsecond so they cover the same
    instants."""
    start = datetime.combine(week_start, time.min, tzinfo=tz)
    tick = timedelta(microseconds=1)
    return start - tick, start + timedelta(days=7) - tick


def test_the_feed_names_the_events_the_weekly_counts_count(tmp_path):
    conn = history(tmp_path)
    weeks = trends.weekly_counts(conn, weeks=WEEKS, now=NOW)
    assert sum(w.missing + w.posted for w in weeks) > 0, "the fixture must exercise both counts"
    for w in weeks:
        since, until = _week_bounds(w.week_start, NOW.tzinfo)
        events = changes.since(conn, since=since, until=until, limit=None)
        missing = [e for e in events if e.kind == "now_missing"]
        posted = [e for e in events if e.kind == "grade_posted"]
        assert len(missing) == w.missing, (
            f"week of {w.week_start}: Trends counts {w.missing} turned missing, the feed shows "
            f"{len(missing)}: {[(e.item_name, e.source) for e in missing]}")
        assert len(posted) == w.posted, (
            f"week of {w.week_start}: Trends counts {w.posted} grades posted, the feed shows "
            f"{len(posted)}: {[(e.item_name, e.source) for e in posted]}")
    conn.close()


def test_they_agree_on_a_one_refresh_install_too(tmp_path):
    """The state every install starts in, and the case the drift was worst in: every
    observation is a first observation, so a store that ignores those reports nothing."""
    from tests.web_fixtures import seed

    conn = seed(tmp_path)
    (week,) = trends.weekly_counts(conn, weeks=1, now=NOW)
    since, until = _week_bounds(week.week_start, NOW.tzinfo)
    events = changes.since(conn, since=since, until=until, limit=None)
    assert week.missing and week.posted                       # the fixture has both
    assert len([e for e in events if e.kind == "now_missing"]) == week.missing
    assert len([e for e in events if e.kind == "grade_posted"]) == week.posted
    conn.close()


def test_they_agree_per_kid(tmp_path):
    """The kid filter is a different code path in each store; it must not split them."""
    from fridgesheet.web.stores import students

    conn = history(tmp_path)
    for s in students.visible(conn):
        weeks = trends.weekly_counts(conn, student_id=s["id"], weeks=WEEKS, now=NOW)
        for w in weeks:
            since, until = _week_bounds(w.week_start, NOW.tzinfo)
            events = changes.since(conn, since=since, until=until, student_id=s["id"], limit=None)
            kinds = [e.kind for e in events]
            assert kinds.count("now_missing") == w.missing, f"{s['key']}, week of {w.week_start}"
            assert kinds.count("grade_posted") == w.posted, f"{s['key']}, week of {w.week_start}"
    conn.close()
