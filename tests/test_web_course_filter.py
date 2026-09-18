"""The Kid page's Course filter names classes, not sources (#40 item 8)."""
from __future__ import annotations

import re

from lakota_grades.web.stores import students
from web_fixtures import app_for, seed


def test_a_paired_class_is_one_option_and_a_lone_one_says_its_source(tmp_path):
    conn = seed(tmp_path)
    sid = students.by_key(conn, "Alex")["id"]
    labels = [label for _, label in students.course_options(conn, sid)]
    conn.close()
    assert labels == sorted(labels, key=str.lower)
    assert "Honors English 9" in labels and "Algebra I" in labels
    assert not any("(canvas)" in l or "(hac)" in l for l in labels)
    assert len(labels) == len(set(labels))                      # no class listed twice


def test_filtering_by_the_class_shows_work_from_both_sources(tmp_path):
    """Participation is HAC-only, in the HAC twin of Honors English 9. Choosing the class must
    show it alongside the Canvas items -- that is what "the class" means to a parent."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    page = c.get("/kids/Alex", headers={"host": "127.0.0.1"}).text
    m = re.search(r'<option value="(\d+)"[^>]*>Honors English 9</option>', page)
    assert m, "one option for the class, no source suffix"
    both = c.get(f"/kids/Alex?show=all&course={m.group(1)}", headers={"host": "127.0.0.1"}).text
    assert "Participation" in both and "Quiz 1" in both
    assert "Homework 4" not in both                              # Algebra I: another class
