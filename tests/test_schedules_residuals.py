"""#7 residuals: task names always sanitised, systemd command lines quoted, and an unmanageable
schedule row that cannot be edited."""
from __future__ import annotations

from fridgesheet import host
from fridgesheet.host import scheduling_linux, service_linux
from tests.web_fixtures import FakeScheduling, app_for, seed


def test_every_task_name_is_sanitised_but_existing_names_do_not_move():
    assert host.task_name("open-work") == "Fridge Sheet - open-work"          # unchanged: installed tasks keep their name
    assert host.task_name("view:7") == "Fridge Sheet - view 7"
    assert "\\" not in host.task_name("odd\\key") and "/" not in host.task_name("a/b")   # a hand-edited key cannot make a task path


def test_a_python_path_with_a_space_survives_systemd():
    """#7: `ExecStart={exe} {args}` split "/home/x/My Venv/bin/python" at the space."""
    exe = "/home/x/My Venv/bin/python"
    for text in (scheduling_linux.service_text("open-work", "Open Work", exe, "-m fridgesheet.cli run open-work", "/home/x", "/home/x/.fridgesheet"),
                 service_linux.unit_text(exe, "-m fridgesheet.cli web --no-browser", "/home/x")):
        line = next(l for l in text.splitlines() if l.startswith("ExecStart="))
        assert line.startswith('ExecStart="/home/x/My Venv/bin/python" -m fridgesheet.cli'), line
    plain = service_linux.unit_text("/usr/bin/python3", "-m fridgesheet.cli web", "/x")
    assert "ExecStart=/usr/bin/python3 -m fridgesheet.cli web" in plain                     # nothing to quote, nothing added


def test_an_unmanageable_rows_fields_are_all_disabled(tmp_path):
    """#7: the Save button and the switch were disabled on a hand-written schedule's row, but
    its time, days, printer and print box still looked editable."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    c.app.state.fridgesheet.extra["scheduling"] = FakeScheduling(
        info={"open-work": host.ScheduleInfo("systemd (hand-written)", True, "Wed 14:00", None, False)})
    body = c.get("/schedules").text
    form = body[body.index('value="open-work"') if 'value="open-work"' in body else body.index("open-work"):]
    form = form[:form.index("</form>")]
    for field in ('type="time"', 'name="days"', 'name="printer"', 'name="prints"'):
        tag = form[form.rindex("<", 0, form.index(field)):form.index(">", form.index(field))]
        assert "disabled" in tag, field
