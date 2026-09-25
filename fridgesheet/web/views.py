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
from datetime import UTC, date as _date, datetime, timedelta

from .. import dates
from ..open_items import school_year_start
from . import reconcile, verdicts
from .stores import changes as changes_store, items as items_store, students as students_store, trends as trends_store

SOURCES = ("items", "grades", "changes")
OPS = ("is", "is not", "contains", "≥", "≤")
NUMERIC_OPS = ("≥", "≤")                # only a number column can answer these
ORIENTATIONS = ("portrait", "landscape")
#: How far back a report's rows reach (#94): (key, label, days, or None for "any time").
#: "school_year" starts on the school year's first day. "Any time" is what every report did
#: before this existed: every item and grade point, and for changes the year the feed keeps.
WINDOWS = (("all", "Any time", None), ("7d", "The last 7 days", 7), ("30d", "The last 30 days", 30),
           ("90d", "The last 90 days", 90), ("school_year", "This school year", None),
           ("custom", "Custom range", None))
WINDOW_KEYS = tuple(k for k, _, _ in WINDOWS)
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
        ("notes", "Notes", "number"), ("cases", "Where it stands", "text"),
    ),
    "grades": _cols(
        ("kid", "Kid", "text"), ("course", "Class", "text"), ("source", "Source", "text"),
        ("official", "Official", "text"), ("label", "Series", "text"), ("value", "Value", "number"), ("at", "Seen", "date"),
    ),
    "changes": _cols(
        ("at", "When", "date"), ("kid", "Kid", "text"), ("what", "What", "text"),
        ("item", "Item", "text"), ("course", "Class", "text"), ("source", "Source", "text"),
        ("detail", "Detail", "text"),
    ),
}

DEFAULT_COLUMNS = {"items": ["kid", "course", "name", "status", "due"],
                   "grades": ["kid", "course", "source", "official", "value", "at"],
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
    window: str = "all"
    date_from: str = ""              # ISO "YYYY-MM-DD", used only when window == "custom"
    date_to: str = ""

    def to_json(self) -> str:
        return json.dumps({
            "title": self.title, "source": self.source, "scope": list(self.scope),
            "columns": list(self.columns), "filters": [dict(f) for f in self.filters],
            "group_by": self.group_by, "sort": [dict(s) for s in self.sort], "chart": None,
            "orientation": self.orientation, "per_kid_sections": self.per_kid_sections,
            "window": self.window, "date_from": self.date_from, "date_to": self.date_to,
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
            window=str(raw.get("window", d.window)),
            date_from=str(raw.get("date_from", "")),
            date_to=str(raw.get("date_to", "")),
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


def _parse_plain_date(s: str) -> _date | None:
    """`date_from`/`date_to` as a plain date, or `None` when blank or unreadable -- callers
    treat `None` as "this custom range cannot be resolved", never as `datetime.min`."""
    from datetime import date as date_
    try:
        return date_.fromisoformat(s) if s else None
    except ValueError:
        return None


def validate(d: Definition) -> list[str]:
    """Every problem with the definition, one sentence each. Empty means it can be built."""
    problems: list[str] = []
    if d.window not in WINDOW_KEYS:
        problems.append(f"Unknown window {d.window!r}; choose one of {', '.join(WINDOW_KEYS)}.")
    elif d.window == "custom":
        fd, td = _parse_plain_date(d.date_from), _parse_plain_date(d.date_to)
        if fd is None or td is None:
            problems.append("A custom range needs both a start and an end date.")
        elif fd > td:
            problems.append("The custom range's start date must be on or before its end date.")
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
    window: str = ""                 # "The last 7 days" when the report is limited to one; "" for any time


def _num(v) -> str:
    return "" if v is None else (f"{v:g}" if isinstance(v, (int, float)) else str(v))


def window_start(d: Definition, now: datetime) -> datetime | None:
    """Where this report's rows begin, or None for "any time" (#94)."""
    if d.window == "custom":
        fd = _parse_plain_date(d.date_from)
        return datetime.combine(fd, datetime.min.time(), tzinfo=now.tzinfo) if fd else None
    if d.window == "school_year":
        return school_year_start(now)
    days = next((n for k, _, n in WINDOWS if k == d.window), None)
    return now - timedelta(days=days) if days else None


def _on_or_after(v: datetime | None, start: datetime | None) -> bool:
    if start is None:
        return True
    if v is None:
        return False                     # an undated row belongs to "any time" only
    a, b = reconcile.comparable(v, start)
    return a >= b


def _date(v, now: datetime | None = None, *, with_time: bool = False) -> str:
    """"9/8", with the year when it is not `now`'s (a report can reach back past New Year,
    and "6/2" alone does not say which June), and with the time for a change (#94)."""
    if v is None:
        return ""
    d = datetime.fromisoformat(v) if isinstance(v, str) else v
    if not isinstance(d, datetime):
        return str(d)
    if now is not None and d.tzinfo is not None and now.tzinfo is not None:
        d = d.astimezone(now.tzinfo)
    text = dates.md(d) + (f"/{d.year}" if now is not None and d.year != now.year else "")
    return f"{text} {dates.time12(d)}" if with_time else text


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


def _item_rows(conn, d, *, now, rules, nicknames, prefs=None, window=None) -> list[tuple[dict, dict]]:
    out = []
    start = window_start(d, now)
    for s in students_store.visible(conn):
        if d.scope and s["key"] not in d.scope:
            continue
        for v in items_store.list_items(conn, s, now=now, rules=rules, show="all", prefs=prefs, **(window or {})):
            if not _on_or_after(v.due, start):
                continue
            row = {
                "kid": nicknames.get(s["key"], s["key"]), "course": v.course_short, "name": v.name,
                "status": v.status, "due": _date(v.due, now), "points": _num(v.points), "kind": v.kind,
                "sources": " + ".join(v.sources), "flag": (v.flag or "").replace("_", " "),
                "open": _yes(v.overdue or v.upcoming), "actionable": _yes(v.actionable),
                "notes": _num(v.notes), "cases": verdicts.standing(v, "") if v.verdict.state in ("question", "decided", "waiting") else "",
            }
            out.append((row, _keys("items", row, {"due": v.due, "points": v.points, "notes": v.notes})))
    return out


def _grade_rows(conn, d, *, now, nicknames, prefs=None) -> list[tuple[dict, dict]]:
    out = []
    for s in students_store.visible(conn):
        if d.scope and s["key"] not in d.scope:
            continue
        for series in trends_store.grade_series(conn, student_id=s["id"], since=window_start(d, now), prefs=prefs):
            for at, value in series.points:
                row = {"kid": nicknames.get(s["key"], s["key"]), "course": series.course_short,
                       "source": series.source, "official": "yes" if series.official else "", "label": series.label,
                       "value": _num(value), "at": _date(at, now)}
                out.append((row, _keys("grades", row, {"at": at, "value": value})))
    return out


def _change_rows(conn, d, *, now, nicknames, prefs=None) -> tuple[list[tuple[dict, dict]], int]:
    """Rows, plus how many events the store's own cap left out of the feed entirely -- a count
    `build` folds into `Rendered.truncated` so a household past the cap is told, not just shown
    fewer rows than it has."""
    visible = students_store.visible(conn)
    keys = {s["key"] for s in visible}
    # "Any time" is the year the feed keeps; a chosen window starts where it says (#94).
    start = window_start(d, now) or now - timedelta(days=365)
    # A scoped report asks the store for each of its kids, so the cap applies to their events,
    # not to every kid's with the others dropped afterwards (#6).
    if d.scope:
        feeds = [changes_store.since(conn, since=start, limit=MAX_ROWS, prefs=prefs, student_id=s["id"])
                 for s in visible if s["key"] in d.scope]
        events = [e for f in feeds for e in f]
        dropped = sum(f.dropped for f in feeds)
    else:
        feed = changes_store.since(conn, since=start, limit=MAX_ROWS, prefs=prefs)
        events, dropped = list(feed), feed.dropped
    out = []
    for e in events:
        if e.student_key not in keys or (d.scope and e.student_key not in d.scope):
            continue
        row = {"at": _date(e.at, now, with_time=True), "kid": nicknames.get(e.student_key, e.student_key),
               "what": e.label, "item": e.item_name or "", "course": e.course_short or "",
               "source": e.source or "", "detail": e.detail}
        out.append((row, _keys("changes", row, {"at": e.at})))
    return out, dropped


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


def build(conn: sqlite3.Connection, d: Definition, *, now: datetime, rules, nicknames: dict, prefs=None,
          window: dict | None = None) -> Rendered:
    """Definition to rows. Raises `ViewError` when the definition does not validate."""
    problems = validate(d)
    if problems:
        raise ViewError(" ".join(problems))
    dropped = 0
    if d.source == "items":
        pairs = _item_rows(conn, d, now=now, rules=rules, nicknames=nicknames, prefs=prefs, window=window)
    elif d.source == "grades":
        pairs = _grade_rows(conn, d, now=now, nicknames=nicknames, prefs=prefs)
    else:
        pairs, dropped = _change_rows(conn, d, now=now, nicknames=nicknames, prefs=prefs)
    for f in d.filters:
        pairs = [p for p in pairs if _keep(p[0], f)]
    # Sort on the comparable value beside each row, never on the display string: "9/8" is after
    # "9/20" as text, and a report must not disagree with the Kid page about what comes first.
    for s in reversed(d.sort):                     # stable sorts, least significant first
        pairs.sort(key=lambda p, c=s["column"]: p[1][c], reverse=s["dir"] == "desc")
    truncated = max(0, len(pairs) - MAX_ROWS) + dropped  # rows cut here, plus rows the store
                                                          # never handed back because of its own cap
    kept = pairs[:MAX_ROWS]
    rows = [p[0] for p in kept]
    columns = [COLUMNS[d.source][c] for c in d.columns]
    slim = [{c.id: r.get(c.id, "") for c in columns} | ({d.group_by: r.get(d.group_by, "")} if d.group_by else {})
            for r in rows]
    groups: list[Group] = []
    if d.group_by:
        seen: dict[str, Group] = {}
        order: dict[str, object] = {}
        for r, (_, key) in zip(slim, kept):
            label = r.get(d.group_by, "")
            g = seen.get(label)
            if g is None:
                g = seen[label] = Group(label)
                order[label] = key[d.group_by]
                groups.append(g)
            g.rows.append({c.id: r[c.id] for c in columns})
        # Headings in the column's own order, the key the rows sort on: as text "9/8" came
        # after "9/20" (#6).
        groups.sort(key=lambda g: order[g.label])
    elif slim:
        groups = [Group("", [{c.id: r[c.id] for c in columns} for r in slim])]
    label = next((l for k, l, _ in WINDOWS if k == d.window), "") if d.window != "all" else ""
    return Rendered(d.title, columns, groups, truncated, label)
