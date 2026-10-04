"""`[grading]` in config.toml: the report card's letter scale (spec 2026-10-03 §9)."""
from fridgesheet import config, grading


def test_settings_default_to_the_ten_point_scale(tmp_path):
    assert config.Settings(home=tmp_path).grading == grading.TEN_POINT


def test_a_grading_section_sets_the_scale(tmp_path):
    (tmp_path / "config.toml").write_text('[grading]\nscale = { A = 93, "A-" = 90, B = 83 }\nbelow = "C"\n', encoding="utf-8")
    s = config.Settings(home=tmp_path)
    config.settings_from_doc(config.load_config_doc(tmp_path / "config.toml"), s)
    assert s.grading.cuts == (("A", 93.0), ("A-", 90.0), ("B", 83.0)) and s.grading.letter(85) == "B" and s.grading.letter(10) == "C"


def test_a_bad_grading_section_keeps_the_default_without_raising(tmp_path):
    (tmp_path / "config.toml").write_text('[grading]\nscale = "ten"\n', encoding="utf-8")
    s = config.Settings(home=tmp_path)
    config.settings_from_doc(config.load_config_doc(tmp_path / "config.toml"), s)
    assert s.grading == grading.TEN_POINT
