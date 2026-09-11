# lakota-grades-mcp

A local MCP server that gives Claude clean JSON from **Canvas** (assignments, due dates, missing/late flags) and **Home Access Center** (official grades) for all three kids, so the weekly check-in reports can be built without driving Chrome.

Design goals:

- **Claude never sees a password.** Logins happen inside this server's process. Credentials come from the OS keyring at the moment they're typed and are not written anywhere.
- **Log in rarely.** One persistent Chromium profile holds the OneLogin, Canvas and HAC cookies; a login only happens when a site bounces us to a login page.
- **One pull, many tools.** A refresh writes a JSON snapshot; the tools read from it (cache TTL 3 h by default), so Thursday's report doesn't hit the sites more than once.
- **A bad pull never erases a good one.** If Canvas or HAC fails (or is skipped) on a refresh, that source's data is carried over from the last successful pull and `status()` reports it as `stale` with the time it was actually fetched.
- **No one has to be present.** Everything runs unattended, including the scheduled refresh and the weekday 2 PM printed sheet (section 6).

## 1. Install (Linux)

```bash
git clone https://github.com/steiner385/lakota-grades-mcp ~/lakota-grades-mcp
cd ~/lakota-grades-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium
```

Requires `secret-tool` (libsecret) and a running `gnome-keyring-daemon` for the default credential store.

## 2. Credentials

Credentials live in the **GNOME keyring** (freedesktop Secret Service):

```bash
lakota-grades set-credentials     # prompts; the password is never echoed
```

They are stored under `service=lakota-grades`, keys `username` and `password`, encrypted at rest under your login password and unlocked by PAM when you log into the desktop. The scheduled refresh can read them because systemd's user manager already exports `DBUS_SESSION_BUS_ADDRESS`.

Inspect or rotate:

```bash
secret-tool search service lakota-grades    # prints the secret too -- careful
lakota-grades set-credentials               # overwrite
```

> **Caveat.** The login keyring is unlocked at desktop login. If the machine boots and nobody signs into the GUI, the keyring stays locked and the refresh fails (loudly) rather than running. For a truly headless box, use a 1Password service account instead — see Alternative B below.

`Settings.credentials()` resolves, in order:

1. `LAKOTA_ONELOGIN_USERNAME` / `LAKOTA_ONELOGIN_PASSWORD` from the environment — a 1Password Environments mount, `op run --env-file=... -- lakota-grades ...`, or a plain `.env` you manage. **Alternative A.** Plaintext at rest if you use a plain file.
2. The GNOME keyring, as above. **Default.**
3. `op read` secret references, if `LAKOTA_OP_USERNAME_REF` / `LAKOTA_OP_PASSWORD_REF` are set. **Alternative B.** The 1Password desktop app prompts for approval on every login, so this suits interactive use, not the timer; for unattended runs set `OP_SERVICE_ACCOUNT_TOKEN` in the unit's environment, scoped to a vault holding only this item.

`op://` references reject punctuation such as `(` in an item title, and percent-encoding does not help — address such items by UUID: `op://Private/<item-uuid>/password`.

Nothing here ever prints or logs a credential.

## 3. First check

```bash
lakota-grades check    # headless: "Canvas: OK", "HAC: OK"
lakota-grades refresh  # pulls all three kids into ~/.lakota-grades/cache/snapshot.json
lakota-grades status   # cache age and last source health
```

Optional settings go in `~/.lakota-grades/.env` (see `env.example`); it is read automatically. Set `LAKOTA_ENV_FILE` only to point somewhere else, e.g. a 1Password Environments mount.

`check` and `refresh` log in by themselves. `lakota-grades login` opens a visible browser if you ever want to sign in by hand — useful for diagnosing a tenant whose OneLogin form has changed. With no terminal attached it watches the session and exits when both sites authenticate (`--wait-minutes`, default 15) instead of blocking on stdin.

If OneLogin ever changes its form, override `LAKOTA_ONELOGIN_USER_SELECTOR`, `LAKOTA_ONELOGIN_PASS_SELECTOR`, `LAKOTA_ONELOGIN_SUBMIT_SELECTOR`.

## 4. Point Claude Desktop at it

Add to `~/.config/Claude/claude_desktop_config.json` (see `claude_desktop_config.example.json`). Quit Claude Desktop first — it rewrites this file on exit.

```json
{
  "mcpServers": {
    "lakota-grades": {
      "command": "/home/tony/lakota-grades-mcp/.venv/bin/lakota-grades",
      "args": ["serve"],
      "env": { "LAKOTA_ENV_FILE": "/home/tony/.lakota-grades/.env" }
    }
  }
}
```

Claude Desktop rewrites this file on exit and can drop keys it does not recognise. If `lakota-grades` disappears from the server list, re-apply the block with Desktop closed. The `env` block is optional: `LAKOTA_ENV_FILE` already defaults to `~/.lakota-grades/.env`, so losing it no longer changes anything.

(For reference, the official 1Password MCP binary on Linux is `/opt/1Password/onepassword-mcp`, not `1password-mcp` — but this server does not need it.)

Restart Claude Desktop. The tools appear as `lakota-grades: grades`, `missing_work`, `upcoming`, `assignments`, `hac_classwork`, `list_students`, `status`, `refresh`.

## 5. Pre-fetch on a schedule

So the noon Thursday task finds a fresh snapshot and doesn't wait on logins:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/lakota-grades-refresh.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now lakota-grades-refresh.timer
systemctl --user list-timers | grep lakota
```

Thursday 11:30 and daily 06:00. The unit sets `TimeoutStartSec=900`: a full pull takes 1–3 minutes and systemd's 90 s default would kill it partway through.

## 6. The printed sheet (weekdays 2:00 PM)

`lakota-grades print-sheet` refreshes, builds one letter-portrait PDF with a section per kid, and sends it to CUPS as one duplex job. No Claude involved: Python, a systemd user timer, and `lp`.

```bash
lakota-grades print-sheet --dry-run          # build ~/.lakota-grades/sheets/<today>/sheet.pdf, print nothing
lakota-grades print-sheet --dry-run --kid Doug --date 2026-09-09
lakota-grades print-sheet                    # refresh, build, print, record
```

Each row: checkbox · **NEW** / *was …* (against the previous sheet) · due and assigned dates · course · assignment · points · where it was read (Canvas / HAC / Both) and how it is turned in (online / paper / in class) · status. Status words: `MISSING`, `ZERO`, `LATE` (turned in late, not graded), `PAPER — CHECK` (on-paper, no grade: ask), `HAC — NO GRADE`, `DUE TODAY`, `DUE TOMORROW`, `DUE <weekday>`. Overdue rows show the last day the teacher still takes the work and for what credit; rows past that day, or more than `--overdue-days` (14) old, are counted in a one-line "Not shown" instead. `--days` (14) is the forward window. A kid with nothing open still gets a section.

Files under `~/.lakota-grades/`, all created on first run and never overwritten:

| File | Purpose |
|---|---|
| `late-rules.toml` | The late-work register: per kid/class, how many days after the due date work is still accepted (`late_days`, or `until = "quarter_end"`) and for what `credit`. First matching rule wins. Seeded from the 2026-27 Canvas syllabi; edit as you learn more. |
| `no-print-days.txt` | One `YYYY-MM-DD` or `YYYY-MM-DD..YYYY-MM-DD` per line, optional note. Seeded with the district's 2026-27 no-school days. `--force` ignores it. |
| `sheets/YYYY-MM-DD/` | `sheet.pdf`, `rows.json` (what was on it; the next run diffs against it), `printed.txt` (the CUPS job id). A date with `printed.txt` is not printed again, even with `--force`; only an explicit `--reprint` does. |
| `print-sheet.log` | One line per run. The same line goes to stderr, so `journalctl --user -u lakota-print-sheet` has it too. |

If the refresh fails, the sheet still prints from the snapshot when its data is under 24 hours old, with a note in the footer; older than that, one log line and exit 1. A source carried forward from an earlier pull counts by its own fetch time.

Schedule it:

```bash
cp systemd/lakota-print-sheet.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now lakota-print-sheet.timer
loginctl enable-linger "$USER"      # so it runs when you are not logged in
systemctl --user list-timers | grep lakota
```

Two desktop shortcuts for running it by hand, whenever:

```bash
cp desktop/lakota-sheet-{pdf,print}.desktop ~/Desktop/ ~/.local/share/applications/
chmod +x ~/Desktop/lakota-sheet-*.desktop
gio set ~/Desktop/lakota-sheet-pdf.desktop metadata::trusted true
gio set ~/Desktop/lakota-sheet-print.desktop metadata::trusted true
```

**Kids' Sheet (PDF only)** refreshes, builds today's sheet, and opens it in Evince without printing. **Kids' Sheet (Send to Printer)** refreshes, builds, and prints, even on a no-school day and even if the 2 PM run already printed (`--force --reprint`). Both open a terminal window so the 1–3 minute refresh shows progress, and both go through `scripts/lakota-sheet-desktop.sh`. A manual print before 2 PM records the day as printed, so the timer's run that afternoon skips.

`OnCalendar=Mon..Fri 14:00 America/New_York` with `Persistent=true`: a run missed while the machine slept fires on wake, and the command refuses to print before 2 PM, so a catch-up the next morning logs "outside print window" and exits instead of printing yesterday's sheet. The printer is set explicitly in the unit (`LAKOTA_PRINTER`; `--printer` on the command line), never the CUPS default.

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

## Notes and known quirks (Lakota, Sept 2026)

- Canvas API token generation is disabled for parent accounts, which is why this uses the browser session's cookies against the REST API instead.
- `/api/v1/users/<kid>/courses` returns 403 for observers; enrollments with `include[]=observed_users` is the working route.
- `/api/v1/courses/<id>/users` **also** returns 403 for observers, so teacher/TA contacts fall back to the course object's `include[]=teachers` (names only, no emails). A per-course failure is recorded in the snapshot rather than aborting the whole Canvas pull.
- **HAC has no login form.** `/HomeAccess/Account/LogOn` is now just a notice pointing at the OneLogin portal, so HAC can only be entered by launching its portal app tile, which performs the SSO hand-off. The tile is found by name (`LAKOTA_HAC_APP_PATTERN`); pin it with `LAKOTA_HAC_ONELOGIN_APP_URL` if discovery ever breaks.
- The HAC student switcher has no "Change" button: the banner element showing the current student (`.sg-banner-chooser`) opens `#StudentPicker`, a POST form that only commits via its **Submit** button.
- HAC Classwork renders inside an iframe named `sg-legacy-iframe`; class blocks are `.AssignmentClass`, rows `tr.sg-asp-table-data-row`. The frame's document renders after `domcontentloaded`, so the frame must be polled, not scanned once.
- Algebra II's Canvas grade is hidden by the teacher; Band and parts of Latin/Biology are graded only in HAC. HAC is the gradebook of record.
- Honors English 9 closes late work one week after the due date.
- The browser reports an ordinary Chrome UA, not Chromium's default `HeadlessChrome/<v>`. ParentSquare's sniffer does not recognise that token, falls through to the trailing `Safari/537.36` and serves `/browser_unsupported?browser=Safari&version=`. The version is read from the Chromium binary so it tracks Playwright upgrades; override with `LAKOTA_USER_AGENT`.
- Other apps on the OneLogin portal, reachable with the same `onelogin_app_url()` helper: ParentSquare/StudentSquare (posts, messages, alerts — carries things no gradebook has, e.g. "Science quiz tomorrow"), PaySchools (cafeteria balances), FinalForms Parent, SchooLinks.
- `mcp` is pinned `<3`: version 2.0 renamed `FastMCP` to `MCPServer`. The server imports either.

## Security notes

- The browser profile in `~/.lakota-grades/browser-profile` contains session cookies. Treat it like a password: the tree is created `0700`.
- The snapshot JSON contains the kids' grades; it is written `0600` and atomically.
- Nothing here ever prints or logs a credential. `Settings.credentials()` is the only reader.

## License

MIT — see [LICENSE](LICENSE).
