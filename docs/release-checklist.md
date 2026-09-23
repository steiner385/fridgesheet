# Release checklist — the human part

This is what you (Tony, or whoever else ends up running this) do on a real Windows PC,
with a real printer and a real phone, after a release ships. **CI has already proved
everything it can prove on a runner with no printer, no phone and no camera; this
checklist only covers what's left.** Nothing here can be done by an agent — there is no
substitute for a real PC and your own eyes.

**A release ships on every merge to `main`, not by hand.** `.github/workflows/release.yml`
waits for `ci` to pass on the merge commit, then picks the version itself
(`packaging/pick_version.py`): a deliberate bump in `pyproject.toml` wins outright, otherwise
the latest published tag's patch number goes up by one. It tags and publishes without a
human pushing anything. A pushed `v*` tag or `workflow_dispatch` still works for a
deliberate, hand-chosen version — the automatic path is only the default for an ordinary
merge. A merge commit opts out with `[skip release]` on a line of its own
(`packaging/skip_release.py`), for a change that should not ship alone (e.g. one half of a
two-PR split) — deliberately not a substring match anywhere in the message, since PR #61's
own commit *explaining* that marker in prose tripped a naive `contains()` check and skipped
its own release.

Read §1 first even if you have done this before: it is the hazard (an upgrade landing on a
running app, #33) that §3 and later sections exist to prove fixed.

Work through it in order. Every box has the result you should see next to it; if you see
something else, stop and fix it before moving on — the sections build on each other (you
can't test a schedule before Settings works, and you can't uninstall before you've
installed).

## 0. What CI already proved — don't re-check these

`.github/workflows/ci.yml` already ran the full pytest suite on **both** `ubuntu-latest`
and `windows-latest` for the commit you're about to tag. `.github/workflows/release.yml`
then, on a Windows runner:

- [ ] *(nothing to do — already true if the release workflow run for this commit is green)*
  - Refused to build if the tag doesn't match `version` in `pyproject.toml`.
  - Ran `packaging/windows/build.ps1`, which built the real `FridgeSheet.exe`, ran
    `packaging/windows/smoke.ps1` against it, and only then wrapped it with Inno Setup.
    That smoke test already exercised, on a real Windows machine: `doctor` passing inside
    the frozen bundle; a `--dry-run` sheet building a real PDF from a fixture snapshot;
    `schedule install` / `schedule remove --all` round-tripping through a real `schtasks`;
    the web server answering `/health`, `/`, `/diagnostics` and `/settings`; a no-args
    launch finding the already-running server and exiting cleanly; and `service install` /
    `service remove` round-tripping the logon task through `schtasks` too.
  - Uploaded the built installer and, on a tag push, attached it to a GitHub release with
    the SumatraPDF licence note in the body.

`tests/test_packaging.py` (run as part of that same suite) pins the shape of
`installer.iss` (per-user install, no admin prompt, the `[UninstallRun]` entries, the
"your data was kept" message naming `fridgesheet.db`), the SumatraPDF version/URL/licence
hashes, and that the temporary `ccswitch` branch trigger is not in `release.yml`. If any
of that had drifted, the suite would already be red and you would not be looking at a
built installer at all.

**So: don't re-run the test suite by hand, don't re-check the installer's Inno Setup
script by reading it, and don't re-verify the SumatraPDF licence pin.** None of that is
what a human adds. What only a human with this hardware can prove is everything below.

## 0b. What a real Windows box has since proved — 2026-09-17, `graphy`

The paragraphs below used to say the installer's `[Code]` had "never been run on Windows".
That is no longer true. On **2026-09-17** the CI-built `FridgeSheet-Setup-0.2.0.exe` from
run 35246094795 (`7fbba23`) was driven over SSH on **graphy**, a Windows 11 26200 desktop,
entirely from the command line. What that pass established:

- **Install** lands: 1499 files, 875 MB, under `%LOCALAPPDATA%\Programs\Fridge Sheet`, no
  admin prompt (the log records "Administrative install mode: No"), Start-menu and desktop
  shortcuts both created — the desktop one on the **OneDrive-redirected** desktop, which is
  where `{autodesktop}` correctly resolves on a machine with Known Folder Move on.
- **The logon task registers** (`Fridge Sheet - web`, "At log on", "Interactive only").
- **The frozen app runs**: `/health` answers with the real version, and `/`, `/settings`,
  `/diagnostics`, `/schedules`, `/runs`, `/trends` all return 200 with content.
- **§3's upgrade over a running app works** — issue #33's fix, executed for the first time.
  A server was started, confirmed serving, and the same installer run over the top: exit
  code 0, all 1499 files replaced, and Inno's own log reads *"RestartManager found no
  applications using one of our files"* because `PrepareToInstall` had already killed it.
  The process was alive immediately before and gone immediately after.
- **§5's Schedules page writes a real task.** With the `login-ok.txt` gate satisfied, a
  POST to `/schedules` created `Fridge Sheet - open-work` in Task Scheduler with the right
  `<Command>`, `<Arguments>`, `StartBoundary` and `<Thursday/>`; the page read it back and
  recognised it as its own; saving with the box unticked deleted it again.
- **§7's uninstall with a hand-started copy running works.** Every `_internal` DLL was
  deleted out from under a live server, `{app}` gone, no `Fridge Sheet - ` tasks left, both
  shortcuts gone, and `%LOCALAPPDATA%\fridgesheet` kept with `fridgesheet.db` intact.
- **A stale `web.lock` is harmless.** Every upgrade now force-kills the server, which leaves
  the lock file behind with a dead pid in it. The next start takes it anyway — it is a
  kernel lock the OS releases on death, not an advisory flag — so an upgrade does not brick
  the next launch.

One defect came out of that pass and is fixed: a silent uninstall stopped on the farewell
`MsgBox`, which `/SUPPRESSMSGBOXES` does not cover for a box raised from `[Code]`. It is a
`SuppressibleMsgBox` now, pinned by `test_the_uninstall_farewell_message_can_be_suppressed`.

**What that pass could not touch, and why** — this is what is actually left for you:

- Anything needing **your OneLogin credentials**: Test login, Refresh, Preview, and so a
  real scheduled run firing. §4 and most of §5.
- Anything needing **paper**: §4's Print now. graphy has the Brother MFC-J4335DW in its
  printer list, and **no Windows default printer is set**, so pick the Brother explicitly.
- Anything needing **a phone and a camera**: all of §6.
- Anything needing **a mouse**: SmartScreen's "Run anyway", the wizard's pages, and the
  fact that no UAC prompt appears.
- The **`taskkill /T` children**: §3 and §7 were both exercised against an idle server. A
  Refresh or a print in flight, so that Chromium under `ms-playwright\` and `SumatraPDF.exe`
  are live under `{app}`, is the case `/T` exists for and it still has not been run.
- **Which account hosts it.** As of 2026-09-22 the `Fridge Sheet - web` task on graphy runs
  as `lakotarunner`, with its install under `C:\Users\lakotarunner\AppData\Local\Programs\
  Fridge Sheet`. (It has been `tony` and `gdrunner` at different times; check rather than
  assume — `schtasks /Query /TN "Fridge Sheet - web" /FO LIST /V` prints `Run As User`.) A
  per-user logon task only fires for the user that owns it, and a per-user install lives in
  that user's profile, so `fridgesheet self-update` refuses when run by anyone else.

## 1. The hazard, and what's supposed to fix it

**Issue #33: an upgrade lands on a running app.** The logon task holds
`FridgeSheet.exe` and its `_internal` DLLs open around the clock, and there is no in-app
"quit" — no tray icon, no shutdown button. Until now, `installer.iss` had no `[Code]`
step to deal with that, so running the installer a second time over an already-running
copy would hit Inno's Restart Manager: at best "Setup was unable to close the following
applications", at worst a demand to reboot mid-install.

`installer.iss` now has a `PrepareToInstall` in `[Code]` that runs before `[Files]`
copies anything: it ends the **"Fridge Sheet - web"** logon task
(`schtasks /End`) and force-kills any `FridgeSheet.exe` still standing
(`taskkill /IM FridgeSheet.exe /T /F` — the `/T` matters: it takes the process's
children down with it, and `{app}` also holds the Chromium under `ms-playwright\` and
`SumatraPDF.exe`, so killing only the parent leaves exactly the locked files this step
exists to release), ignoring both commands' exit codes — a first
install has no task and no process, and both legitimately return non-zero then, so
failing on that would break the install that works today. `[Run]` re-registers and
restarts the task afterward, once the new files are in place.

**This has now been run against a real Windows 11 install and works** (section 0b) — but
only over an *idle* server. Section 3 below is where you prove it for the case that
actually bites, an upgrade landing while a Refresh or a print is in flight. If it
doesn't, the manual fallback is the same as it always was: open **Task Scheduler**,
find **"Fridge Sheet - web"**, click **End**, confirm no `FridgeSheet.exe` remains in
**Task Manager**, then re-run the installer.

## 2. Install as a standard user

- [ ] Download `FridgeSheet-Setup-<version>.exe` from the GitHub release you just built
  (not a hand-built one — the one CI produced and attached). Do this logged in as a normal
  Windows account, not an administrator.
- [ ] Run it. **Expect:** Windows SmartScreen says "Windows protected your PC" (the
  installer isn't code-signed). Click **More info**, then **Run anyway**.
- [ ] **Expect:** no UAC/administrator prompt appears at all — the installer runs entirely
  as your user (`PrivilegesRequired=lowest`).
- [ ] Click through. **Expect:** no directory picker (it installs to
  `%LOCALAPPDATA%\Programs\Fridge Sheet` without asking) and a **"Create a desktop
  shortcut"** checkbox on the tasks page.
- [ ] Finish the wizard with **"Open Fridge Sheet"** left ticked. **Expect:** the installer
  closes and a browser window opens on its own at `http://127.0.0.1:8433/`, showing the
  Fridge Sheet dashboard.
- [ ] Check the desktop for the **Fridge Sheet** shortcut (if you left that box ticked).
- [ ] Open **Task Scheduler** and find **"Fridge Sheet - web"**. **Expect:** it exists,
  its trigger is "At log on", and its status is "Running" (or "Ready" if it hasn't
  actually needed to (re)start since you logged in).

  **Or, if Windows would not let this account create the task** (a standard user can be
  refused outright, #10): **Expect** no "Fridge Sheet - web" task, but a **Fridge Sheet**
  shortcut in the Startup folder (Win+R, `shell:startup`), the app already answering at
  `http://127.0.0.1:8433/`, and `FridgeSheet.exe service show` saying it "starts at
  sign-in from …\Startup\Fridge Sheet.lnk". Sign out and back in: **expect** it answers
  again without being opened by hand. Record which case this machine was, the Windows
  edition, and whether the account is an administrator.
- [ ] **Expect** no error dialog at the end of setup. If one says Fridge Sheet "could not
  set itself up to start when you sign in", that is a failure to report with the text from
  the app's Diagnostics page; the wizard no longer reports success over it (#10).

## 3. Upgrade over a running install — prove issue #33's fix

Section 2 just left Fridge Sheet running: the installer's own "Open Fridge Sheet" step
opened a browser at it, and its logon task should show "Running" in Task Scheduler. Do
**not** stop it by hand — that would only prove the old manual workaround still works,
not that the installer stops it itself.

The steps below upgrade over an **idle** server, which is the easy case. The case that
actually bites is a Refresh or a print still in flight: `{app}` also holds Chromium
under `ms-playwright\` (driven by a dashboard **Refresh now**) and `SumatraPDF.exe`
(driven by a print), and `PrepareToInstall`'s `taskkill /T` is what is supposed to take
those down with the parent rather than leave them winding down on their own. If you
have time, repeat this section a second time with a Refresh started right before you
launch the installer, to actually exercise that.

- [ ] Run the **exact same** `FridgeSheet-Setup-<version>.exe` you just installed, a
  second time, over the top. Click through it exactly as you did in section 2.
- [ ] **Expect:** no "Setup was unable to close the following applications" dialog, and
  no prompt to reboot. If you see either, `PrepareToInstall` didn't stop the app in
  time — that's a real finding for issue #33, not a false alarm; note what the dialog
  named and file it.
- [ ] Finish the wizard with **"Open Fridge Sheet"** left ticked, same as before.
  **Expect:** the installer closes and a browser window opens on its own, same as a
  first install.
- [ ] Open **Task Scheduler** and find **"Fridge Sheet - web"** again. **Expect:** it
  still exists, with a trigger of "At log on" and a status of "Running" (or "Ready") —
  `[Run]`'s `service install` re-registered it after `PrepareToInstall` ended it.
- [ ] Open **Settings** and read the version at the bottom of the form. **Expect:** the
  version you just installed. On 2026-09-18 a 0.3.0 upgrade over 0.2.0 kept saying 0.2.0:
  Inno copies the new bundle over the old and deletes nothing, so both versions' dist-info
  folders sat in `_internal` and the app read the older one — to the About box, to
  `/health`, and to the update check, which would have offered the app its own version.
  `[InstallDelete]` now clears them first; this box is what proves it on a real upgrade.
- [ ] **Wait until the dashboard page has finished loading**, then open **Task
  Manager**. **Expect:** exactly one `FridgeSheet.exe` process. (Checking too early can
  show two or three: the no-args launcher that the shortcut/postinstall step runs is a
  separate `FridgeSheet.exe` from the server it spawns, and it can take up to 30
  seconds of polling before the launcher opens the browser and exits, per
  `fridgesheet/web/__main__.py`'s `launch()`. One process is the steady state once
  the page is actually up; more than one at that point is the real finding.)

## 3b. Self-update, over a running app

Section 3 proves the *installer* survives landing on a running app, run by a human. This
proves the app can start that installer **on itself** — the in-app Update button and
`fridgesheet self-update` both end up calling the same `PrepareToInstall` this checklist has
already exercised, but by way of a Windows spawn (`cmd /c start "" /b <installer> ...` in
`fridgesheet/host/selfupdate_windows.py`). It needs a release newer than the installed one,
so do it on the release after the one that introduces self-update — the current install
stays as-is until then.

✅ **Proven false, then corrected, 2026-09-23.** This section used to carry a caveat that the
detachment mechanism (`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`) was unproven on real
Windows. It has since been measured (GitHub Actions runs 35844316753 and 35844539925,
workflow `probe-detachment.yml`, branch `probe/windows-detachment`, `windows-latest`,
2026-09-23) and the reviewer's suspicion was correct: an installer spawned with those flags
was killed by `taskkill /T` exactly like an unflagged control spawned alongside it — both
confirmed recorded descendants of the parent, both dead after the tree kill. The flags
touch console/Ctrl+C behavior, not `InheritedFromUniqueProcessId`, which is what `taskkill
/T` actually walks. `fridgesheet/host/selfupdate_windows.py`'s `spawn_installer` has been
changed to `cmd /c start "" /b <installer> ...` instead, which the same experiment measured
to survive (including with a space in the target's path) because cmd.exe exits immediately,
breaking the recorded parent/child chain before `taskkill /T` snapshots it.
`packaging/windows/smoke.ps1` step 4 now exercises this corrected mechanism (and a
spaces-in-path case) on real Windows CI, gating rather than merely warning. The checklist
items below still verify the end-to-end behavior on a real family-PC-shaped machine; treat
them as confirmation, not as the first evidence anymore.

- [ ] Settings → set an **Update PIN**, Save. **Expect:** `config.toml`'s `[web]` has an
  `update_pin_hash` beginning `pbkdf2_sha256$...`, and the PIN itself appears nowhere in it —
  same rule as the password, but a hash instead of a keyring entry, because a PIN this short
  is only as strong as its hash's cost.
- [ ] Reload Settings. **Expect:** the PIN box is empty, with its placeholder — a PIN is
  settable and never readable, same as the password field above it.
- [ ] From a **phone**, enter the wrong PIN five times. **Expect:** each one refused with
  "That PIN is not right.", then the sixth attempt — right or wrong — answered with "Too many
  wrong PINs. Try again in 15 minutes." for fifteen minutes from the fifth failure.
- [ ] From the phone, after the lock expires, enter the right PIN and press **Update**.
  **Expect:** progress in the page, then it waits (the server is about to be killed out from
  under the response that told it to wait), then it reloads on its own showing the new
  version — the page's own poll against `/health`, not you refreshing it.
- [ ] Open **Settings** and read the version at the bottom of the form. **Expect:** the new
  one. This is the same `[InstallDelete]` hazard section 3 already covers: if it still reads
  the old version, that is a real finding, not something to shrug off because "the update
  reported success."
- [ ] Open **Task Scheduler**. **Expect:** `Fridge Sheet - web` still there, still Running (or
  Ready) — the spawned installer's own `[Run]` step re-registered it, the same as section 3.
- [ ] **Wait until the dashboard page has finished loading**, then open **Task Manager**.
  **Expect:** exactly one `FridgeSheet.exe`, for the same reason and on the same timing as
  section 3's equivalent box.
- [ ] **Do it again with a Refresh in flight**, so Chromium is live under `{app}` when the
  installer's `taskkill /T` runs. This is the case `/T` exists for, the one section 3 also
  flagged as still-unexercised: if the spawned installer is *itself* a process Windows still
  tracks as a descendant of `FridgeSheet.exe` — which is exactly what the corrected `cmd /c
  start` mechanism above is measured to avoid, and what the old flags-based one did not —
  this is where a Refresh's Chromium, or the installer itself, would die mid-update instead
  of surviving it. **Expect:** the installer completes and the page reloads on the new
  version, same as the idle-server run above. If the update instead stalls, the page never
  reloads, or Task Manager shows no `FridgeSheet.exe` at all afterward, that is a real
  regression from the measured behavior above — file it, don't assume it was a fluke.

## 4. First run, the way your friend will do it

- [ ] **Settings page**: enter a real OneLogin username and password, pick a real printer
  from the dropdown (not "System default", so you know exactly which one is being used),
  leave the rest at their defaults, and **Save**.
- [ ] **Settings → Test login**. **Expect:** it takes up to a minute, shows progress as it
  runs, and both lines end in **OK**. If either doesn't, fix the credentials, Save, and
  try again before moving on — nothing past this point works without a real login.
- [ ] **Dashboard → Refresh now**. **Expect:** it pulls Canvas and HAC and the dashboard
  fills in with each kid's open work.
- [ ] **Dashboard → Preview today's sheet**. **Expect:** a PDF opens/downloads and looks
  like a real sheet (kids' names, assignments, due dates).
- [ ] **Dashboard → Print now**, aimed at the real printer you chose in Settings.
  **Expect:** the sheet comes out of that printer. If the printer supports duplex, it
  should print **two-sided**; if it doesn't, separate single-sided pages are correct.
  (CI's smoke test proves the print pipeline runs without crashing against whatever
  printer happens to be configured on a fresh CI runner — it does not, and cannot, prove
  that a real print job lands correctly on your real printer. This is that proof.)

## 5. A schedule, end to end

`smoke.ps1` does round-trip `schedule install` / `schedule remove --all` through a real
`schtasks` on the CI runner — but from the **command line**, and it never waits for
anything to fire. Section 0b has since covered the first of the two gaps: the **Schedules
page writing a task** (the web app's own path into `schtasks`, which the suite always runs
against an injected fake) was driven end to end on graphy and the task came out right.

What is still untested anywhere is a **scheduled run actually firing** at its trigger time
and printing — which needs credentials, a printer and the patience to wait. That is why
this section asks you to sit and wait. Note that the scheduler write is gated on
`login-ok.txt`: until **Test login** has succeeded once, saving a schedule stores your
settings and tells you plainly that nothing is installed yet. That is by design, so do
section 4 first.

- [ ] On the **Schedules** page, find the report you want to test (Open Work Sheet is
  fine), tick **"Run this on a schedule"**, set the time to a few minutes from now, tick
  today's day of the week, tick **"Print it"**, and click that section's **Save**.
- [ ] Open **Task Scheduler** again. **Expect:** a task named **"Fridge Sheet -
  open-work"** (or **"Fridge Sheet - view N"** if you scheduled a saved report instead)
  now exists, with a trigger matching the time you set.
- [ ] **Stay logged in** (a locked screen is fine) until that time passes. Don't touch
  Print now or Preview for this report in the meantime — you want to see the scheduled
  run happen on its own.
- [ ] **Expect:** the sheet prints on the real printer at the time you set, and a Windows
  notification appears saying it printed (or, if something legitimately went wrong,
  saying why).
- [ ] Open the **Runs** page. **Expect:** a new row for that report with a timestamp
  matching when it fired. Its **How** column will read **"cli"** — that's correct, not a
  bug: a scheduled run is Task Scheduler literally invoking `FridgeSheet.exe run
  <key>`, the same command line as running it from a terminal, so there is no separate
  "scheduled" trigger value to look for. **Outcome** should be **OK**, and the PDF link
  should open the same sheet that came out of the printer.

  If instead the row says **SKIP** and today is listed in `no-print-days.txt` (edit it from
  the Settings page), that's the seeded district calendar blocking it, not a bug — pick a
  day that isn't listed, or a different report, and repeat this section.

## 6. The phone

⚠️ **Windows Firewall will block this and say nothing.** Ticking "Allow other devices"
makes the app bind `0.0.0.0`, and the Settings page will duly show a LAN URL and a QR
code — but nothing shipped adds a firewall rule for port 8433, and Windows' default
inbound action is block on every profile. The phone just spins. Worse, a check run **on
the PC itself** passes (`http://192.168.x.x:8433/` answers fine locally), so it is easy to
believe this works when it does not — that is exactly the mistake made on graphy on
2026-09-17. **Test from another device, always.**

The rule an administrator needs to add once, scoped to the house network rather than
opened to whatever Wi-Fi the machine joins:

```powershell
New-NetFirewallRule -DisplayName 'Fridge Sheet (TCP 8433)' -Direction Inbound `
  -Action Allow -Protocol TCP -LocalPort 8433 -Profile Any -RemoteAddress LocalSubnet
```

`-RemoteAddress LocalSubnet` matters: a desktop's Wi-Fi is often categorised **Public**
(graphy's is), and scoping by subnet keeps the port reachable at home without opening it
on the Public profile generally. See #38.

- [ ] On **Settings**, tick **"Allow other devices on this network"** and **Save**.
  **Expect:** a message that the server address changed.
- [ ] Sign out and back in (or restart the PC) so the logon task picks up the new bind
  address, per the message.
- [ ] Back on **Settings**, **expect:** a LAN URL now shown (something like
  `http://192.168.x.x:8433/`) with a QR code next to it.
- [ ] Using your phone's **ordinary camera app** — not a dedicated QR scanner, since
  that's not what a parent will reach for — point it at the QR code on the monitor.
  **Expect:** the phone recognizes it and offers to open the link; tapping it loads Lakota
  Sheet's dashboard in the phone's browser. (This QR code has only ever been verified by
  decoding a rendered SVG in software; this is the first time an actual camera, at an
  actual angle, under actual lighting, has ever pointed at it. If it doesn't scan cleanly,
  that's a real finding — say what lighting/angle/distance you tried.)
- [ ] On the phone, go to **Settings**. **Expect:** the **password** field is there and
  usable, with a note saying the password crosses your network in the clear because this
  page has no HTTPS. (This used to be refused unless you were on the PC itself. That rule
  was dropped: it is unsatisfiable on a headless host, where the account running the
  server has no desktop and so no browser that could ever be loopback, and it protected
  little — any device that can reach this page could already read the kids' grades and the
  OneLogin username.)
- [ ] Type the real password there and **Save**. **Expect:** "Password stored", and
  **Test login** then passes from the phone.
- [ ] Reload **Settings** on the phone and look at the password box. **Expect:** it is
  **empty**, with the placeholder "leave blank to keep the stored one" — setting the
  password from another device is allowed; reading it back never is. If the stored
  password ever appears prefilled in that box, stop: that is a real finding.
- [ ] Change something harmless (e.g. "days ahead") and Save with the password box left
  blank. **Expect:** it succeeds and the stored password still works — a blank box keeps
  what is stored rather than wiping it.

## 7. Uninstall

The uninstall side has the same locked-file hazard as section 3's upgrade, and the same
"written here, never run on Windows" caveat. `[UninstallRun]`'s `service remove` ends the
logon task, but a copy **you** started from the desktop shortcut is not that task's child
and outlives it — with its Chromium and SumatraPDF children — while Inno tries to delete
`{app}` from under it. `installer.iss` now stops the app in `CurUninstallStepChanged`'s
`usUninstall` step (the same `schtasks /End` + `taskkill /T /F` + `Sleep` as
`PrepareToInstall`), which runs before `[UninstallRun]` and before any file is removed.
**That has now been run on real Windows against a hand-started but idle server, and it
worked** (section 0b). What is left for you is the same gap as section 3's: doing it with
a Refresh actually in flight, so `/T` has children to take down. So:

- [ ] **Before uninstalling, start a copy from the desktop shortcut** and leave its
  browser tab open — that is the case `service remove` alone does not cover. If you have
  time, start a **Refresh now** as well and uninstall while it is still running, so
  Chromium is live under `{app}\ms-playwright\`.
- [ ] **Settings (Windows) → Apps → Fridge Sheet → Uninstall.**
- [ ] **Expect:** no "files in use"/"could not be removed" dialog, and no leftover
  `%LOCALAPPDATA%\Programs\Fridge Sheet` folder afterwards. If either appears, the
  `usUninstall` stop did not do its job — a real finding, and the manual workaround is the
  same as section 1's: End the task in Task Scheduler, confirm no `FridgeSheet.exe` is left
  in Task Manager, then uninstall again.
- [ ] Open **Task Manager** after the uninstall finishes. **Expect:** no `FridgeSheet.exe`,
  no `SumatraPDF.exe`, and no `chrome.exe` left behind from the copy you started.
- [ ] **Expect:** a message box on completion naming `fridgesheet.db`, the
  `%LOCALAPPDATA%\fridgesheet` folder, and Windows Credential Manager's **"fridgesheet"**
  entry as what was kept.
- [ ] **Eyeball Task Scheduler yourself — do not trust a silent uninstall.** The
  uninstaller's `[UninstallRun]` entry runs `schedule remove --all` as `runhidden`, and
  Inno Setup does not check a `[UninstallRun]` entry's exit code — so if `schedule remove
  --all` fails partway through (leaves a task behind), nothing on screen will tell you.
  Open Task Scheduler and look through the **whole** list yourself for anything starting
  with "Fridge Sheet - " (the built-in report, any custom reports you scheduled in section
  5, and the logon task). **Expect:** none remain. If one does, that's a real finding, not a
  false alarm — file it.
- [ ] Confirm `%LOCALAPPDATA%\fridgesheet` still exists with your sheets, `fridgesheet.db`,
  `config.toml`, and logs intact.
- [ ] Open Windows Credential Manager and confirm the **"fridgesheet"** entry is still
  there (delete it yourself now if you're done testing, or leave it for next time).

## 7b. The rename: upgrading a Lakota Sheet install (0.4.0 only)

0.4.0 is the first release under the new name, with a new Inno AppId. On a machine that has
Lakota Sheet 0.3.x (`graphy`, as of 2026-09-18), the FridgeSheet installer's `[Code]` finds
the old app by its old AppId and runs its uninstaller silently before installing; the app's
first start then moves `%LOCALAPPDATA%\lakota-grades` to `%LOCALAPPDATA%\fridgesheet`,
renames `lakota.db`, and copies the Credential Manager entry (`fridgesheet\migrate.py`).

- [ ] Before: note the counts on Diagnostics (refreshes, items, active flags) and the number
  of runs on Runs.
- [ ] Run `FridgeSheet-Setup-0.4.0.exe` as the same user. **Expect:** Settings → Apps lists
  Fridge Sheet only; no Lakota Sheet entry; `%LOCALAPPDATA%\Programs\Lakota Sheet` gone.
- [ ] Start the app. **Expect:** `%LOCALAPPDATA%\fridgesheet` exists with `fridgesheet.db`,
  `%LOCALAPPDATA%\lakota-grades` is gone, Diagnostics shows the same counts as before, the
  Runs page has the same history, and `doctor.txt`'s "old names" line reads `none`.
- [ ] Settings → Test login passes without re-entering the password (the entry was copied).
- [ ] **The admin-registered task.** Where "Lakota Sheet - web" was registered by an
  administrator with a stored password (§0b), the old uninstaller cannot remove it and the
  standard-user install cannot register "Fridge Sheet - web" (#10). As the administrator:
  `schtasks /End /TN "Lakota Sheet - web"`, `schtasks /Delete /TN "Lakota Sheet - web" /F`,
  then register "Fridge Sheet - web" exactly as §0b describes, pointing at
  `%LOCALAPPDATA%\Programs\Fridge Sheet\FridgeSheet.exe web --no-browser`.
- [ ] From another machine: `/health` answers `"app":"fridgesheet"`, version 0.4.0, and the
  header shows the fridge-magnet mark.

## 8. Only now, the tag

Everything above passed. This step is yours — an agent does not run it and this checklist
does not authorize one to.

```
git tag v<version-in-pyproject.toml>
git push origin v<version-in-pyproject.toml>
```

For example, if `pyproject.toml` currently says `version = "0.2.0"`, that's
`git tag v0.2.0 && git push origin v0.2.0`. (As of this checklist being written, this repo
has no tags at all yet — this will be the first one.) `release.yml` refuses to build
anything for a tag that doesn't match `pyproject.toml` exactly, so get the version bumped
and merged to `main` first if it isn't already (see "Releasing the Windows installer" in
`README.md`).

**Pushing the tag is the maintainer's call, on his own schedule — not something this
document, or any agent, decides for him.**
