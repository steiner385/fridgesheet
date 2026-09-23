# Source of truth per family, kid and class: design

Date: 2026-09-22. Status: approved in discussion, awaiting review of this document.
Amends the "Which source is the source of truth" section of `docs/outcomes.md` and the
`config.toml` layout in `2026-09-14-windows-sheet-app-design.md`. Ingest, the database
schema and the pairing rules are unchanged.

## 1. Goal

Let a family say which source is authoritative for **grade averages** and which for
**assignment scores**, in any combination of Canvas and Home Access Center (HAC), and let
that answer differ for one kid or one class. The default stays what the app does today:
Canvas for assignments, HAC for grades.

The app keeps reading and storing both sources. This setting decides only which value is
shown and reasoned about when both have one.

## 2. Why this shape

Three decisions were taken in discussion, each checked against the real snapshot of
2026-09-21.

**Level.** A household default plus one list of override rules, each rule naming an
optional kid and an optional course. One rule with only a kid is a per-child setting; one
with only a course applies to that class for every kid; one with both is the finest grain.
This is the shape `late-rules.toml` already uses, and its name-based matching survives the
semester rollover that would leave a per-course-ID table pointing at dead rows. Per-child
alone cannot express Band, which is graded only in HAC; per-class alone means roughly
twenty entries that go stale each term when the default already covers most of them.

**Conflicts.** The chosen source wins when both have a value. The other still fills gaps:
an unpaired class, a HAC-only worksheet, a kid whose school uses one system. Excluding the
other source outright would drop the 95 HAC-only rows (86 of them graded) that never
appear in Canvas, and would drop Canvas submission facts for a class whose scores come
from HAC.

**No assignment-kind matcher.** The idea that paper work "lives in HAC" was tested and
does not hold here. Of 27 past-due paper assignments in Canvas, 20 are graded in Canvas;
the one scored only in HAC is an excusal. No paper or in-class item is flagged missing by
Canvas. Every real score disagreement in the snapshot is one teacher's online work
(Honors Algebra II: Canvas 12.5/50 against HAC 48/50, and three more like it), which a
kid-plus-course rule fixes in one line. Kind can be added as a matcher later if a snapshot
ever shows the pattern.

## 3. Configuration

A new `[sources]` table in `~/.fridgesheet/config.toml`:

```toml
[sources]
assignments = "canvas"        # household defaults; these are the built-in values
grades = "hac"

[[sources.rule]]              # kid and course are optional and matched like late-rules:
kid = "Douglas"               #   kid is a prefix match either way (Alex ~ Alexander)
course = "Honors Algebra II"  #   course is a case-insensitive substring of the class name
assignments = "hac"           #   or of its short name; a rule may set one field or both
```

- Values are `"canvas"` or `"hac"`. Any other value logs a warning naming the key and the
  rule, and that field is treated as unset. Config load never fails because of this table;
  a typo in a preference must not take the app down.
- Each field resolves independently: the first rule in file order that matches the kid and
  course **and sets that field** wins; otherwise the household default; otherwise the
  built-in default. So a per-kid grades rule and a per-class assignments rule compose
  without either having to restate the other.
- Unknown keys inside `[sources]` are ignored, like every other table, so older builds
  read the file untouched.
- Environment variables do not override this table. There is nothing to migrate from.

### 3.1 The resolver

New module `fridgesheet/sources.py`, modelled on `late_rules.py`:

```python
@dataclass(frozen=True)
class Choice:
    assignments: str = "canvas"
    grades: str = "hac"

class SourcePrefs:
    default: Choice
    rules: list[SourceRule]          # kid, course, assignments|None, grades|None
    def resolve(self, kid: str, course: str) -> Choice
    def rule_for(self, kid: str, course: str) -> SourceRule | None   # exact kid+course match, for the course-page control
    def with_rule(self, kid, course, assignments, grades) -> SourcePrefs   # replace or add
    def without_rule(self, kid, course) -> SourcePrefs
    def to_doc(self) -> dict          # the [sources] table, for save_config_doc
```

`SourceRule.matches` reuses the kid-prefix and course-substring logic from
`late_rules.Rule.matches`, extracted into `matching.py` so both files share it.
`Settings` gains a `sources: SourcePrefs` field populated by `settings_from_doc`.

## 4. Where the choice is applied

Ingest (`web/ingest.py`) does not change. It keeps storing a Canvas observation and a HAC
observation per item, and one `grade_observations` row per source course. Switching a rule
is therefore retroactive and reversible, and Changes and Trends history is intact.

The resolver is consulted at read time, wherever the code picks one source's value today.
Every one of these currently hard-codes Canvas first (assignments) or shows both with no
preference (grades).

| surface | today | becomes |
|---|---|---|
| `web/outcomes.classify` score selection | Canvas score, else HAC | preferred source's score, else the other |
| `stores/items.grade_text`, `status_text` | Canvas first | preferred first |
| `open_items` (printed sheet, MCP `open_items`) | Canvas item, HAC score fills | preferred score; HAC score still suppresses PAPER — CHECK |
| Course page headline average | Canvas current, then HAC average | preferred source's average as the headline, the other as a labelled second line |
| MCP `grades()` | `hac_official` and `canvas_current` side by side | both kept, plus `official` = the resolved average and `official_source` |
| Trends default series, Changes grade events | one series per source | preferred source is the default series; the other remains selectable |
| Report builder "grades" source | one column per source | resolved average is the default column |

Rules of application:

- **Submission facts stay Canvas.** Submitted, late, missing and excused come from Canvas
  regardless of the assignments preference, because HAC has no submission record. The
  assignments preference governs the score and therefore done-or-not.
- **Gap fill.** When the preferred source has no value, the other's value is used and the
  existing source labels ("HAC average", "Canvas current", the `source` column) make that
  visible. No new "fell back" indicator is needed.
- **Threading.** `list_items`, `_views`, `open_work` and friends already take `rules` (the
  late-work register) as a keyword argument. `prefs` travels the same way, and
  `classify(item, obs, now, prefer="canvas")` gains a keyword with today's behaviour as
  the default so `reconcile.py` and `trends.py` keep working until they pass it.
- **Kid and course names.** The resolver is called with the student's snapshot key and the
  course's full name. For a paired class it is called once with the Canvas course name;
  the Canvas and HAC names are close enough that a substring rule written from either side
  matches, and the course-page control writes the name it displays.
- **Disagreements stay visible.** `reconcile.cases` kind `"disagree"` is unchanged. A rule
  decides which number is the headline; it does not hide that the sources differ.

## 5. Editing

**Settings page.** Two dropdowns, "Assignments come from" and "Grades come from", each
offering Canvas or HAC, saved into `[sources]` through the existing `FormValues` and
`actions.save` path. Below them, the current rule list rendered as a table (kid, class,
assignments, grades) with a remove button per row. No add form here; rules are added from
the class they apply to.

**Course page.** A small "Sources for this class" control with two selects, assignments
and grades, each offering Canvas, HAC or "household default". Saving posts to
`POST /kids/{key}/courses/{course_id}/sources`, which writes or replaces the rule with
`kid` = the student's key and `course` = the course's full name. Choosing "household
default" for both removes the rule. The control shows the resolved choice, and says when a
broader rule (kid only, or course only) is what is currently deciding.

Both write through `save_config_doc`, so the file keeps its 0600 mode and atomic replace.
There is no separate rules file: `config.toml` already holds the per-kid nicknames table,
and adding a second TOML file for two fields would be a third place to look.

## 6. Documentation

- `docs/outcomes.md`, "Which source is the source of truth": add that the default can be
  changed per family, kid or class, describe the resolution order, and record the snapshot
  finding that paper work is mostly graded in Canvas here.
- `README.md`: add the `[sources]` table to the `config.toml` example, with the Honors
  Algebra II rule as the worked example.
- `server.py` `grades()` docstring: drop "HAC is the gradebook of record" in favour of
  "the configured official source".

## 7. Testing

- `tests/test_sources.py`: resolution order (rule beats default beats built-in), per-field
  independence, kid prefix and course substring matching, bad values warn and fall
  through, round trip through `to_doc` and `settings_from_doc`, `with_rule` replaces
  rather than duplicates.
- `tests/test_web_outcomes.py`: the same paired item classified under
  `prefer="canvas"` and `prefer="hac"`, including the case Canvas flags missing while HAC
  holds a score, pinned as `test_honors_algebra_quiz_canvas_missing_hac_48` from the real
  data.
- `tests/test_web_kid_table.py`: `grade_text` and `status_text` under both preferences;
  gap fill when the preferred source has nothing.
- `tests/test_open_items.py`: the printed sheet's score under both preferences.
- `tests/test_web_settings_page.py`: dropdown round trip; remove-rule button.
- `tests/test_web_server.py`: the course-page control writes, replaces and removes a
  rule; "household default" on both fields deletes it.
- `tests/test_server_tools.py`: `grades()` returns `official` from the preferred source
  and falls back when that source has no average.
- `tests/test_config.py`: `[sources]` parses into `Settings.sources`; a bad value warns
  and does not fail the load.
- Existing ingest and pairing tests must pass unchanged, since ingest is untouched.

## 8. Out of scope

- A matcher on assignment kind (paper, online, in class). Rejected on the evidence above;
  the rule schema leaves room for it.
- Excluding a source entirely for a kid or class. Hiding is a different feature and the
  `hidden` columns already exist for it.
- Reconciling score disagreements automatically. They stay listed under Changes.
- A stored Canvas-to-HAC course mapping. Pairing stays name-based; the alias environment
  variable remains the escape hatch.
