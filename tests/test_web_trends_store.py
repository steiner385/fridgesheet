"""Trends: grade lines per class, and the weekly counts under them."""
from __future__ import annotations

from datetime import date, datetime

from lakota_grades.web import db, ingest
from lakota_grades.web.stores import flags, students, trends
from tests.web_fixtures import NOW, REFRESH_TIMES, TZ, history, seed, snapshot


def test_empty_database_has_no_series(tmp_path):
    conn = db.open_db(tmp_path)
    assert trends.grade_series(conn) == []
    weeks = trends.weekly_counts(conn, weeks=4, now=NOW)
    assert len(weeks) == 4 and all(w.missing == 0 and w.posted == 0 for w in weeks)
    assert trends.on_time_rate(weeks) is None
    conn.close()


def test_grade_series_per_course_and_source(tmp_path):
    conn = history(tmp_path)
    series = {(s.course_short, s.source): s for s in trends.grade_series(conn)}
    hac = series[("Honors English 9", "hac")]
    assert [v for _, v in hac.points] == [85.0, 88.0]                 # day 1 then day 2 onward
    assert [t.isoformat() for t, _ in hac.points] == [REFRESH_TIMES[0], REFRESH_TIMES[1]]
    canvas = series[("Honors English 9", "canvas")]
    assert [v for _, v in canvas.points] == [93.0, 91.2]
    assert canvas.label == "Honors English 9 (Canvas current)"
    assert hac.label == "Honors English 9 (HAC average)"
    conn.close()


def test_grade_series_filters_by_student_and_since(tmp_path):
    conn = history(tmp_path)
    sam = students.by_key(conn, "Sam")["id"]
    assert {s.course_short for s in trends.grade_series(conn, student_id=sam)} == {"Science 7"}
    late = trends.grade_series(conn, since=datetime.fromisoformat(REFRESH_TIMES[1]))
    assert all(all(t >= datetime.fromisoformat(REFRESH_TIMES[1]) for t, _ in s.points) for s in late)
    conn.close()


def test_grade_series_since_accepts_a_naive_datetime(tmp_path):
    """`since` must be compared with `reconcile.comparable`, never bare `<`: a naive value
    against the tz-aware timestamps this store stores would otherwise raise TypeError."""
    conn = history(tmp_path)
    naive_since = datetime(2026, 9, 14, 6, 0)                          # no tzinfo
    series = {(s.course_short, s.source): s for s in trends.grade_series(conn, since=naive_since)}
    hac = series[("Honors English 9", "hac")]
    assert [v for _, v in hac.points] == [88.0]                        # day 1's point dropped
    canvas = series[("Honors English 9", "canvas")]
    assert [v for _, v in canvas.points] == [91.2]                     # day 1's point dropped
    conn.close()


def test_weekly_counts_bucket_by_week(tmp_path):
    conn = history(tmp_path)
    weeks = trends.weekly_counts(conn, weeks=3, now=NOW)
    assert len(weeks) == 3 and [w.week_start for w in weeks] == sorted(w.week_start for w in weeks)
    assert weeks[-1].week_start == date(2026, 9, 14)                  # the Monday of NOW's week
    this_week = weeks[-1]
    assert this_week.missing >= 1 and this_week.posted >= 1
    assert all(w.missing >= 0 and w.late >= 0 and w.on_time >= 0 for w in weeks)
    conn.close()


def test_weekly_counts_counts_a_hand_in_seen_on_the_first_observation(tmp_path):
    """An item can enter the change log already submitted -- a household adopting the app
    mid-year, or a refresh landing just after a hand-in -- and that first observation must
    still count as a hand-in, not be silently dropped because there was no earlier row to
    diff against. The default snapshot's Essay draft (course Honors English 9) is already
    submitted, not late, so a single fresh refresh puts it straight into `on_time`."""
    conn = db.open_db(tmp_path)
    ingest.record(conn, snapshot(), tz=TZ, now=NOW)
    weeks = trends.weekly_counts(conn, weeks=1, now=NOW)
    assert weeks[0].on_time == 1 and weeks[0].late == 0
    conn.close()


def test_weekly_counts_filter_by_student(tmp_path):
    conn = history(tmp_path)
    sam = students.by_key(conn, "Sam")["id"]
    mine = trends.weekly_counts(conn, student_id=sam, weeks=3, now=NOW)
    everyone = trends.weekly_counts(conn, weeks=3, now=NOW)
    # Sam's own items, from _history_snapshots' docstring: Cell diagram is missing from its
    # first observation (day 1, week of 9/7); Safety quiz is graded 0 on day 3 (week of 9/14).
    # Nothing of hers is ever late/on-time, since this fixture never sets her submitted_at.
    assert [(w.missing, w.late, w.on_time, w.posted) for w in mine] == [
        (0, 0, 0, 0), (1, 0, 0, 0), (0, 0, 0, 1),
    ]
    assert sum(w.missing for w in mine) < sum(w.missing for w in everyone)
    assert sum(w.posted for w in mine) < sum(w.posted for w in everyone)
    conn.close()


def test_weekly_counts_treats_no_weeks_as_this_week(tmp_path):
    """`weeks=0` used to raise IndexError off an empty `starts`. Only the route clamps, and
    the store is called directly too."""
    conn = history(tmp_path)
    for asked in (0, -3):
        weeks = trends.weekly_counts(conn, weeks=asked, now=NOW)
        assert [w.week_start for w in weeks] == [date(2026, 9, 14)]
    conn.close()


def test_on_time_rate_is_a_fraction_or_none(tmp_path):
    conn = history(tmp_path)
    weeks = trends.weekly_counts(conn, weeks=8, now=NOW)
    rate = trends.on_time_rate(weeks)
    assert rate is None or 0.0 <= rate <= 1.0
    conn.close()


def test_open_days_reports_the_longest_first(tmp_path):
    conn = history(tmp_path)
    rows = trends.open_days(conn, now=NOW)
    assert len(rows) <= 10
    assert [d for _, d in rows] == sorted((d for _, d in rows), reverse=True)
    assert all(d >= 0 for _, d in rows)
    conn.close()


def test_open_days_excludes_items_due_before_the_school_year(tmp_path):
    """The floor is the item's due date, the same one `reconcile.live_items` uses, not when it
    was first observed -- else a stale course-copy item first seen this year would show up
    here while the Kid and Reconcile pages, which floor on due, hide it."""
    conn = db.open_db(tmp_path)
    snap = snapshot()
    eng = snap["students"]["Alex"]["canvas"]["courses"][0]
    for a in eng["assignments"]:
        if a["name"] == "Quiz 1":
            a["due_at"] = "2025-05-01T23:59:00-04:00"                  # last school year, still MISSING
    ingest.record(conn, snap, tz=TZ, now=NOW)
    rows = trends.open_days(conn, now=NOW)
    assert "Quiz 1" not in [name for name, _ in rows]
    conn.close()


def test_open_days_drops_an_item_the_parent_has_handled(tmp_path):
    """"Open the longest" has to mean what the Kid page means by open. A `done`, `excused` or
    `ignore` flag takes an item off that page; it must take it off this card too."""
    conn = seed(tmp_path)
    quiz = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    assert "Quiz 1" in [name for name, _ in trends.open_days(conn, now=NOW)]
    flags.set_flag(conn, quiz, "done", now="2026-09-15T15:00:00-04:00")
    assert "Quiz 1" not in [name for name, _ in trends.open_days(conn, now=NOW)]
    conn.close()


def test_open_days_drops_an_item_the_gradebooks_stopped_reporting(tmp_path):
    """A dead item's day count only grows, so one the sources have dropped climbs to the top
    of a ten-row chart and stays there. `reconcile.live_items`' `last_seen` bound is what
    keeps the card to work somebody can still act on."""
    conn = db.open_db(tmp_path)
    ingest.record(conn, snapshot(), tz=TZ, now=NOW)
    assert "Cell diagram" in [name for name, _ in trends.open_days(conn, now=NOW)]
    later = snapshot()                                             # Canvas stops listing it
    sci = later["students"]["Sam"]["canvas"]["courses"][0]
    sci["assignments"] = [a for a in sci["assignments"] if a["name"] != "Cell diagram"]
    later["fetched_at"] = "2026-09-15T13:55:00-04:00"
    ingest.record(conn, later, tz=TZ, now=datetime.fromisoformat(later["fetched_at"]))
    assert "Cell diagram" not in [name for name, _ in trends.open_days(conn, now=NOW)]
    assert "Safety quiz" in [name for name, _ in trends.open_days(conn, now=NOW)]   # still live
    conn.close()


# --- weekly_outcomes: the chart the Trends page actually shows (#40 item 5) -------------------

def test_weekly_outcomes_bucket_by_due_week_not_by_refresh_week(tmp_path):
    """One refresh, on the first day: `weekly_counts` puts everything in this week because
    that is when it was *seen*; `weekly_outcomes` spreads it over the weeks it was *due*."""
    conn = db.open_db(tmp_path)
    ingest.record(conn, snapshot(), tz=TZ, now=NOW)
    weeks = trends.weekly_outcomes(conn, weeks=4, now=NOW)
    assert [w.week_start for w in weeks] == sorted(w.week_start for w in weeks)
    assert weeks[-1].week_start == date(2026, 9, 14)
    settled = sum(w.on_time + w.late + w.not_done + w.done_offline + w.unknown for w in weeks)
    assert settled > 0
    assert sum(1 for w in weeks if any((w.on_time, w.late, w.not_done, w.done_offline, w.unknown))) >= 2, \
        "work due in more than one week must land in more than one bucket"
    conn.close()


def test_weekly_outcomes_agree_with_the_dashboard_record(tmp_path):
    """Same items, same classifier: the weekly table summed over a window that covers the
    whole year must equal the record line on the kid's card."""
    from lakota_grades.late_rules import LateRules, Rule
    from lakota_grades.web.stores import items, students
    conn = history(tmp_path)
    rules = LateRules(Rule(), [], [])
    for s in students.visible(conn):
        record = items.dashboard_counts(conn, s, now=NOW, rules=rules).record
        weeks = trends.weekly_outcomes(conn, student_id=s["id"], weeks=52, now=NOW)
        assert sum(w.on_time for w in weeks) == record.on_time, s["key"]
        assert sum(w.not_done for w in weeks) == record.not_done, s["key"]
        assert sum(w.unknown for w in weeks) == record.unknown, s["key"]
    conn.close()


def test_weekly_outcomes_treats_no_weeks_as_this_week(tmp_path):
    conn = history(tmp_path)
    assert [w.week_start for w in trends.weekly_outcomes(conn, weeks=0, now=NOW)] == [date(2026, 9, 14)]
    conn.close()


def test_open_days_measures_from_the_due_date_not_the_first_sighting(tmp_path):
    """Installed today, every open item used to read "0.2 days". Homework 4 has been due since
    8/20 and Quiz 1 since 9/12; with NOW on 9/15 that is ~26 days and ~3, and the month-old one
    comes first."""
    conn = history(tmp_path)
    rows = dict(trends.open_days(conn, now=NOW))
    assert 25 <= rows["Homework 4"] <= 27
    assert 2 <= rows["Quiz 1"] <= 4
    assert trends.open_days(conn, now=NOW)[0][0] == "Homework 4"
    conn.close()
