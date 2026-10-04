"""HAC Classwork rows (hac.parse_row): the cell lists as the page renders them, captured
2026-10-04. A weighted class's category table has six columns (Category, Student's Points,
Maximum Points, Percent, Category Weight, Category Points); the scraper used to keep only
four-column rows and dropped every weighted class's table."""
from fridgesheet import hac


def test_an_assignment_row_is_an_assignment():
    kind, row = hac.parse_row(["10/02/2026", "10/02/2026", "Slope Quiz #2", "Test", "6.00", "6.00", "1.00", "6.00", "6.00", "100.00%", "100.00%"])
    assert kind == "assignment" and row["category"] == "Test" and row["points"] == 6.0 and row["percent"] == "100.00%"


def test_a_four_column_category_row_has_no_weight():
    kind, row = hac.parse_row(["Labs", "36.0000", "60.00", "60.000%"])
    assert kind == "category" and row == {"category": "Labs", "earned": 36.0, "possible": 60.0, "percent": "60.000%", "weight": None}


def test_a_six_column_category_row_carries_its_weight():
    kind, row = hac.parse_row(["Quiz", "11.0000", "17.00", "64.705%", "1.00", "0.647060"])
    assert kind == "category" and row == {"category": "Quiz", "earned": 11.0, "possible": 17.0, "percent": "64.705%", "weight": 1.0}


def test_anything_else_is_ignored():
    assert hac.parse_row(["Total", "", ""]) == (None, None) and hac.parse_row([]) == (None, None)
