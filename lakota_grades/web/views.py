"""A view report: a JSON definition, the rows it selects, and the checks that keep it honest.

The rows come from the same stores the pages read, so a report can never disagree with the Kid,
Trends or Changes page about the same fact -- that is the whole reason this module has no SQL.
Every value is formatted to a string here, once, so the HTML table, the PDF and the CSV all show
the same text.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from .. import dates
from .stores import changes as changes_store, items as items_store, students as students_store, trends as trends_store

SOURCES = ("items", "grades", "changes")
OPS = ("is", "is not", "contains", "≥", "≤")
NUMERIC_OPS = ("≥", "≤")                # only a number column can answer these
ORIENTATIONS = ("portrait", "landscape")
DIRS = ("asc", "desc")
MAX_ROWS = 2000


class ViewError(RuntimeError):
    """The definition cannot be read or cannot be built."""


@dataclass(frozen=True)
class Column:
    id: str
    label: str
    kind: str                       # text | number | date | bool


def _cols(*specs: tuple[str, str, str]) -> dict[str, Column]:
    return {c[0]: Column(*c) for c in specs}


COLUMNS: dict[str, dict[str, Column]] = {
    "items": _cols(
        ("kid", "Kid", "text"), ("course", "Class", "text"), ("name", "Item", "text"),
        ("status", "Status", "text"), ("due", "Due", "date"), ("points", "Points", "number"),
        ("kind", "Kind", "text"), ("sources", "Seen in", "text"), ("flag", "Flag", "text"),
        ("open", "Open", "bool"), ("actionable", "Actionable", "bool"),
        ("notes", "Notes", "number"), ("cases", "Reconcile", "text"),
    ),
    "grades": _cols(
        ("kid", "Kid", "text"), ("course", "Class", "text"), ("source", "Source", "text"),
        ("label", "Series", "text"), ("value", "Value", "number"), ("at", "Seen", "date"),
    ),
    "changes": _cols(
        ("at", "When", "date"), ("kid", "Kid", "text"), ("what", "What", "text"),
        ("item", "Item", "text"), ("course", "Class", "text"), ("source", "Source", "text"),
        ("detail", "Detail", "text"),
    ),
}

DEFAULT_COLUMNS = {"items": ["kid", "course", "name", "status", "due"],
                   "grades": ["kid", "course", "source", "value", "at"],
                   "changes": ["at", "kid", "what", "item", "detail"]}


@dataclass(frozen=True)
class Definition:
    title: str = "Untitled report"
    source: str = "items"
    scope: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    filters: tuple[dict, ...] = ()
    group_by: str | None = None
    sort: tuple[dict, ...] = ()
    chart: None = None
    orientation: str = "portrait"
    per_kid_sections: bool = False

    def to_json(self) -> str:
        return json.dumps({
            "title": self.title, "source": self.source, "scope": list(self.scope),
            "columns": list(self.columns), "filters": [dict(f) for f in self.filters],
            "group_by": self.group_by, "sort": [dict(s) for s in self.sort], "chart": None,
            "orientation": self.orientation, "per_kid_sections": self.per_kid_sections,
        }, indent=1)


def defaults(source: str = "items") -> Definition:
    src = source if source in SOURCES else "items"
    return Definition(source=src, columns=tuple(DEFAULT_COLUMNS[src]))


def from_json(text: str) -> Definition:
    """Read a stored definition. Unknown keys are dropped, missing ones defaulted; anything that
    is not a JSON object, or whose fields are the wrong shape, is a `ViewError`."""
    try:
        raw = json.loads(text or "{}")
    except ValueError as e:
        raise ViewError(f"the definition is not JSON: {e}") from None
    if not isinstance(raw, dict):
        raise ViewError("the definition must be a JSON object")
    src = raw.get("source") if isinstance(raw.get("source"), str) else "items"
    d = defaults(src)
    def seq(key, default):
        v = raw.get(key)
        return tuple(v) if isinstance(v, list) else default
    try:
        return replace(
            d,
            title=str(raw.get("title", d.title)),
            source=src,
            scope=tuple(str(x) for x in seq("scope", ())),
            columns=tuple(str(x) for x in seq("columns", d.columns)),
            filters=tuple(dict(f) for f in seq("filters", ()) if isinstance(f, dict)),
            group_by=raw["group_by"] if isinstance(raw.get("group_by"), str) else None,
            sort=tuple(dict(s) for s in seq("sort", ()) if isinstance(s, dict)),
            orientation=str(raw.get("orientation", d.orientation)),
            per_kid_sections=_as_bool(raw.get("per_kid_sections", False)),
        )
    except (TypeError, ValueError) as e:
        raise ViewError(f"the definition has a field of the wrong shape: {e}") from None


def _as_bool(v) -> bool:
    """A JSON bool stays itself; a JSON string reads as its own word, so a form field or an
    old export that wrote `"false"` does not turn a truthy non-empty string into `True`."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() not in ("", "false", "0", "no")
    return bool(v)


def validate(d: Definition) -> list[str]:
    """Every problem with the definition, one sentence each. Empty means it can be built."""
    problems: list[str] = []
    if not d.title.strip():
        problems.append("The title cannot be empty.")
    if d.source not in SOURCES:
        problems.append(f"Unknown source {d.source!r}; choose one of {', '.join(SOURCES)}.")
        return problems                      # every other check depends on the source, and a
                                              # column that is fine on a real source would
                                              # otherwise be told it needs fixing
    known = COLUMNS[d.source]
    if not d.columns:
        problems.append("Choose at least one column.")
    for c in d.columns:
        if c not in known:
            problems.append(f"{c!r} is not a column of the {d.source} source.")
    for f in d.filters:
        field, op = f.get("field"), f.get("op")
        if field not in known:
            problems.append(f"The filter field {field!r} is not a column of the {d.source} source.")
        if op not in OPS:
            problems.append(f"{op!r} is not a filter operator; use one of {', '.join(OPS)}.")
        elif op in NUMERIC_OPS and field in known and known[field].kind != "number":
            # `_keep` can only answer >= / <= by reading both sides as numbers, so on a text or
            # date column it would quietly drop every row. Say so here instead.
            problems.append(f"The {known[field].label} column holds {known[field].kind}, not numbers, "
                            f"so it cannot be filtered with {op}.")
        if str(f.get("value", "")).strip() == "":
            problems.append("A filter needs a value.")
    if d.group_by is not None and d.group_by not in known:
        problems.append(f"Cannot group by {d.group_by!r}; it is not a column of the {d.source} source.")
    for s in d.sort:
        if s.get("column") not in known:
            problems.append(f"Cannot sort by {s.get('column')!r}; it is not a column of the {d.source} source.")
        if s.get("dir") not in DIRS:
            problems.append(f"{s.get('dir')!r} is not a sort direction; use asc or desc.")
    if d.orientation not in ORIENTATIONS:
        problems.append(f"Unknown orientation {d.orientation!r}; use portrait or landscape.")
    return problems


@dataclass
class Group:
    label: str
    rows: list[dict] = field(default_factory=list)


@dataclass
class Rendered:
    title: str
    columns: list[Column]
    groups: list[Group] = field(default_factory=list)
    truncated: int = 0               # rows dropped by MAX_ROWS


def _num(v) -> str:
    return "" if v is None else (f"{v:g}" if isinstance(v, (int, float)) else str(v))


def _date(v) -> str:
    if v is None:
        return ""
    d = datetime.fromisoformat(v) if isinstance(v, str) else v
    return dates.md(d) if isinstance(d, datetime) else str(d)


def _yes(v) -> str:
    return "yes" if v else "no"


def _as_datetime(v) -> datetime | None:
    if isinstance(v, datetime):
        return v
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return None
    return None


def _date_key(v) -> str:
    """A date as text that sorts chronologically -- which `dates.md`'s "9/8" does not, and that
    is the whole reason a display string is never the sort key. An aware timestamp is read in
    UTC first so two offsets cannot sort by their wall clocks; an unreadable value sorts first."""
    d = _as_datetime(v)
    if d is None:
        return ""
    if d.tzinfo is not None:
        d = d.astimezone(UTC)
    return d.replace(tzinfo=None).isoformat()


def _num_key(v) -> float:
    """A number as a float, so 9 sorts before 10. A blank or unreadable value sorts as 0."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return 0.0


def _keys(source: str, row: dict, raw: dict) -> dict:
    """The comparable value of every column of `row`, beside its display string.

    `raw` carries the unformatted value of each date and number column; everything else sorts on
    its own lowered display text, which is what it reads as anyway.
    """
    out: dict = {}
    for cid, col in COLUMNS[source].items():
        if col.kind == "date":
            out[cid] = _date_key(raw.get(cid))
        elif col.kind == "number":
            out[cid] = _num_key(raw.get(cid))
        else:
            out[cid] = str(row.get(cid, "")).lower()
    return out


def _item_rows(conn, d, *, now, rules, nicknames) -> list[tuple[dict, dict]]:
    out = []
    for s in students_store.visible(conn):
        if d.scope and s["key"] not in d.scope:
            continue
        for v in items_store.list_items(conn, s, now=now, rules=rules, show="all"):
            row = {
                "kid": nicknames.get(s["key"], s["key"]), "course": v.course_short, "name": v.name,
                "status": v.status, "due": _date(v.due), "points": _num(v.points), "kind": v.kind,
                "sources": " + ".join(v.sources), "flag": (v.flag or "").replace("_", " "),
                "open": _yes(v.overdue or v.upcoming), "actionable": _yes(v.actionable),
                "notes": _num(v.notes), "cases": ", ".join(k.replace("_", " ") for k in v.case_kinds),
            }
            out.append((row, _keys("items", row, {"due": v.due, "points": v.points, "notes": v.notes})))
    return out


def _grade_rows(conn, d, *, now, nicknames) -> list[tuple[dict, dict]]:
    out = []
    for s in students_store.visible(conn):
        if d.scope and s["key"] not in d.scope:
            continue
        for series in trends_store.grade_series(conn, student_id=s["id"]):
            for at, value in series.points:
                row = {"kid": nicknames.get(s["key"], s["key"]), "course": series.course_short,
                       "source": series.source, "label": series.label,
                       "value": _num(value), "at": _date(at)}
                out.append((row, _keys("grades", row, {"at": at, "value": value})))
    return out


def _change_rows(conn, d, *, now, nicknames) -> tuple[list[tuple[dict, dict]], int]:
    """Rows, plus how many events the store's own cap left out of the feed entirely -- a count
    `build` folds into `Rendered.truncated` so a household past the cap is told, not just shown
    fewer rows than it has."""
    keys = {s["key"] for s in students_store.visible(conn)}
    feed = changes_store.since(conn, since=now - timedelta(days=365), limit=MAX_ROWS)
    out = []
    for e in feed:
        if e.student_key not in keys or (d.scope and e.student_key not in d.scope):
            continue
        row = {"at": _date(e.at), "kid": nicknames.get(e.student_key, e.student_key),
               "what": e.label, "item": e.item_name or "", "course": e.course_short or "",
               "source": e.source or "", "detail": e.detail}
        out.append((row, _keys("changes", row, {"at": e.at})))
    return out, feed.dropped


def _keep(row: dict, f: dict) -> bool:
    got, want, op = row.get(f["field"], ""), str(f["value"]).strip(), f["op"]
    if op in NUMERIC_OPS:
        try:
            a, b = float(got or 0), float(want)
        except ValueError:
            return False
        return a >= b if op == "≥" else a <= b
    a, b = got.lower(), want.lower()
    if op == "is":
        return a == b
    if op == "is not":
        return a != b
    return b in a


def build(conn: sqlite3.Connection, d: Definition, *, now: datetime, rules, nicknames: dict) -> Rendered:
    """Definition to rows. Raises `ViewError` when the definition does not validate."""
    problems = validate(d)
    if problems:
        raise ViewError(" ".join(problems))
    dropped = 0
    if d.source == "items":
        pairs = _item_rows(conn, d, now=now, rules=rules, nicknames=nicknames)
    elif d.source == "grades":
        pairs = _grade_rows(conn, d, now=now, nicknames=nicknames)
    else:
        pairs, dropped = _change_rows(conn, d, now=now, nicknames=nicknames)
    for f in d.filters:
        pairs = [p for p in pairs if _keep(p[0], f)]
    # Sort on the comparable value beside each row, never on the display string: "9/8" is after
    # "9/20" as text, and a report must not disagree with the Kid page about what comes first.
    for s in reversed(d.sort):                     # stable sorts, least significant first
        pairs.sort(key=lambda p, c=s["column"]: p[1][c], reverse=s["dir"] == "desc")
    truncated = max(0, len(pairs) - MAX_ROWS) + dropped  # rows cut here, plus rows the store
                                                          # never handed back because of its own cap
    rows = [p[0] for p in pairs[:MAX_ROWS]]
    columns = [COLUMNS[d.source][c] for c in d.columns]
    slim = [{c.id: r.get(c.id, "") for c in columns} | ({d.group_by: r.get(d.group_by, "")} if d.group_by else {})
            for r in rows]
    groups: list[Group] = []
    if d.group_by:
        seen: dict[str, Group] = {}
        for r in slim:
            label = r.get(d.group_by, "")
            g = seen.get(label)
            if g is None:
                g = seen[label] = Group(label)
                groups.append(g)
            g.rows.append({c.id: r[c.id] for c in columns})
        groups.sort(key=lambda g: g.label)
    elif slim:
        groups = [Group("", [{c.id: r[c.id] for c in columns} for r in slim])]
    return Rendered(d.title, columns, groups, truncated)
