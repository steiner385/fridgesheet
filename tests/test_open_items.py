"""One definition of "open work" for both the MCP tools and the printed sheet.

Open = Canvas items not yet submitted (past due: missing / zero / paper-check; upcoming:
due within the window) plus HAC rows with a blank score after their due date, deduped
against Canvas. Overdue items are shown only while the class still gives credit for them.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from fridgesheet import late_rules, open_items

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 11, 14, 0, tzinfo=TZ)  # a Friday


def iso(days: float, hour: int = 23, minute: int = 59) -> str:
    d = (NOW + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return d.isoformat()


def canvas_item(**over) -> dict:
    a = {
        "id": over.pop("id", 1), "name": "WS 1", "due_at": iso(-1), "unlock_at": iso(-3), "created_at": iso(-20),
        "points_possible": 10.0, "submission_types": ["online_upload"], "group": "Homework", "published": True,
        "score": None, "grade": None, "state": "unsubmitted", "late": False, "missing": False, "excused": False,
    }
    a.update(over)
    return a


def entry(assignments: list[dict], course="Honors Biology S1-2027-Nance", hac_classes=None) -> dict:
    return {
        "name": "Alex Example",
        "canvas": {"courses": [{"id": 5, "name": course, "assignments": assignments}]},
        "hac": {"classes": hac_classes or []},
    }


@pytest.fixture
def rules(tmp_path):
    p = tmp_path / "late-rules.toml"
    p.write_text('[default]\nlate_days = 14\ncredit = "?"\n\n[[rule]]\ncourse = "Biology"\nlate_days = 7\ncredit = "50%"\n')
    return late_rules.load(p)


def run(e, rules, **kw):
    return open_items.open_items(e, "Al", NOW, rules=rules, **kw)


def test_missing_item_is_overdue_with_deadline_and_credit(rules):
    work = run(entry([canvas_item(missing=True)]), rules)
    (it,) = work.items
    assert it.status == "MISSING" and it.overdue
    assert it.course == "Honors Biology"
    assert it.late_until == datetime.fromisoformat(iso(6))
    assert it.credit == "50%"
    assert it.source == "canvas" and it.kind == "online"
    assert it.assigned == datetime.fromisoformat(iso(-3))


def test_graded_zero_is_zero_and_ungraded_late_is_late(rules):
    work = run(entry([
        canvas_item(id=1, state="graded", score=0.0),
        canvas_item(id=2, state="submitted", late=True, due_at=iso(-2)),
        canvas_item(id=3, state="graded", score=8.0, late=True),  # graded late: nothing left to do
    ]), rules)
    assert [(i.key, i.status) for i in work.items] == [("canvas:2", "LATE"), ("canvas:1", "ZERO")]


def test_past_due_paper_item_without_grade_is_check_not_missing(rules):
    (it,) = run(entry([canvas_item(submission_types=["on_paper"])]), rules).items
    assert it.status == "PAPER — CHECK" and it.kind == "paper" and it.overdue


def test_upcoming_statuses_and_window(rules):
    work = run(entry([
        canvas_item(id=1, due_at=iso(0, 15, 0)),
        canvas_item(id=2, due_at=iso(1)),
        canvas_item(id=3, due_at=iso(3)),
        canvas_item(id=4, due_at=iso(15)),
    ]), rules, days_ahead=14)
    assert [(i.key, i.status) for i in work.items] == [("canvas:1", "DUE TODAY"), ("canvas:2", "DUE TOMORROW"), ("canvas:3", "DUE MON")]
    assert not work.items[0].overdue


def test_items_past_the_late_deadline_are_dropped_not_shown(rules):
    work = run(entry([canvas_item(id=1, missing=True, due_at=iso(-8)), canvas_item(id=2, missing=True, due_at=iso(-6))]), rules)
    assert [i.key for i in work.items] == ["canvas:2"]
    assert [i.key for i in work.dropped] == ["canvas:1"]
    assert work.dropped[0].points == 10.0


def test_items_older_than_overdue_days_are_dropped_even_if_rules_allow(tmp_path):
    p = tmp_path / "r.toml"
    p.write_text("[default]\nlate_days = 60\n")
    work = run(entry([canvas_item(missing=True, due_at=iso(-15))]), late_rules.load(p), overdue_days=14)
    assert work.items == [] and [i.key for i in work.dropped] == ["canvas:1"]


def test_previous_year_course_copy_artifacts_are_ignored_entirely(rules):
    work = run(entry([canvas_item(missing=True, due_at="2025-10-09T23:59:00-04:00")]), rules)
    assert work.items == [] and work.dropped == []


def test_excused_unpublished_and_untouched_undated_items_are_skipped(rules):
    work = run(entry([
        canvas_item(id=1, missing=True, excused=True),
        canvas_item(id=2, missing=True, published=False),
        canvas_item(id=3, due_at=None),
    ]), rules)
    assert work.items == []


def test_undated_work_the_teacher_marked_prints_with_no_window(rules):
    """No due date can never pass, so a missing mark or a zero is what puts undated work on
    the sheet, as it puts it on the record (docs/outcomes.md, #137): no due date, no credit
    line, never too old."""
    work = run(entry([canvas_item(id=1, missing=True, due_at=None), canvas_item(id=2, state="graded", score=0, due_at=None)]), rules)
    assert [(i.key, i.status, i.due, i.late_until, i.overdue) for i in work.items] == \
        [("canvas:1", "MISSING", None, None, True), ("canvas:2", "ZERO", None, None, True)]
    assert work.dropped == []


def test_hac_blank_row_is_shown_and_paired_canvas_item_is_not_duplicated(rules):
    hac = [{"name": "Honors Biology - 3", "assignments": [
        {"name": "WS 1", "assigned": "09/07/2026", "due": "09/10/2026", "score": None, "score_raw": "", "points": 10.0, "category": "Homework"},
        {"name": "Lab Safety Contract", "assigned": "09/01/2026", "due": "09/08/2026", "score": None, "score_raw": "", "points": 5.0, "category": "Labs"},
        {"name": "Quiz 1", "assigned": "09/01/2026", "due": "09/09/2026", "score": 18.0, "score_raw": "18.00", "points": 20.0, "category": "Quizzes"},
    ]}]
    work = run(entry([canvas_item(missing=True)], hac_classes=hac), rules)
    # the HAC-only key is matching.hac_only_key: the short course, the normalised name and the
    # due date, so it is the same string the database stores and a flag set in the app can find it.
    assert [(i.key, i.status) for i in work.items] == [("hac:Honors Biology:lab safety contract:2026-09-08", "HAC — NO GRADE"), ("canvas:1", "MISSING")]
    canvas_row = work.items[1]
    assert canvas_row.source == "both"
    assert canvas_row.assigned == datetime(2026, 9, 7, tzinfo=TZ)   # HAC's assigned date wins
    assert work.items[0].kind == ""


def test_include_hac_false_leaves_only_canvas(rules):
    hac = [{"name": "Honors Biology - 3", "assignments": [
        {"name": "Lab Safety Contract", "assigned": "09/01/2026", "due": "09/08/2026", "score": None, "score_raw": "", "points": 5.0, "category": "Labs"}]}]
    work = run(entry([canvas_item(missing=True)], hac_classes=hac), rules, include_hac=False)
    assert [i.key for i in work.items] == ["canvas:1"]


def test_overdue_first_then_upcoming_each_by_due_date(rules):
    work = run(entry([
        canvas_item(id=1, due_at=iso(2)),
        canvas_item(id=2, missing=True, due_at=iso(-1)),
        canvas_item(id=3, due_at=iso(1)),
        canvas_item(id=4, missing=True, due_at=iso(-3)),
    ]), rules)
    assert [i.key for i in work.items] == ["canvas:4", "canvas:2", "canvas:3", "canvas:1"]


def test_compare_reports_new_changed_and_cleared(rules):
    before = run(entry([canvas_item(id=1, due_at=iso(1)), canvas_item(id=2, due_at=iso(2))]), rules)
    prev_rows = [i.to_dict() for i in before.items]
    later = run(entry([canvas_item(id=2, missing=True, due_at=iso(-1)), canvas_item(id=3, due_at=iso(1))]), rules)
    d = open_items.compare(prev_rows, later.items)
    assert d.new == {"canvas:3"}
    assert d.changed == {"canvas:2": "DUE SUN"}
    assert [r["key"] for r in d.cleared] == ["canvas:1"]
    # an item struck off with a handled flag was not cleared by the kid; the sheet reports it
    # in the handled trailer instead, so it belongs in neither list
    handled = open_items.open_items(entry([canvas_item(id=1, due_at=iso(1))]), "Al", NOW,
                                    rules=rules, flags={"canvas:1": "done"})
    d = open_items.compare(prev_rows, later.items, handled.handled)
    assert d.cleared == [] and d.new == {"canvas:3"}


def test_to_dict_round_trips_datetimes_as_iso(rules):
    (it,) = run(entry([canvas_item(missing=True)]), rules).items
    d = it.to_dict()
    assert d["due"] == iso(-1) and d["late_until"] == iso(6) and d["status"] == "MISSING"


def _entry_with_two_missing():
    a = lambda i, name: {"id": i, "name": name, "due_at": (NOW - timedelta(days=2)).isoformat(), "unlock_at": None, "created_at": None,  # noqa: E731
                         "points_possible": 10.0, "submission_types": ["online_upload"], "group": "Homework", "published": True,
                         "score": None, "grade": None, "state": "unsubmitted", "late": False, "missing": True, "excused": False}
    return {"name": "Alex Example", "canvas": {"courses": [{"id": 5, "name": "Honors Biology S1-2027-Nance", "assignments": [a(1, "WS 1"), a(2, "WS 2")]}]}, "hac": {"classes": []}}


def test_handled_flags_remove_items_and_marked_flags_annotate():
    work = open_items.open_items(_entry_with_two_missing(), "Al", NOW, flags={"canvas:1": "done", "canvas:2": "ask_teacher"})
    assert [i.key for i in work.items] == ["canvas:2"] and work.items[0].flag == "ask_teacher"
    assert [i.key for i in work.handled] == ["canvas:1"] and work.handled[0].flag == "done"
    assert work.dropped == []
    assert "flag" in work.items[0].to_dict()
    assert open_items.HANDLED_FLAGS == ("done", "excused", "ignore", "too_late") and open_items.MARKED_FLAGS == ("follow_up", "ask_teacher")


def test_no_flags_means_no_change():
    work = open_items.open_items(_entry_with_two_missing(), "Al", NOW)
    assert len(work.items) == 2 and work.handled == [] and all(i.flag == "" for i in work.items)


def test_paper_work_graded_in_hac_is_done_and_not_on_the_sheet(rules):
    """Canvas lists paper work as unsubmitted forever; HAC's grade is the proof it was handed
    in. Seen live: "Concert Contract Due", 10/10 in HAC, was printing as PAPER — CHECK."""
    e = entry([canvas_item(id=1, name="Concert Contract Due", submission_types=["on_paper"])])
    hac_class = e["canvas"]["courses"][0]["name"]            # the HAC twin of the fixture's course
    e["hac"] = {"classes": [{"name": hac_class, "assignments": [
        {"name": "Concert Contract Due", "due": "09/10/2026", "assigned": "09/01/2026", "score": 10.0, "score_raw": "10.00", "points": 10.0}]}]}
    assert run(e, rules).items == []
    # ... and so does Canvas's MISSING flag: HAC's grade beats it (docs/outcomes.md). The sheet
    # has no refresh history, so it cannot see a flag set after the grade; the web app asks.
    e2 = entry([canvas_item(id=1, name="Concert Contract Due", submission_types=["on_paper"], missing=True)])
    e2["hac"] = e["hac"]
    assert run(e2, rules).items == []


from fridgesheet import sources  # noqa: E402

HAC = sources.DEFAULT.with_default("hac", "hac")


def hac_class(rows, name="Honors Biology - 3"):
    return [{"name": name, "assignments": rows}]


def hac_row(name, score, points=10.0):
    return {"name": name, "due": "09/10/2026", "assigned": "09/01/2026", "category": "Homework", "points": points,
            "score": score, "score_raw": "" if score is None else f"{score:.2f}"}


def test_hac_preference_drops_canvas_missing_when_hac_graded_it(rules):
    e = entry([canvas_item(missing=True)], hac_classes=hac_class([hac_row("WS 1", 9.0)]))
    assert run(e, rules).items == []                  # HAC's grade beats the automatic flag under either preference
    assert run(e, rules, prefs=HAC).items == []


def test_hac_zero_prints_zero_under_hac_preference(rules):
    """Review focus 5, on paper."""
    e = entry([canvas_item(state="graded", score=8.0, grade="8")], hac_classes=hac_class([hac_row("WS 1", 0.0)]))
    assert run(e, rules).items == []
    (it,) = run(e, rules, prefs=HAC).items
    assert it.status == "ZERO" and it.score == 0.0 and it.overdue


def test_hac_preference_without_a_hac_score_changes_nothing(rules):
    e = entry([canvas_item(missing=True)], hac_classes=hac_class([hac_row("WS 1", None)]))
    assert [i.status for i in run(e, rules, prefs=HAC).items] == ["MISSING"]


def test_rules_resolve_by_first_name_not_the_printed_nickname(rules):
    p = sources.DEFAULT.with_rule("Alex", "Honors Biology", "hac", None)
    e = entry([canvas_item(missing=True)], hac_classes=hac_class([hac_row("WS 1", 9.0)]))
    assert open_items.open_items(e, "Dougie", NOW, rules=rules, prefs=p).items == []


# --- a HAC grade beats Canvas's automatic missing on the sheet too (docs/outcomes.md) -------------

def _entry_with_ws(hac_score):
    hac = [{"name": "Honors Biology - 3", "assignments": [
        {"name": "WS 1", "score": hac_score, "due": "09/10/2026", "assigned": "09/01/2026", "points": 10.0}]}]
    return entry([canvas_item(missing=True)], hac_classes=hac)


def test_a_hac_grade_drops_an_auto_missing_row_from_the_sheet():
    work = open_items.open_items(_entry_with_ws(9.0), "Alex", NOW)
    assert "WS 1" not in [i.name for i in work.items]


def test_a_hac_zero_keeps_the_missing_row():
    work = open_items.open_items(_entry_with_ws(0.0), "Alex", NOW)
    assert "WS 1" in [i.name for i in work.items]


# --- #133 / #134: the sheet resolves late rules the way the web does ----------------------------

def _two_day_rule(tmp_path, body):
    p = tmp_path / "late-rules.toml"
    p.write_text('[default]\nlate_days = 14\n\n[[rule]]\n' + body + 'late_days = 2\ncredit = "50%"\n')
    return late_rules.load(p)


def test_late_rules_resolve_by_the_students_name_not_the_printed_nickname(tmp_path):
    """Robert, printed as Bobby: a rule for Robert closes his work after 2 days on paper too."""
    rules = _two_day_rule(tmp_path, 'kid = "Robert"\n')
    e = {**entry([canvas_item(missing=True, due_at=iso(-4))]), "name": "Robert Example"}
    work = open_items.open_items(e, "Bobby", NOW, rules=rules)
    assert work.items == [] and [i.credit for i in work.dropped] == ["50%"]


def test_late_rules_resolve_by_the_snapshot_key_when_given(tmp_path):
    """The web resolves by the student's key; the sheet does too when it has one."""
    rules = _two_day_rule(tmp_path, 'kid = "Robert"\n')
    e = {**entry([canvas_item(missing=True, due_at=iso(-4))]), "name": "Bob Example"}
    assert open_items.open_items(e, "Bobby", NOW, rules=rules, student_key="Robert").items == []


def test_a_hac_only_row_takes_a_rule_written_against_the_canvas_name(tmp_path):
    rules = _two_day_rule(tmp_path, 'course = "Honors Biology S1"\n')
    hac = [{"name": "Hon Bio - 3", "assignments": [
        {"name": "Lab Safety Contract", "assigned": "09/01/2026", "due": "09/08/2026", "score": None, "score_raw": "", "points": 5.0, "category": "Labs"},
    ]}]
    work = run(entry([canvas_item(missing=True, due_at=iso(-1))], hac_classes=hac), rules)
    assert [i.key for i in work.items] == ["canvas:1"]
    assert [(i.key, i.credit) for i in work.dropped] == [("hac:Hon Bio:lab safety contract:2026-09-08", "50%")]


def test_a_canvas_row_takes_a_rule_written_against_the_hac_name(tmp_path):
    rules = _two_day_rule(tmp_path, 'course = "Hon Bio"\n')
    hac = [{"name": "Hon Bio - 3", "assignments": []}]
    work = run(entry([canvas_item(missing=True, due_at=iso(-4))], hac_classes=hac), rules)
    assert work.items == [] and [i.credit for i in work.dropped] == ["50%"]
