---
version: 1
slug: "fridgesheet-web-templates-base-html"
primary_target: "fridgesheet/web/templates/base.html"
related_targets: ["fridgesheet/web/templates/_header.html","fridgesheet/web/templates/_page_head.html","fridgesheet/web/templates/_child_nav.html"]
---

# Surface brief: the shell (rail, status line, page head, child tabs)

Scope: `base.html` with `_header.html`, `_page_head.html` and `_child_nav.html`: the frame around
every page, on every width, in family mode and kid mode; Operate mode. Audience: everyone who
opens the app; the child on their own device sees the kid shell. Job: name where you are, get to
the next page in one tap, and say when the data was read. Proof: the current page pulled forward
as a tab; the status line's refresh time and source states. Constraints (maintainer,
2026-09-30): the planner's index tabs, not a cover band and not a restyle; in kid mode Plan and
Assignments first, Check-in, Trends and Changes behind a More fold (parity: folded, never
removed); every link and question-count id stays in the page; the status bar's words and classes
stay (tests read them); 44px for tabs and the fold summaries. The world is settled (DESIGN.md);
this brief records composition only. Unresolved: whether the chooser (`/who`) joins the world;
whether the class page and Open work follow.

## Direction contract

THESIS: The shell is the planner's edge: the pages are printed index tabs down the left, the
current one pulled forward onto the page, and the status is the page's ruled "as of" line in
pencil. It refuses the admin sidebar with rounded hover pills and the app bar.

OWN-WORLD: The rail sits on the planner white with the day-box rule as its edge; each page is a
tab in the tier's body size, no radius beyond the planner's 2px, no fill at rest; the current tab
is paper white with the box rule on three sides and open toward the page, so it reads as the tab
in front. Group names (Work, Time, App) are the day-label type: small caps, tracked, pencil grey.
The status line is pencil-grey small type on a hairline. The child tabs under a page title are
the same index tabs turned sideways, the current one standing on the ruled header line. On a
phone the shell is one ruled row: the mark, the wordmark, and a Menu fold that opens the tabs as
a wrapped list; the status line stays beneath as one pencil line. Kid mode's row shows Plan and
Assignments as tabs beside the mark, More folded, "Not Sam?" at the end.

STORY: A parent glances left and sees where she is by the tab that stands out; she taps the next
page and the tab moves. On a phone the page begins under one thin row. A child on her own device
sees her two pages and nothing that is not hers.

FIRST VIEWPORT: At 1440: the rail column (220px) on planner white, the wordmark at the top, then
TODAY, ALEX 1, SAM as tabs in body type, then WORK · Open work · Questions · Reports · Schedules,
TIME · Changes · Trends, APP · Runs · Settings · Diagnostics · Switch to a kid's view, with the
current tab pulled forward in paper white. In the page column, the status line in pencil under a
hairline, then the page head as now. At 390: one row, the mark and "Fridge Sheet" at the left,
"Menu" at the right (44px); the status line under it; the page title next. Kid mode at 390: the
mark, Plan, Assignments, More, Not Sam?.

FORM: The planner's index tabs, chosen by the maintainer from three shell forms; an extension of
the settled world, no roll. Signature interaction: the tab moves; on a phone the menu folds and
unfolds in place; nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
