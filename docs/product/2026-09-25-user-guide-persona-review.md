# User-guide persona review — 2026-09-25

After writing [docs/user-guide.md](../user-guide.md), four persona reviewers read it against the
templates and code on `main` (f8d975f) and reported where the product, not only the doc, could be
simpler. Defects found along the way are filed as issues #120–#154; this page is the usability
side, ranked by how much each change would remove.

| Persona | Who | Where they lose time |
|---|---|---|
| **Dana** | Non-technical Windows parent, three kids (4th, 7th, 10th), 20 minutes to get a 3 pm sheet printing | First-run setup |
| **Marcus & Priya** | Working parent, 5-minute nightly phone check and Sunday check-ins; co-parent who uses it occasionally | Vocabulary and navigation |
| **Maya (9, ADHD) & Leo (14)** | Children beside a parent at check-in, and reading the fridge | Check-in wording and feedback |
| **Sam** | Software-literate parent, another district, Central time, headless Linux server, Claude Desktop | District, time zone, headless setup |

## 1. Setup: make the working path the only path

The single most likely outcome for a new household is *no sheet on day 2*.

1. **A report schedule should imply a refresh schedule** (#120). Either turning on a report
   schedule turns on *Refresh the data* with its defaults, or a scheduled run refreshes when the
   data is older than a few hours. Until then, Schedules should show a warning banner when a
   report is scheduled and refresh is off. Today the page says the opposite of what happens.
2. **Test login should save first.** It tests the *saved* credentials; a parent who types, then
   clicks Test login, tests the old ones. Make Test login submit the form, or disable it while
   the form is dirty.
3. **Put Refresh now where the empty page is** (#153). The first screen a new user sees tells them
   to run a terminal command.
4. **Reading level on Settings.** `[kids] grades` is the only per-child setting a parent will
   want that requires editing `config.toml`. A "Kids" card with one grade dropdown per child
   (populated from the last refresh) removes the only file-editing step from Windows setup.
5. **"Refresh data first" defaults.** Tick it by default when the last refresh is more than an
   hour old; untick and say "data is fresh" otherwise. The first Print now is otherwise from
   whatever data happened to be there.
6. **Time inputs** — show "3:00 PM" next to a 24-hour value, or use a 12-hour picker.
7. **Don't seed another district with Lakota's calendar.** No-print days and quarter ends start
   with Lakota's 2026-27 dates; a district setting (or an empty seed with "fill these in") would
   stop silent wrong skips.

## 2. One vocabulary

Marcus's and Priya's recurring cost is translating between screens. The guide now needs a
"same thing, different words" table (§4a) — the product should not.

1. **One label table for answers** (#129). *Let it go* appears as `ignore`, *Ignored*, *let go*,
   *let it go*; the record block reads differently on check-in and on Assignments.
2. **Open vs. Open work vs. still fixable.** Three names for overlapping sets. Candidates:
   rename the Assignments filter *Open* to *Needs doing* (still fixable + coming due) so *Open
   work* is only the page, or rename the page *Tonight's list*.
3. **Say "handled" once.** Four answers hide an item identically (It's done, Excused, Let it go,
   Too late to submit). Consider whether four are needed on the first menu; *Excused* and *Too
   late* could sit under a "More reasons" fold.

## 3. Fewer dead ends

1. The ⚠ banner's **Refresh now** only navigates to Today; make it start the refresh (job card
   inline), the same as the button.
2. After **Refresh now** finishes, re-render the counts (htmx swap of the cards) instead of
   asking for a reload.
3. **Plan tab edits** should return to Plan (#128); **Close** on a detail opened from a question
   card should restore the card (#126).
4. **Let all N go** should show the items it will touch and offer a bulk undo (#124).
5. **Agreements** (finished check-ins) can't be corrected; a same-day "edit summary" would cover
   typos without breaking the snapshot's purpose.

## 4. For the children

(Prior audit F1–F12 not repeated.)

1. **Tier the School-record block** (`_planning_evidence.html`): route "marked missing", "no
   submission recorded", "no grade posted" through `phrasing.PHRASES` like the sheet's status
   words. It is the harshest sentence on Maya's screen and the only un-tiered one.
2. **"Family account (your side of the story)" → "In your own words".** The current label frames
   the child's account as testimony against the school.
3. **Acknowledge a completed step.** Completion disappears into a *Completed steps* fold. One
   visible "✓ step — owner, date" line is the plan's equivalent of *Done so far*.
4. **Step form "State"** → "Where is this step?".
5. **Budget overrun** in the warn colour on the early tier reads as a red mark; soften the colour
   and say "That's more than we agreed for today."
6. **Early-tier check-in intro** — "Where is the school record wrong?" positions a 9-year-old as
   adversary; lead with "What went well?".
7. Reconfirm that older-tier kids should see red `MISSING`/`ZERO` capitals on a shared fridge.

## 5. Headless and other districts

1. **Time zone setting** defaulting to the host's (#122) — the biggest correctness gap outside
   Eastern time.
2. **A District card** on Settings for the three addresses and the HAC tile pattern.
3. **Complete terminal setup** (#154): `check` writes the Test-login stamp;
   `schedule install data-refresh`; Save doesn't require a password the environment already
   supplies; a `fridgesheet setup` that does credentials → check → service → both schedules.
4. **A credentials option for servers** that isn't "plain-text `.env`": document the 1Password
   service-account path clearly (README, env.example and config.py disagree today) and have
   Diagnostics say "keyring locked; nobody signed in".
5. **MCP refresh through `refresh --record`** with the run lock, so Claude, the web app and the
   printer agree (#151).

## Method note

Two of the four reviewers read templates from the main checkout, which was on an older feature
branch, and reported label mismatches ("Reconcile", "All work", "N actionable") that do not
exist on `main`. Those findings were checked against the worktree and dropped.
