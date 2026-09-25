# Fridge Sheet for Windows

Fridge Sheet prints a one-page-per-kid list of open schoolwork every school day at a time you choose, pulled from Canvas and Home Access Center with your own OneLogin parent login (the district defaults are Lakota's; another district's addresses go in `.env`, see "Your files"). Everything runs on your PC. The app talks only to OneLogin, Canvas and Home Access Center — and, once a day, asks GitHub whether a newer version exists, which sends nothing and can be switched off on Settings. Nothing about your kids leaves your computer.

## Before you start

- Windows 10 or 11, 64-bit, and a printer Windows can already print to.
- Your district's OneLogin parent username and password. If the district has turned on **multi-factor** sign-in for your account (a code on your phone every time), the automatic refresh cannot work; Test login will tell you so.
- About 900 MB of disk space once installed (the installer itself is about 270 MB); a copy of Chromium is included so the app can sign in the way a browser does.

## Install

1. Download `FridgeSheet-Setup-<version>.exe` from the Releases page.
2. Run it. Windows **SmartScreen** will say "Windows protected your PC" because the installer is not code-signed. Click **More info**, then **Run anyway**.
3. The installer needs no administrator password; it installs for your Windows user only and offers a desktop shortcut. It registers a task that starts Fridge Sheet quietly whenever you sign in, and opens the app when it finishes.
4. If Windows Defender or another antivirus quarantines the installer or the app, restore it and add an exclusion; unsigned programs built from Python sometimes trip these heuristics.

## First run

Fridge Sheet is a small web app that runs on your own PC. The shortcut starts it if it is not already running and opens it in your browser at `http://127.0.0.1:8433/`. Nothing is published to the internet; only this PC can reach that address unless you turn on the option below.

1. **Settings page.** Enter your OneLogin username and password. The password goes into Windows Credential Manager, never into a file, and the page refuses to take one from another device. Pick your printer (or leave "System default") and how many days ahead to look. If your kids go by nicknames, put one `First=Nick` per line. Click **Save**.
2. **Settings page → Test login.** Takes up to a minute; progress appears on the page as it goes. Both lines must say OK. If not, fix the username and password, Save, and try again.
3. **Schedules page.** This is where you turn printing on. The built-in "Open Work Sheet" has its own section here, and so does any report you build yourself on the Reports page. In the section for the report you want, tick **Run this on a schedule**, set a time, and tick the days. Leave the printer where it says "(the printer on the Settings page)" to use the one you already chose, or pick a different printer just for this report. Tick **Print it** to have the sheet print itself, or leave it unticked to keep it as a PDF only, without printing — handy if you want to check a sheet before it goes to a kid. Click that section's **Save** — that's all it takes, and it works even before Test login has passed. There is no Windows task to install: Fridge Sheet's own background server (the one the installer set to start when you sign in) checks this setting once a minute and fires it itself at the time you chose, for as long as that server is running.
4. **Dashboard → Refresh now** pulls Canvas and Home Access Center and fills the page in. **Preview today's sheet** builds the PDF and links it; **Print now** prints it straight away.
5. **Runs** lists every sheet that has been built or printed, with a link to each PDF and a Reprint button.
6. To read the sheet on your phone, tick **Allow other devices on this network** on the Settings page and save. Saving says the server address changed; sign out and back in (or restart the PC) so the background task picks it up, and the Settings page then shows the address to type on the phone — with a **QR code** next to it, so you can point the phone's ordinary camera at the screen instead of typing. Leave the box unticked if you would rather keep the app on this PC only.

## What happens every day

At the time you chose, on school days, Fridge Sheet's own background server fires the schedule itself — there is no separate Windows task per report — while you are **logged in** (a locked screen is fine; a signed-out or powered-off PC skips that day, and the next day's run does not print the old sheet). If the server was only briefly unavailable, it catches up the moment it is back, as long as that is still the same day and at or after the time you chose. It refreshes Canvas and Home Access Center, builds the sheet, prints it two-sided, and shows a small notification saying it printed, or why it did not. If the refresh fails, it prints from the last good data if that is under a day old and says so on the sheet. If your printer cannot print two-sided, the sheet comes out on separate pages.

If the data goes older than 24 hours, every page carries a banner saying how old it is and when the last good refresh was. That is the same ceiling at which a scheduled print refuses to run, so the banner and the missing sheet always agree about why.

## Your files

Everything lives in `%LOCALAPPDATA%\fridgesheet` (paste that into File Explorer's address bar):

| File | What it is |
|---|---|
| `sheets\<date>\sheet.pdf` | every sheet, one folder per day |
| `no-print-days.txt` | days not to print (seeded with the district calendar); edit it on the Settings page |
| `late-rules.toml` | how long each class still takes late work; edit it on the Settings page |
| `fridgesheet.db` | the app's database: what each refresh found, the run history, your notes and flags |
| `print-sheet.log` | one line per run -- printed, skipped, or why it failed -- after an `INFO ingested ...` line on runs that refreshed |
| `app.log` | the app's own log, including the web server's |
| `doctor.txt` | the last diagnostics report |
| `config.toml` | your settings (no password in it) |
| `web.lock` | present only while the server is running; it keeps a second copy from starting |

## If something goes wrong

- **Diagnostics** (in the list down the left of every page) checks Chromium, the PDF engine, the credential store, printers, the scheduler and the web server, and writes `doctor.txt`. Any `FAIL` line is the place to look.
- **The shortcut does nothing, or the browser says it cannot connect**: the server did not start. Open `app.log` -- the last lines say why. Signing out and back in starts it again; so does running the shortcut a second time.
- **The page says "Fridge Sheet only answers at http://127.0.0.1:8433/"**: you reached the app by some name other than the address it is served on — this PC's computer name (`http://dobby:8433/`), an SSH or Remote Desktop port-forward, or a shortcut somebody edited. Fridge Sheet has no password, so it answers only at its own addresses; anything else is refused, whether it is you or a web page trying it behind your back. On this PC, use `http://127.0.0.1:8433/` (the desktop shortcut already does). For a phone or tablet, tick **Allow other devices on this network** on the Settings page and use the address or QR code it then shows — that address is allowed as soon as the setting takes effect. A *name* (`http://dobby:8433/`, a Tailscale MagicDNS name) is different: even with that tick on, a name is refused until you list it — see **Advanced: `[web] extra_hosts`** below, and the refusal page itself shows the exact line to add once other devices are allowed.
- **Advanced: `FRIDGESHEET_WEB_HOST`**: you can pin the address Fridge Sheet binds to, by putting a line like `FRIDGESHEET_WEB_HOST=0.0.0.0` in `%LOCALAPPDATA%\fridgesheet\.env` (create the file if it is not there) and restarting the app. It overrides the **Allow other devices on this network** tick. Be honest about what it is for:
  - `FRIDGESHEET_WEB_HOST=0.0.0.0` is the same thing that tick does — every address on this PC, loopback included. Use the tick instead; this is here for a service or a script that has no UI.
  - `FRIDGESHEET_WEB_HOST=127.0.0.1` forces loopback only, even if the tick is on. That is the one use worth knowing: it keeps the app off the network without touching Settings.
  - **Pinning it to a computer name or a single LAN IP is not a way to make `http://dobby:8433/` work.** The app would then answer at that address *and stop answering at `127.0.0.1`* — and three things look for it there: the shortcut's "is it already running?" check (so launching it twice can start a second copy or fail), Diagnostics' web-server check (which will report `FAIL` while the app is running perfectly well), and `fridgesheet web`'s hand-off to a server that is already up. Use `127.0.0.1` here; to reach the app by a computer name, list the name under `[web] extra_hosts` instead (next bullet).
- **Advanced: `[web] extra_hosts`**: the names Fridge Sheet will answer to besides its own addresses. Addresses never need listing — with **Allow other devices on this network** ticked, every address this PC has is accepted — but a *name* is only accepted when it is on this list, because a name is exactly what a DNS-rebinding attack forges. Open `%LOCALAPPDATA%\fridgesheet\config.toml`, find the `[web]` section (it is there once other devices are allowed; add the heading if not) and put the names under it, then restart the app:

  ```toml
  [web]
  allow_lan = true
  extra_hosts = ["dobby", "dobby.tailnet-1234.ts.net"]
  ```

  This only works together with the tick (or `FRIDGESHEET_WEB_HOST=0.0.0.0`): the list is consulted only when the app is listening on every address. Type the names in lower case; matching ignores case either way.

- **"Login failed"**: the username or password is wrong, or OneLogin wants multi-factor sign-in. Fix the Settings page, Save, and Test login again.
- **Nothing printed at the scheduled time**: open the Runs page; it shows the last result for every day. Common causes: the PC was off or you were signed out; the printer was off (the sheet is kept as a PDF in `sheets\<date>`, and the Runs page links it); it was a no-print day. The Schedules page itself is the other place to look: each report's row shows **next:** with when it will next try and **last:** with when it last actually ran on a schedule and whether that was OK; if the page header says "Schedules are paused: the scheduler inside Fridge Sheet has stopped", restart Fridge Sheet. Task Scheduler is not involved in a report's own schedule any more — the only Fridge Sheet entry you will ever see there is **"Fridge Sheet - web"**, the always-running server itself. To stop a report's schedule for good, go to the Schedules page, untick **Run this on a schedule** for it, and Save.
- **Wrong printer**: pick another on the Settings page and Save; the app never uses the Windows default unless you leave the choice at "System default". **Print now** on the Dashboard prints straight away so you can check.

## Upgrading from Lakota Sheet

Fridge Sheet was called Lakota Sheet through version 0.3. Run the Fridge Sheet installer over it: setup removes the old app first, then installs the new one, and the first start moves your data (`%LOCALAPPDATA%\lakota-grades` becomes `%LOCALAPPDATA%\fridgesheet`, `lakota.db` becomes `fridgesheet.db`) and copies your saved password to the new name in Credential Manager. Your notes, flags, run history, sheets and schedules all carry over. Two things to check afterwards: the Start-menu and desktop shortcuts now say Fridge Sheet (the old ones were removed with the old app), and if someone registered the old "Lakota Sheet - web" task for you by hand, it needs replacing with "Fridge Sheet - web" the same way. The old `lakota-grades` entry in Credential Manager is left alone; delete it yourself once everything works.

## Uninstall

Settings → Apps → Fridge Sheet → **Uninstall**. The uninstaller removes the program and every task it installed itself -- the always-on server task, plus any leftover Task Scheduler entry a much older version left behind (a report's own schedule has not created a Windows task since Fridge Sheet started firing schedules itself) -- and leaves your sheets, settings, database and logs in `%LOCALAPPDATA%\fridgesheet` for you to delete if you wish. Your password stays in Credential Manager under "fridgesheet" until you remove it there.

The uninstaller runs that cleanup silently, so if you want to be sure, open Windows **Task Scheduler** afterwards and look for anything still named "Fridge Sheet - ...". Nothing should be left; if something is (the cleanup could not read its own settings for it, say), select it and click **Delete** — those tasks do nothing once the program is gone, but they will keep trying to start it.

## Credits and licences

Fridge Sheet is MIT-licensed: https://github.com/steiner385/fridgesheet. It bundles Chromium via Playwright (BSD-3-Clause), SumatraPDF 3.5.2 for printing (GPL-3.0; source at https://github.com/sumatrapdfreader/sumatrapdf/tree/3.5.2rel; the licence text is installed as `SumatraPDF-LICENSE.txt`), and segno for the Settings page's QR code (BSD-3-Clause, Copyright 2016-2025 Lars Heuer).
