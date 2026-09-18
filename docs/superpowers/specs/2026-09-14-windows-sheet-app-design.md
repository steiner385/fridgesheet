# Lakota Sheet for Windows: design

Date: 2026-09-14. Status: approved in discussion, awaiting review of this document.

## 1. Goal

Package the printed open-work sheet so another Lakota parent can install it on a
Windows PC, enter their own OneLogin account, pick their printer, and have the sheet
print every weekday afternoon without touching a terminal. The MCP server that feeds
Claude Desktop is **not** part of the package. New report types must be addable later
without restructuring.

Tony's Linux install (systemd timers, GNOME keyring, CUPS, desktop shortcuts) keeps
working from the same code with one documented migration step (section 10).

## 2. What is specific today, and what happens to it

| Today | Kind | Disposition |
|---|---|---|
| Canvas, HAC, OneLogin hosts; time zone; no-school days; quarter dates | Lakota-wide | Stay as built-in defaults |
| `Alex=Al` default nickname | Tony's family | Removed; nicknames come only from config |
| Late-rules seed naming Tony's kids' classes | Tony's family | Seed shrinks to `[default]`, `[quarters]`, and one commented example rule |
| `Brother_MFC_J4335DW` default printer | Tony's family | Default becomes the system default printer; blank config means "system default" |
| Drive archive path in `env.example`; `/home/tony` in `.desktop` files | Tony's machine | Replaced with placeholders |
| "for the Stein kids" in `pyproject.toml` | Tony's family | Reworded |
| `secret-tool` credentials | Linux | Stays on Linux; Windows uses Credential Manager |
| `lp` / `lpstat` printing | Linux | Stays on Linux; Windows uses SumatraPDF |
| systemd timer | Linux | Stays on Linux; Windows uses Task Scheduler |
| bash wrapper, Evince, `notify-send` | Linux | Stay on Linux; Windows uses `os.startfile` and toasts |
| `%-m` `%-d` `%-I` strftime codes | glibc only; raise on Windows | Replaced by one date helper |
| `tomllib` | Python 3.11+ | `requires-python` becomes `>=3.11`; the bundle ships 3.12 |

## 3. Package layout

```
lakota_grades/
  reports/
    __init__.py      REPORTS registry: {"open-work": OpenWorkReport()}
    base.py          Report protocol, BuildContext, Built
    open_work.py     the current sheet, moved out of print_sheet.py
  runner.py          the generic guards / refresh / archive / print / record loop
  host/              OS adapters, one implementation chosen at import time
    __init__.py      IS_WINDOWS, CREATE_NO_WINDOW, NotSupported, SERVICE, PrintError, SchedulingError, ScheduleInfo, task_name; adapters are imported as submodules
    printing.py      list_printers, default_printer, print_pdf
    scheduling.py    install, remove, describe
    notify.py        toast(title, body)
    opener.py        open_file(path)
    credentials.py   read_password, write
    task.xml         Task Scheduler template with {time} {exe} {workdir} placeholders (package data)
  app/
    actions.py       everything the buttons do, no tkinter imports
    gui.py           the tkinter window
    __main__.py      PyInstaller entry: no args -> gui, else cli.main(argv)
  dates.py           md, wd_md, time12, long_date
  config.py          gains config.toml load/save; env still overrides
  print_sheet.py     becomes a thin alias: Options -> runner.run("open-work", ...)
packaging/windows/
  LakotaSheet.spec   PyInstaller one-folder build
  installer.iss      Inno Setup script
  build.ps1          the steps CI runs, runnable by hand
.github/workflows/
  ci.yml             pytest on ubuntu-latest and windows-latest
  release.yml        on tag v*: build, package, attach installer to the GitHub release
docs/
  windows.md         the page Tony sends his friend
```

The package name `lakota-grades-mcp`, the `lakota-grades` command, and the module name
`lakota_grades` do not change. The Windows product name is **Lakota Sheet**.

## 4. Report plugin layer

A report is one PDF built from the snapshot for one day. The runner does everything
around it.

```python
@dataclass
class BuildContext:
    settings: Settings
    home: Path
    day: date
    now: datetime            # tz-aware
    out_dir: Path            # <home>/<report.output_dir>/<day>/, created by the runner
    kid: str | None          # --kid filter
    nicknames: dict[str, str]
    prev_rows: dict | None   # rows.json from the most recent earlier run of this report
    prev_label: str | None
    stale_note: str | None

@dataclass
class Built:
    pdf: Path
    rows: dict               # written to rows.json; next run gets it as prev_rows
    summary: str             # goes in the log line, e.g. "2p Al=5 Kate=2"

class Report(Protocol):
    key: str                 # "open-work"; used in CLI, config, task name
    title: str               # "Open Work Sheet"; used in the app and toasts
    output_dir: str          # "sheets" for open-work (keeps today's paths), "reports/<key>" for others
    default_time: str        # "14:00"
    def archive_name(self, day: date) -> str: ...    # "2026-09-14 Open Work.pdf"
    def build(self, snap: dict, ctx: BuildContext) -> Built: ...
```

Per-report options that are not shared (days ahead, overdue days) are read by the
report itself from `ctx.options`, which the runner builds by merging `config.toml`'s
`[reports.<key>]` table with CLI overrides. The registry is a dict in
`reports/__init__.py`; adding a report is a new module plus one entry.

The runner keeps the current behaviour and order exactly: no-print-days guard
(`--force` overrides), already-printed guard (only `--reprint` overrides), print-window
guard (before 14:00 is a catch-up, not a print; `--force`, `--dry-run`, `--date`
override), refresh with the 24-hour stale fallback, build, `rows.json`, archive copy
(warn and continue on failure), print, `printed.txt`, one log line. The window start
hour becomes the report's configured time rather than a constant, so a report scheduled
for 18:00 does not print at 15:00 on a catch-up.

## 5. Command line

```
lakota-grades run <report> [--dry-run] [--force] [--reprint] [--date YYYY-MM-DD]
                           [--kid NAME] [--no-refresh] [--printer NAME]
lakota-grades print-sheet  ...          alias for `run open-work`, same flags as today
lakota-grades reports                   list registered reports and their schedule
lakota-grades schedule install|remove|show [<report>]
lakota-grades printers                  list printers, mark the default
lakota-grades doctor                    check Python, Chromium, the PDF engine, the credential store, printers and the scheduler
lakota-grades set-credentials           unchanged interface; uses host.credentials
lakota-grades app                       open the settings window
```

`login`, `check`, `refresh`, `status` and `serve` are unchanged. `serve` still works
from a source install; it is simply not exposed in the Windows bundle.

## 6. Configuration and credentials

**Home directory.** `~/.lakota-grades` on Linux, `%LOCALAPPDATA%\lakota-grades` on
Windows. `LAKOTA_GRADES_HOME` overrides both. The `0700` chmod stays on Linux and is a
no-op on Windows.

**`config.toml`** lives in the home directory and is what the app edits:

```toml
[account]
username = "parent@example.com"       # the password is in the OS credential store

[print]
printer = ""                          # blank = system default printer
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

**Precedence**, highest first: command-line flag, environment variable (including
Tony's `.env`), `config.toml`, built-in default. Existing `LAKOTA_*` variables keep
their names and meanings. `LAKOTA_NICKNAMES` and `LAKOTA_PRINTER` continue to work.

**Credentials.** `Settings.credentials()` keeps its order: environment, OS store,
1Password references. The OS store is `host.credentials`:

- Linux: the existing `secret-tool` calls, unchanged, so Tony's stored entry keeps working.
- Windows: the `keyring` library's Windows Credential Manager backend,
  `service="lakota-grades"`, account = the OneLogin username from config. Credential
  Manager entries are per Windows user and readable by a scheduled task running as that
  user in an interactive session, with no prompt.

The password is never written to `config.toml`, the log, or a toast.

**Seeds.** `no-print-days.txt` keeps the district calendar. `late-rules.toml` seeds with
`[default] late_days = 14, credit = "?"`, the `[quarters]` table, and a commented-out
example `[[rule]]`. `ensure_seed` still never overwrites an existing file.

**Login stamp.** A passing Test login writes `<home>/login-ok.txt` with a timestamp.
The app uses it to decide whether the schedule may be enabled (section 8).

## 7. Host adapters

Each module in `lakota_grades/host/` has a Linux and a Windows implementation selected
by `sys.platform`. Nothing outside `host/` checks the OS. Every adapter takes its
`subprocess.run` as an injectable argument so tests can assert on the command built.

**printing**

```python
def list_printers() -> list[str]
def default_printer() -> str | None
def print_pdf(pdf: Path, printer: str | None, title: str, run=subprocess.run) -> str   # returns a job reference
```

- Linux: `lpstat -a` / `lpstat -d`; `lp -d <printer> -o sides=two-sided-long-edge -o media=Letter -t <title>` as today; the job reference is the CUPS request id.
- Windows: `win32print.EnumPrinters` and `GetDefaultPrinter` from pywin32; printing runs the bundled `SumatraPDF.exe -print-to "<printer>" -print-settings "duplexlong,paper=letter" -silent -exit-when-done "<pdf>"` with no console window. SumatraPDF does not return a job id, so the job reference is `<printer> @ <time>`. A non-zero exit or a printer name not in `list_printers()` is a print failure; the PDF is kept.
- `printer=None` means the system default: `lp` without `-d` on Linux, `-print-to-default` on Windows. The job reference then names the resolved default printer.

**scheduling**

```python
def install(key: str, time: str, days: list[str], exe: str, args: str, workdir: str, run=subprocess.run) -> None
def remove(key: str, run=subprocess.run) -> None
def describe(key: str, run=subprocess.run) -> ScheduleInfo   # managed_by, next_run, last_result
def command_for(key: str) -> tuple[str, str, str]   # (exe, args, workdir) that runs the report from this installation
```

- Linux: `install` and `remove` raise `NotSupported("managed by systemd; see README section 6")`; `describe` reports `managed_by="systemd"` and reads `systemctl --user list-timers` when present.
- Windows: `install` renders `lakota_grades/host/task.xml` and runs `schtasks /Create /TN "Lakota Sheet - <key>" /XML <file> /F`. The task: weekly `CalendarTrigger` on the configured days at the configured time; `StartWhenAvailable=true` so a run missed while asleep fires on wake (the runner's print-window guard then decides); `ExecutionTimeLimit=PT30M`; `MultipleInstancesPolicy=IgnoreNew`; `DisallowStartIfOnBatteries=false`; `StopIfGoingOnBatteries=false`; `WakeToRun=false`; principal `LogonType=InteractiveToken`, `RunLevel=LeastPrivilege`, so it runs only while the user is logged in, which is what Credential Manager and the printer need; action `<install dir>\LakotaSheet.exe run <key>`. `remove` runs `schtasks /Delete /F`; `describe` parses `schtasks /Query /FO LIST /V`.

**notify**

```python
def toast(title: str, body: str) -> None
```

- Linux: `notify-send -a "Lakota sheet"` when present, else nothing.
- Windows: a short PowerShell script using `Windows.UI.Notifications.ToastNotificationManager`, launched with `CREATE_NO_WINDOW`. No third-party toast library. The toast is attributed to the Start menu shortcut's `AppUserModelID` (`Cairnea.LakotaSheet`, set by Inno Setup) so it shows the app's name and icon. The runner toasts once per scheduled run: `OK` ("Printed today's Open Work Sheet, 2 pages"), `SKIP` (the reason), or `FAIL` (the one-line cause, plus "Open Lakota Sheet to check your password" for a login failure). Toasts never fire on `--dry-run`.

**opener**

- Linux: Evince if present, else `xdg-open`, detached as the bash wrapper does today.
- Windows: `os.startfile(path)`.

**Windowed process.** The Windows executable is built windowed, so `sys.stdout` and
`sys.stderr` are `None` inside it. The runner's log writes to `print-sheet.log` always
and to stderr only when it exists; logging goes to `<home>/app.log`.

## 8. The Windows app

One tkinter window, title "Lakota Sheet", launched from the Start menu, a desktop
shortcut, or `lakota-grades app`. Two tabs and an About box.

**Settings tab**

- OneLogin username (text) and password (masked; blank on save means "keep the stored one").
- Printer (dropdown from `host.printing.list_printers()`, first entry "System default", with a Refresh button).
- Print time (HH:MM, 24-hour, validated).
- Days ahead and overdue days (spin boxes, 1 to 60).
- Kid nicknames (multi-line, one `First=Nick` per line).
- Archive folder (text plus Browse; blank means none).
- Scheduled printing (checkbox).
- Buttons: **Save**, **Open late-work rules**, **Open no-print days**.

Save validates the fields, writes `config.toml`, stores the password if one was typed,
and then installs, updates, or removes the scheduled task to match the checkbox. If the
checkbox is on and `login-ok.txt` does not exist, Save stores everything but leaves the
task uninstalled and tells the user to run Test login first; the next Save after a
passing test installs it.

**Run tab**

- **Test login**: `check` in a worker thread; writes `login-ok.txt` on success.
- **Preview today's sheet**: `run open-work --dry-run --force`, then opens the PDF.
- **Print now**: `run open-work --force --reprint`.
- A read-only log pane that streams the worker's output so the one-to-three minute refresh is visibly alive; buttons are disabled while a worker runs.
- A status line: the last line of `print-sheet.log` and `describe()`'s next run time.

**About**: version, a link to the repo, and the SumatraPDF and Chromium licence notes.

**Structure.** `app/actions.py` implements every button as a plain function that takes
a `log: Callable[[str], None]` and returns a result object. `app/gui.py` only builds
widgets, spawns threads, and marshals log lines back to the main loop. `actions.py` is
tested; `gui.py` is not.

Files owned by Plan 2: `<home>/login-ok.txt` (written by Test login) and `<home>/app.log`
(the windowed exe's logging target). Neither exists after Plan 1.

## 9. Build and distribution

- **CI (`ci.yml`)**: on every push and PR, `pytest` on `ubuntu-latest` and `windows-latest` with Python 3.12. The Windows leg exists so a glibc-only format code or a POSIX-only path assumption can never ship again.
- **Release (`release.yml`)**: on a `v*` tag, a `windows-latest` job runs `packaging/windows/build.ps1`, which:
  1. `pip install .[windows]` (adds `pywin32`, `keyring`, `pyinstaller`).
  2. `playwright install chromium` with `PLAYWRIGHT_BROWSERS_PATH=build\ms-playwright`.
  3. Downloads the pinned SumatraPDF portable release, checks its SHA-256, and stages the exe with its licence file.
  4. `pyinstaller packaging/windows/LakotaSheet.spec` producing `dist\LakotaSheet\` with `LakotaSheet.exe` (windowed, `app/__main__.py`), the Playwright driver, and `ms-playwright\` copied in.
  5. `iscc packaging/windows/installer.iss` producing `LakotaSheet-Setup-<version>.exe`.
  6. Attaches the installer to the GitHub release for the tag.
  7. The build runs `packaging/windows/smoke.ps1` on the bundle before packaging: `LakotaSheet.exe doctor` (all probes must pass), a dry-run sheet from a fixture snapshot, and a no-arguments launch that must still have a window after eight seconds.
- **Installer**: per-user (`PrivilegesRequired=lowest`, installs under `%LOCALAPPDATA%\Programs\Lakota Sheet`), Start menu shortcut with `AppUserModelID`, optional desktop shortcut, "Launch Lakota Sheet" on finish. `[UninstallRun]` calls `LakotaSheet.exe schedule remove` before files are deleted. Data under `%LOCALAPPDATA%\lakota-grades` is left in place on uninstall and the uninstaller says so.
- **Runtime**: `app/__main__.py` sets `PLAYWRIGHT_BROWSERS_PATH` to the bundled folder before importing Playwright.
- **Size**: about 200 MB, almost all Chromium. Accepted.
- **Version**: single source in `pyproject.toml`; `build.ps1` reads it and passes it to PyInstaller and Inno Setup; the About box shows it.
- **Updates**: none in this version. He downloads and runs the next installer over the top; Inno Setup handles the upgrade in place.

## 10. Compatibility with Tony's Linux install

- `lakota-grades print-sheet` and every flag keep working, so `systemd/lakota-print-sheet.service`, the timer, `scripts/lakota-sheet-desktop.sh` and the `.desktop` files do not change.
- `secret-tool` credentials are read exactly as today.
- `~/.lakota-grades/.env` is read exactly as today and overrides `config.toml`.
- Existing `sheets/<date>/` folders are the open-work report's `output_dir`, so the NEW/was diff against the previous sheet is unbroken.
- **One migration step**: because the `Alex=Al` default leaves the code, Tony adds `LAKOTA_NICKNAMES=Alex=Al` to his `.env` (or the `[kids]` table to a `config.toml`) before upgrading, or Al prints as Alex.
- The late-rules seed change does not touch Tony's existing `late-rules.toml`.

## 11. Error handling

Unchanged: a failed refresh prints from a snapshot under 24 hours old with a footer
note and fails past that; an unreachable archive folder warns and still prints; a
broken `late-rules.toml` is an error, never a silent fallback; nothing logs a credential.

New:

- A login failure during a scheduled run toasts and logs `FAIL`; the app's status line shows it the next time it opens.
- A printer that is not in `list_printers()` at run time (renamed, removed) fails the print, keeps the PDF, and toasts the printer name.
- SumatraPDF missing from the install folder is a `FAIL` naming the path, not a crash.
- `schtasks` failing (policy, corrupted task store) surfaces its stderr in the Save error dialog; the config is still saved.
- `config.toml` that does not parse is an error naming the file; the app offers to open it in Notepad. Unknown keys are ignored so a newer config works with an older app.
- Two overlapping runs (a scheduled run while Print now is going) are prevented on Windows by `MultipleInstancesPolicy=IgnoreNew` for the task and by a lock file in the home directory for everything else; the second run logs `SKIP already running`.

## 12. Testing

Existing tests keep passing unchanged except where they import from `print_sheet`
symbols that move to `runner` or `reports.open_work`. New tests:

- `test_dates.py`: every helper, including noon, midnight, and the 23:59 "no time" case that `fmt_due` relies on.
- `test_reports.py`: registry contents; `OpenWorkReport.build` produces the same PDF page count and rows as the pre-split code for a fixture snapshot.
- `test_runner.py`: each guard, the stale fallback, archive failure, print failure, `printed.txt` append, the lock file, and the toast calls, with fake printing and notify adapters.
- `test_config.py`: `config.toml` round trip, precedence (flag over env over file over default), unknown keys ignored, nicknames parsing from both sources.
- `test_host_windows.py` (runs on both OSes with injected `run`): the exact `schtasks`, SumatraPDF and PowerShell command lines; Task XML rendering against a golden file; `describe()` parsing of a captured `schtasks /Query` output.
- `test_host_linux.py`: `lp`, `lpstat`, `notify-send` command lines; `install` raises `NotSupported`.
- `test_actions.py`: each app action with fakes, including "Save with schedule on but no login stamp" leaving the task uninstalled.

The PyInstaller build is verified by the release job launching `LakotaSheet.exe run open-work --dry-run --no-refresh` against a fixture snapshot and checking that a PDF appears; this is the one test that runs on the built artefact. The same smoke test also installs and removes the "Lakota Sheet - open-work" scheduled task through `schedule install`/`schedule remove` and confirms it with `schtasks /Query`, then launches the window with no arguments and checks it is still alive with a real window handle after 8 s.

## 13. Known limitations, told to the friend in `docs/windows.md`

- If the district has enabled multi-factor authentication on his OneLogin account, the unattended refresh cannot work. Test login reports this ("OneLogin did not redirect after submitting credentials") and there is no workaround short of an MFA-free account.
- The installer is not code-signed. Windows SmartScreen shows "Windows protected your PC" on first launch; he clicks More info, then Run anyway. Signing costs money and is out of scope.
- The scheduled run only fires while he is logged in to Windows. A locked screen is fine; a signed-out or powered-off PC skips that day and the next day's run does not print the old sheet.
- Everything stays on his machine. The app talks only to OneLogin, Canvas and HAC.

## 14. Out of scope for this version

macOS build; system-tray icon; auto-update; code signing; packaging the MCP server;
more than one OneLogin account per install; a GUI editor for late-work rules (Notepad is
the editor); reports other than open-work (the layer exists, no second report ships).

## 15. Risks to retire first in the plan

1. **Playwright inside PyInstaller.** The driver and `PLAYWRIGHT_BROWSERS_PATH` handling are known to work with the community hook, but this is the one thing that would sink the packaging, so the plan's first Windows task is a throwaway build that launches Chromium headless from the bundle.
2. **SumatraPDF duplex flags on his printer.** `duplexlong` is honoured only if the driver reports duplex; the fallback is a single-sided sheet, which is acceptable.
3. **Credential Manager from a scheduled task.** `InteractiveToken` makes this work; the plan includes a manual check on a real machine before the release job is trusted.
