# fridgesheet

The sheet on the fridge: a parent's daily list of open school work, pulled from **Canvas** (assignments, due dates, missing/late flags) and **Home Access Center** (official grades) for every kid in the house, decided once by [one definition of done](docs/outcomes.md), and printed or shown on a browser app. It started for one district (the Windows build is still called "Fridge Sheet") and works for any district that runs those two systems behind OneLogin. It also serves the same data to Claude as a local MCP server, so weekly check-in reports can be built without driving Chrome.

The Python package and the Linux install path still carry the old name, `fridgesheet` / `~/fridgesheet`; those rename in a later release with a migration for existing installs.

Design goals:

- **Claude never sees a password.** Logins happen inside this server's process. Credentials come from the OS keyring at the moment they're typed and are not written anywhere.
- **Log in rarely.** One persistent Chromium profile holds the OneLogin, Canvas and HAC cookies; a login only happens when a site bounces us to a login page.
- **One pull, many tools.** A refresh writes a JSON snapshot; the tools read from it (cache TTL 3 h by default), so Thursday's report doesn't hit the sites more than once.
- **A bad pull never erases a good one.** If Canvas or HAC fails (or is skipped) on a refresh, that source's data is carried over from the last successful pull and `status()` reports it as `stale` with the time it was actually fetched.
- **No one has to be present.** Everything runs unattended, including the scheduled refresh and the weekday 2 PM printed sheet (section 6).
- **Other parents can install it.** A Windows build ("Fridge Sheet") with a browser app and a per-user installer: see [docs/windows.md](docs/windows.md) and "Releasing" below.

## 1. Install (Linux)

```bash
git clone https://github.com/steiner385/fridgesheet ~/fridgesheet
cd ~/fridgesheet
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium
```

Requires `secret-tool` (libsecret) and a running `gnome-keyring-daemon` for the default credential store.

Python 3.11 or newer.

## 2. Credentials

Credentials live in the **OS credential store** (GNOME keyring on Linux, Credential Manager on Windows):

```bash
fridgesheet set-credentials     # prompts; the password is never echoed
```

They are stored under `service=fridgesheet`, keys `username` and `password`, encrypted at rest under your login password and unlocked by PAM when you log into the desktop. The scheduled refresh can read them because systemd's user manager already exports `DBUS_SESSION_BUS_ADDRESS`.

Inspect or rotate:

```bash
secret-tool search service fridgesheet    # prints the secret too -- careful
fridgesheet set-credentials               # overwrite
```

> **Caveat.** The login keyring is unlocked at desktop login. If the machine boots and nobody signs into the GUI, the keyring stays locked and the refresh fails (loudly) rather than running. For a truly headless box, use a 1Password service account instead — see Alternative B below.

`Settings.credentials()` resolves, in order:

1. `FRIDGESHEET_ONELOGIN_USERNAME` / `FRIDGESHEET_ONELOGIN_PASSWORD` from the environment — a 1Password Environments mount, `op run --env-file=... -- fridgesheet ...`, or a plain `.env` you manage. **Alternative A.** Plaintext at rest if you use a plain file.
2. The OS credential store, as above. **Default.**
3. `op read` secret references, if `FRIDGESHEET_OP_USERNAME_REF` / `FRIDGESHEET_OP_PASSWORD_REF` are set. **Alternative B.** The 1Password desktop app prompts for approval on every login, so this suits interactive use, not the timer; for unattended runs set `OP_SERVICE_ACCOUNT_TOKEN` in the unit's environment, scoped to a vault holding only this item.

`op://` references reject punctuation such as `(` in an item title, and percent-encoding does not help — address such items by UUID: `op://Private/<item-uuid>/password`.

Nothing here ever prints or logs a credential.

## 3. First check

```bash
fridgesheet check    # headless: "Canvas: OK", "HAC: OK"
fridgesheet refresh  # pulls all three kids into ~/.fridgesheet/cache/snapshot.json
fridgesheet status   # cache age and last source health
```

Optional settings go in `~/.fridgesheet/.env` (see `env.example`); it is read automatically. Set `FRIDGESHEET_ENV_FILE` only to point somewhere else, e.g. a 1Password Environments mount.

`check` and `refresh` log in by themselves. `fridgesheet login` opens a visible browser if you ever want to sign in by hand — useful for diagnosing a tenant whose OneLogin form has changed. With no terminal attached it watches the session and exits when both sites authenticate (`--wait-minutes`, default 15) instead of blocking on stdin.

If OneLogin ever changes its form, override `FRIDGESHEET_ONELOGIN_USER_SELECTOR`, `FRIDGESHEET_ONELOGIN_PASS_SELECTOR`, `FRIDGESHEET_ONELOGIN_SUBMIT_SELECTOR`.

## 4. Point Claude Desktop at it

Add to `~/.config/Claude/claude_desktop_config.json` (see `claude_desktop_config.example.json`). Quit Claude Desktop first — it rewrites this file on exit.

```json
{
  "mcpServers": {
    "fridgesheet": {
      "command": "/home/<you>/fridgesheet/.venv/bin/fridgesheet",
      "args": ["serve"],
      "env": { "FRIDGESHEET_ENV_FILE": "/home/<you>/.fridgesheet/.env" }
    }
  }
}
```

Claude Desktop rewrites this file on exit and can drop keys it does not recognise. If `fridgesheet` disappears from the server list, re-apply the block with Desktop closed. The `env` block is optional: `FRIDGESHEET_ENV_FILE` already defaults to `~/.fridgesheet/.env`, so losing it no longer changes anything.

(For reference, the official 1Password MCP binary on Linux is `/opt/1Password/onepassword-mcp`, not `1password-mcp` — but this server does not need it.)

Restart Claude Desktop. The tools appear as `fridgesheet: grades`, `missing_work`, `upcoming`, `assignments`, `hac_classwork`, `list_students`, `status`, `refresh`.

## 5. Pre-fetch on a schedule

So the noon Thursday task finds a fresh snapshot and doesn't wait on logins:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/fridgesheet-refresh.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now fridgesheet-refresh.timer
systemctl --user list-timers | grep fridgesheet
```

Thursday 11:30 and daily 06:00. The unit sets `TimeoutStartSec=900`: a full pull takes 1–3 minutes and systemd's 90 s default would kill it partway through.

This is unrelated to report scheduling below — it only keeps the snapshot warm, and it is not something the app will ever touch (`fridgesheet-refresh.{service,timer}` are refused by name by every `schedule` command, the same as the hand-written print timer in the next section). A report's own printing schedule, including the weekday sheet's, is what the app now writes itself.

## 6. Printing a report on a schedule

`fridgesheet run <key>` refreshes, builds one report's PDF, prints it, and records the run — it's what a schedule executes, however it was installed. A report key is `open-work` (the built-in kids' sheet: one letter-portrait PDF with a section per kid) or `view:<id>` (a report built on the Reports page). `fridgesheet reports` lists every key with its enabled state, schedule and whether it's PDF-only:

```bash
fridgesheet reports
# open-work    Open Work Sheet      disabled  14:00 Mon,Tue,Wed,Thu,Fri
```

`fridgesheet print-sheet` still exists — it's `run open-work` under its original name, sending the PDF to CUPS as one duplex job, except it always applies its own `--days`/`--overdue-days` defaults (14) rather than `config.toml`'s. The household's live hand-written timer still calls it by that name; a schedule installed since (from the CLI or the Schedules page) calls `run <key>` instead.

```bash
fridgesheet run open-work --dry-run                    # build sheets/<today>/sheet.pdf, print nothing
fridgesheet run open-work --dry-run --kid Al --date 2026-09-09
fridgesheet print-sheet --dry-run                       # the same sheet, the original command
```

The printer is `--printer` if given (its default, on the CLI, comes from `FRIDGESHEET_PRINTER` — how the hand-written unit sets one), else the report's own printer (`[reports.<key>].printer`, settable from the Schedules page), else `[print].printer` in `config.toml`, else the CUPS default.

Each row of the open-work sheet: checkbox · **NEW** / *was …* (against the previous sheet) · due and assigned dates · course · assignment · points · where it was read (Canvas / HAC / Both) and how it is turned in (online / paper / in class) · status. Status words: `MISSING`, `ZERO`, `LATE` (turned in late, not graded), `PAPER — CHECK` (on-paper, no grade: ask), `HAC — NO GRADE`, `DUE TODAY`, `DUE TOMORROW`, `DUE <weekday>`. Overdue rows show the last day the teacher still takes the work and for what credit; rows past that day, or more than `--overdue-days` (14) old, are counted in a one-line "Not shown" instead. `--days` (14) is the forward window. A kid with nothing open still gets a section.

Files under `~/.fridgesheet/`, all created on first run and never overwritten:

| File | Purpose |
|---|---|
| `late-rules.toml` | The late-work register: per kid/class, how many days after the due date work is still accepted (`late_days`, or `until = "quarter_end"`) and for what `credit`. First matching rule wins. Seeded from the 2026-27 Canvas syllabi; edit as you learn more. |
| `no-print-days.txt` | One `YYYY-MM-DD` or `YYYY-MM-DD..YYYY-MM-DD` per line, optional note. Seeded with the district's 2026-27 no-school days. `--force` ignores it. |
| `sheets/YYYY-MM-DD/` | `sheet.pdf`, `rows.json` (what was on it; the next run diffs against it), `printed.txt` (the CUPS job id). A date with `printed.txt` is not printed again, even with `--force`; only an explicit `--reprint` does. |
| `print-sheet.log` | One line per run with its outcome, preceded by an `INFO ingested …` line on runs that refreshed. The same lines go to stderr, so `journalctl --user -u fridgesheet-print-sheet` has them too. |
| `fridgesheet.db` | The app's database: every refresh as a change log, plus notes, flags and run history. SQLite in WAL mode, so `fridgesheet.db-wal` and `fridgesheet.db-shm` sit beside it; copy all three or none. Deleting it costs the history, not the sheets. |

Set `FRIDGESHEET_SHEETS_ARCHIVE` in `~/.fridgesheet/.env` to a folder people actually look in, such as a Google Drive mount, and every PDF is also saved there as `<school year>/<date> Open Work.pdf` (for example `2026-27/2026-09-11 Open Work.pdf`). The log line then ends with `saved=<path>`. If that folder is unreachable the run logs a warning and still prints; the local copy under `sheets/` is always written.

### Settings file

Most settings can live in `~/.fridgesheet/config.toml` instead of `.env`; the environment still wins when both set the same thing. `fridgesheet set-credentials` records the username there (the password goes in the OS credential store).

```toml
[account]
username = "parent@example.com"

[print]
printer = ""                          # blank = system default (fridgesheet printers)
archive = ""                          # optional folder for a second copy of every PDF

[kids]
nicknames = { Alex = "Al" }      # snapshot first name -> name printed on the sheet

[reports.open-work]
enabled = true
time = "14:00"
days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
days_ahead = 14
overdue_days = 14
```

`fridgesheet run open-work` is the general form of `print-sheet` (same flags); `print-sheet` always passes its own `--days`/`--overdue-days` defaults (14), so `days_ahead`/`overdue_days` in `config.toml` apply to `run open-work` but not to the alias. `fridgesheet reports` lists report types and their schedules; `fridgesheet schedule show <key>` prints the next run and who manages it. `fridgesheet schedule install <key>` writes the schedule itself — the Task Scheduler task on Windows, a systemd user timer pair on Linux (below).

**Upgrading from 0.1:** the built-in `Alex=Al` nickname is gone. Add `FRIDGESHEET_NICKNAMES=Alex=Al` to `.env` or the `[kids]` table above, or the sheet prints the full first name. The built-in `Brother_MFC_J4335DW` printer default is also gone; the systemd unit still sets `FRIDGESHEET_PRINTER`, but the desktop shortcuts run without it, so add `FRIDGESHEET_PRINTER=<your CUPS printer name>` to `~/.fridgesheet/.env` (or `[print] printer` in `config.toml`) or those shortcuts print to the CUPS default.

If the refresh fails, the sheet still prints from the snapshot when its data is under 24 hours old, with a note in the footer; older than that, one log line and exit 1. A source carried forward from an earlier pull counts by its own fetch time.

Schedule it — from the CLI, or the Schedules page in the browser app (below):

```bash
fridgesheet schedule install open-work    # writes fridgesheet-open-work.{service,timer}, enables the timer
fridgesheet schedule show open-work       # next run, and who manages it
fridgesheet schedule remove open-work     # disables and deletes the pair
fridgesheet schedule remove --all         # every report's schedule at once -- what the Windows uninstaller runs
loginctl enable-linger "$USER"              # so the timer fires when you are not logged in
```

`install` writes `~/.config/systemd/user/fridgesheet-<key>.{service,timer}` — the timer's days and time come from `[reports.<key>]` in `config.toml`, or the Schedules page — and runs `systemctl --user enable --now` on the timer itself; no `daemon-reload` or `cp` to remember. The printer is not baked into the unit; it's read at run time, per the precedence above. Every unit the app writes starts with a `# Written by Fridge Sheet` marker line, and `install`/`remove` refuse outright, before touching anything, for a unit that lacks it: `fridgesheet-print-sheet.{service,timer}` above and `fridgesheet-refresh.{service,timer}` from section 5 are exactly such units, and stay safe under hand editing no matter what `schedule` commands you run. For `open-work` specifically the app also knows the hand-written print timer by name: if it's enabled, `schedule install open-work` and `schedule remove open-work` both refuse rather than risk printing the sheet twice or silently leaving it running.

Two desktop shortcuts for running it by hand, whenever:

```bash
cp desktop/fridgesheet-{pdf,print}.desktop ~/Desktop/ ~/.local/share/applications/
chmod +x ~/Desktop/fridgesheet-*.desktop
gio set ~/Desktop/fridgesheet-pdf.desktop metadata::trusted true
gio set ~/Desktop/fridgesheet-print.desktop metadata::trusted true
```

**Kids' Sheet (PDF only)** refreshes, builds today's sheet, and opens it in Evince without printing. **Kids' Sheet (Send to Printer)** refreshes, builds, and prints, even on a no-school day and even if the 2 PM run already printed (`--force --reprint`). Both open a terminal window so the 1–3 minute refresh shows progress, and both go through `scripts/fridgesheet-desktop.sh`. A manual print before 2 PM records the day as printed, so the timer's run that afternoon skips.

Both the hand-written timer and an app-installed one fire from an `OnCalendar=` line with `Persistent=true` — the hand-written one as a day range (`Mon..Fri 14:00 America/New_York`), the app as a comma list instead (`Mon,Tue,Wed,Thu,Fri 14:00 America/New_York`), which is what lets it schedule a set with gaps. Either way, a run missed while the machine slept fires on wake, and `run`/`print-sheet` themselves refuse to print before their configured time, so a catch-up the next morning logs "outside print window" and exits instead of printing yesterday's sheet.

### The browser app

`fridgesheet web` runs a small local web server (127.0.0.1:8433 by default) and opens it in your browser. **Dashboard** shows each kid's open work and the last refresh, with **Refresh now**, **Preview** and **Print now** buttons whose progress streams into the page as the job runs. Each kid also has their own page: the item list with filters, an expandable row, and a course view. **Reconcile** shows what the sources and your flags don't agree on, per kid. **Reports** lists the built-in and saved report types and holds the builder — pick a source, columns, filters, sort and grouping, preview it live, export CSV/JSON. **Schedules** is one row per report, built-in or saved: enable it, set its days, time, printer and whether it's PDF-only, and saving writes both `config.toml` and the OS timer or task — the same `schedule install`/`remove` section 6 describes. A report already scheduled by a unit this app did not write shows up here too, but disabled, with the `systemctl` command to turn it off yourself first. **Changes** is a feed of everything that moved since a chosen moment. **Trends** plots grade lines per class and weekly missing/late/on-time counts, and lists what has sat open longest. **Runs** lists run history — what ran, how it went, the PDF, print it again. **Settings** edits the same values as `config.toml` (plus a **Test login** button that records a passing login in `~/.fridgesheet/login-ok.txt`, and in-browser editors for `late-rules.toml` and `no-print-days.txt`). **Diagnostics** runs the doctor and shows the report.

Once a day the app asks GitHub whether a newer release exists and says so on Settings and in the header — the one thing it talks to besides the school systems; it sends nothing, and the Settings checkbox turns it off.

Every count, filter and colour that says whether an assignment was done comes from one definition, written out in [`docs/outcomes.md`](docs/outcomes.md): why Canvas's "missing" undercounts, why a teacher's 0 is *not done*, why paper work that was graded is not, and which of the two sources can answer which question.

`fridgesheet service install` keeps the server running in the background — a systemd user unit on Linux, a logon task on Windows — so the shortcut only has to open the page. On Windows this is the "Fridge Sheet" app: the exe with no arguments starts the server if it is not already up and opens the browser at it. The server writes `app.log` in the same folder.

## Tools

| Tool | Returns |
|---|---|
| `list_students()` | Kids on the account, Canvas IDs, which sources have data |
| `grades(student)` | Per class: HAC marking-period average (official), HAC last-updated, category subtotals, Canvas current/final, teacher/TA contacts |
| `missing_work(student)` | Overdue work the kid can still act on: missing, zero, ungraded-late, past-due-unsubmitted (Canvas; paper items as PAPER — CHECK) + blank-score past-due rows (HAC), deduped; each with `late_until` and `credit` from `late-rules.toml`; assessments first |
| `upcoming(student, days=14)` | Unsubmitted items due in the window, Eastern time, with DUE TODAY / DUE TOMORROW / DUE <weekday> statuses |
| `assignments(student, course=None)` | Full Canvas assignment list with flags |
| `hac_classwork(student, course=None)` | Raw HAC rows and category subtotals |
| `status()` / `refresh(kids, hac, canvas)` | Snapshot age, source health, and `stale` (sources served from an older pull, with that pull's time) / pull now |

All dates are `America/New_York` ISO strings (Canvas `due_at` is UTC and is converted).

A refresh on which a source fails, or is skipped with `hac=false` / `canvas=false`, keeps that source's data from the previous snapshot rather than writing it out empty; `sources` still shows the error, and `stale` names the source, the reason, and when its data was last actually fetched. Kids left out with `kids=[...]` are likewise kept from the previous snapshot. There is nothing to keep on the very first pull, so a source that fails then is simply absent.

## Tests

```bash
pip install -e '.[dev]'
pytest
```

CI runs the suite on Ubuntu and Windows.

## Notes and known quirks (Lakota, Sept 2026)

- Canvas API token generation is disabled for parent accounts, which is why this uses the browser session's cookies against the REST API instead.
- `/api/v1/users/<kid>/courses` returns 403 for observers; enrollments with `include[]=observed_users` is the working route.
- `/api/v1/courses/<id>/users` **also** returns 403 for observers, so teacher/TA contacts fall back to the course object's `include[]=teachers` (names only, no emails). A per-course failure is recorded in the snapshot rather than aborting the whole Canvas pull.
- **HAC has no login form.** `/HomeAccess/Account/LogOn` is now just a notice pointing at the OneLogin portal, so HAC can only be entered by launching its portal app tile, which performs the SSO hand-off. The tile is found by name (`FRIDGESHEET_HAC_APP_PATTERN`); pin it with `FRIDGESHEET_HAC_ONELOGIN_APP_URL` if discovery ever breaks.
- The HAC student switcher has no "Change" button: the banner element showing the current student (`.sg-banner-chooser`) opens `#StudentPicker`, a POST form that only commits via its **Submit** button.
- HAC Classwork renders inside an iframe named `sg-legacy-iframe`; class blocks are `.AssignmentClass`, rows `tr.sg-asp-table-data-row`. The frame's document renders after `domcontentloaded`, so the frame must be polled, not scanned once.
- Algebra II's Canvas grade is hidden by the teacher; Band and parts of Latin/Biology are graded only in HAC. HAC is the gradebook of record.
- Honors English 9 closes late work one week after the due date.
- The browser reports an ordinary Chrome UA, not Chromium's default `HeadlessChrome/<v>`. ParentSquare's sniffer does not recognise that token, falls through to the trailing `Safari/537.36` and serves `/browser_unsupported?browser=Safari&version=`. The version is read from the Chromium binary so it tracks Playwright upgrades; override with `FRIDGESHEET_USER_AGENT`.
- Other apps on the OneLogin portal, reachable with the same `onelogin_app_url()` helper: ParentSquare/StudentSquare (posts, messages, alerts — carries things no gradebook has, e.g. "Science quiz tomorrow"), PaySchools (cafeteria balances), FinalForms Parent, SchooLinks.
- `mcp` is pinned `<3`: version 2.0 renamed `FastMCP` to `MCPServer`. The server imports either.

## Security notes

- The browser profile in `~/.fridgesheet/browser-profile` contains session cookies. Treat it like a password: the tree is created `0700`.
- The snapshot JSON contains the kids' grades; it is written `0600` and atomically.
- Nothing here ever prints or logs a credential. `Settings.credentials()` is the only reader.

## Releasing the Windows installer

The Windows app ("Fridge Sheet") is built by `.github/workflows/release.yml` on a Windows runner, from `packaging/windows/build.ps1`, which bundles Chromium and a pinned SumatraPDF, smoke-tests the built exe, and wraps it with Inno Setup.

1. Bump `version` in `pyproject.toml` and merge to `main`.
2. Optionally, after step 1 has merged (GitHub only offers the Run workflow button for workflows on the default branch), run the workflow by hand first (Actions → release → Run workflow) and download the `FridgeSheet-Setup` artifact to try it.
3. Tag and push: `git tag v0.4.1 && git push origin v0.4.1`. The job refuses a tag that does not match `pyproject.toml`, and on success attaches `FridgeSheet-Setup-0.4.1.exe` to a GitHub release. Installed copies notice the new release within a day (Settings shows *Fridge Sheet 0.4.1 is available* with a download link; the header carries a badge) and the installer upgrades over the running app.

Before that tag, work through [docs/release-checklist.md](docs/release-checklist.md) by hand on a real Windows PC with a real printer and a real phone — it covers what CI cannot.

The page to send along with it is [docs/windows.md](docs/windows.md).

## License

MIT — see [LICENSE](LICENSE).
