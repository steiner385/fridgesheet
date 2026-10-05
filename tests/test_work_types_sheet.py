"""The family on the printed sheet and in the MCP server's order (assignment types §6.2)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("reportlab")

from fridgesheet import open_items, sheet, work_types  # noqa: E402

NOW = datetime(2026, 9, 11, 14, 0, tzinfo=ZoneInfo("America/New_York"))


def _item(name="Unit Test", **kw):
    d = dict(key="canvas:1", kid="Al", course="Biology", name=name, due=NOW, status="MISSING",
             overdue=True, source="canvas", kind="paper")
    d.update(kw)
    return open_items.Item(**d)


def test_an_item_defaults_to_everyday_work_and_carries_its_family_out():
    assert _item().family == "practice"
    assert _item(family="assessment").to_dict()["family"] == "assessment"


def test_the_via_cell_names_the_family_but_not_everyday_work():
    assert sheet.via_text(_item(family="assessment"), "") == "Canvas · paper · test/quiz"
    assert sheet.via_text(_item(family="lab_project"), "early") == "Canvas · paper · lab or project"
    assert sheet.via_text(_item(family="practice"), "") == "Canvas · paper"
    assert sheet.via_text(_item(kind="", source="hac", family="practice"), "") == "Hac · —"


def test_the_snapshot_path_classifies_from_the_group_and_the_hac_category():
    entry = {"canvas": {"courses": [{"id": 1, "name": "Biology S1", "assignments": [
        {"id": 7, "name": "Cells", "due_at": "2026-09-08T23:59:00-04:00", "points_possible": 10.0, "submission_types": ["online_upload"],
         "group": "Labs", "missing": True, "state": "unsubmitted", "score": None, "excused": False, "late": False}]}]},
        "hac": {"classes": []}}
    work = open_items.open_items(entry, "Al", NOW, days_ahead=14)
    assert [(i.name, i.family, i.is_assessment) for i in work.items] == [("Cells", "lab_project", False)]


def test_mcp_order_is_tests_first_then_points():
    rows = [{"family": "practice", "points": 50}, {"family": "assessment", "points": 5}, {"family": "lab_project", "points": 20}]
    rows.sort(key=lambda r: (work_types.RANK.get(r["family"], len(work_types.RANK)), -(r["points"] or 0)))
    assert [r["family"] for r in rows] == ["assessment", "lab_project", "practice"]
