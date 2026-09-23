# In-app "update to the latest" (design)

`fridgesheet/web/updates.py` has, since it was written, ended its docstring with a refusal:

> A one-click upgrade -- the app fetching and running an installer on itself -- is a
> different level of trust and is deliberately not here yet.

This is the design that closes that gap, and the reason the refusal stood is the thing the
design has to answer for: the app would be downloading an unsigned executable and running it
on a family PC, then killing itself so that executable can replace it.

Today a new release reaches a household only if someone downloads
`FridgeSheet-Setup-<version>.exe` from GitHub and runs it. On `graphy` that is done over SSH.
In another parent's house it is not done at all, because nobody there knows it is possible.
`README.md`'s "Other parents can install it" is the goal this serves: a household that cannot
run a command line still gets fixes.

## 1. Who it is for, and what follows from that

Both audiences, one mechanism:

- **Another parent's household.** Windows app, no SSH, no way to diagnose a failed upgrade.
  They are the reason every failure path below ends somewhere a person can act on rather
  than in a log nobody will read.
- **This household, on `graphy`.** Saves the SSH-and-installer dance. Because a shell on the
  box already owns the box, the CLI path is deliberately *not* gated on the PIN in §3 --
  asking for a PIN from a shell that could delete the app outright is theatre.

Serving both at once means the higher bar wins everywhere. The engine is a CLI subcommand;
the web button is one caller of it. One implementation, two front doors -- the same rule the
rest of this codebase applies to phrase tables and status words.

**Windows only.** `graphy` is Windows and other parents install the Windows app; a Linux
install is a git checkout and updates with `git pull`, which no button can improve. The Linux
variant of the module exists and refuses, in one sentence that names the checkout path,
rather than being absent and raising `AttributeError` somewhere less helpful.

## 2. Shape

A new platform-split module beside the ones that already exist for services, printing,
scheduling, credentials and notifications:

```
fridgesheet/host/selfupdate.py          # the interface, and the platform pick
fridgesheet/host/selfupdate_windows.py  # download, verify, hand off
fridgesheet/host/selfupdate_linux.py    # refuses, and says why
```

`fridgesheet/web/updates.py` keeps the job it has -- *noticing* -- and gains one field.
Nothing about checking moves. The split is deliberate: noticing is a read of a public API and
is safe to do on a timer; doing is code execution and is not.

| Piece | Responsibility |
|---|---|
| `updates.py` | Is there a newer release? (unchanged, plus the asset digest) |
| `host/selfupdate*` | Download it, prove it is what GitHub said, hand off to it |
| `cli.py` | `fridgesheet self-update` -- the engine, for a shell |
| web route | The same engine, behind the PIN, with progress in the page |

## 3. The gate

The web app has **no authentication of any kind**, and `[web] allow_lan` binds `0.0.0.0`, so
every device on the house network reaches every route. `docs/release-checklist.md` already
says so for reading: *"any device that can reach this page could already read the kids' grades
and the OneLogin username."* Reading is not this. An unauthenticated button that executes a
downloaded binary is a different object, and a house network has children on it.

**An update PIN**, set on Settings, required by the web route.

- Stored as `pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>` in `config.toml` under
  `[web] update_pin_hash`. `hashlib.pbkdf2_hmac` is stdlib; no new dependency, and the
  plaintext is never written anywhere.
- **Write-only**, exactly as the OneLogin password field already is: it can be set from a
  phone, and it never reads back. A hash that renders into a form field is a hash that has
  been given away.
- Compared with `hmac.compare_digest`. Five wrong attempts lock the route for fifteen
  minutes, counted in `state.extra` -- in memory, so a restart clears it, which is acceptable
  because a restart is not something an attacker without the PIN can cause.
- **With no PIN set there is no button.** Settings says to set one first. The failure mode of
  a default PIN is worse than the failure mode of no feature.

What the PIN does not do, stated plainly so nobody later mistakes it for more: the page has no
HTTPS, so the PIN crosses the LAN in the clear and is visible to anyone already positioned to
watch that traffic; and it can be shoulder-surfed by a child standing behind a parent. It
raises the bar from "any device on the wifi" to "a device that has seen the PIN". That was a
considered trade -- the alternative considered and rejected was restricting the button to
loopback, which is stronger but stops a parent updating from the phone in their hand.

The **CLI takes no PIN**, per §1.

## 4. Verifying what was downloaded

The release API returns a digest for each asset, on a different host from the one that serves
the file:

```
api.github.com                 -> "digest": "sha256:b99a9645...b7def"   (TLS)
objects.githubusercontent.com  -> FridgeSheet-Setup-0.4.1.exe           (286 MB)
```

The flow is: read the release JSON, stream the asset while hashing it, compare, and **refuse
to execute on any mismatch** -- delete the file and say so. This catches a truncated download,
a corrupted one, and tampering anywhere below the API response.

It does not defend against a compromised GitHub account publishing a malicious release; that
release would carry a matching digest. That is the same trust anchor the manual download has
today, so the feature is no worse than what it replaces -- but it is not better, and the
spec says so rather than implying the hash proves authorship. Code-signing the installer
would raise that bar (and kill the SmartScreen warning every household currently clicks
through); it costs money and is out of scope here.

Practical consequences of a 286 MB asset:

- **Check free space before starting.** Roughly twice the asset size: the installer on disk
  plus the install it performs. Refuse early and legibly rather than filling the disk.
- **Stream in chunks, hashing as we go.** Never hold the file in memory.
- **The download is slow.** Progress goes through the job machinery that already streams
  Refresh, Preview and Print into the page -- not a second progress mechanism.

## 5. Surviving your own upgrade

`packaging/windows/installer.iss:117`, inside `PrepareToInstall`, before `[Files]` copies
anything:

```
Exec('taskkill.exe', '/IM FridgeSheet.exe /T /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
```

**The `/T` kills the process tree.** An installer launched as an ordinary child of
`FridgeSheet.exe` is inside that tree, so the installer would kill itself before copying a
file. This is the single fact that shapes the handoff, and it is not visible from the Python
side at all.

> **Corrected 2026-09-23.** This design originally assumed the installer could be spawned
> **detached** -- `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` -- and that this would keep
> it outside `FridgeSheet.exe`'s process tree. **That assumption was tested on real Windows
> and disproved.** Measured on `windows-latest`, 2026-09-23 (GitHub Actions runs
> 35844316753 and 35844539925, workflow `probe-detachment.yml`, branch
> `probe/windows-detachment`): an installer spawned with those flags was killed by
> `taskkill /T` exactly like an unflagged control process spawned alongside it -- both were
> confirmed recorded descendants of the parent (`InheritedFromUniqueProcessId` walked back
> to it), and both died. The flags concern the console and Ctrl+C routing; neither is
> documented to change `InheritedFromUniqueProcessId`, which is the field `taskkill /T`
> actually walks, and the only documented way to make a child *not* inherit that value is
> `PROC_THREAD_ATTRIBUTE_PARENT_PROCESS`, unreachable from `subprocess`. What DID survive,
> in the same experiment, was `cmd /c start "" /b <installer> ...` -- not because it
> reparents anything, but because cmd.exe exits immediately after launching the installer,
> breaking the recorded parent/child chain before `taskkill /T` ever snapshots it. The
> mechanism below reflects that correction; see
> `fridgesheet/host/selfupdate_windows.py`'s module docstring for the full measurement.

So the installer is spawned via **`cmd /c start "" /b <installer> ...`**, and the app then
returns and waits to be killed. The empty `""` immediately after `start` is the window
title argument and is load-bearing: `start` reads a lone quoted argument as a title, so
without it, a path containing a space (e.g. `C:\Users\John Smith\...\Setup.exe`) opens a
titled window and runs nothing instead of installing. `/b` means no new console window for
the installer; the `Popen` call itself also carries `creationflags=CREATE_NO_WINDOW` so
cmd.exe does not flash a console under the frozen, windowless app. `Popen`'s returned pid is
cmd.exe's, not the installer's -- nothing relies on it.

```
POST /update  {pin}
  |
  +- PIN wrong or locked       -> 403, attempt counted
  +- no newer release          -> 409, nothing to do
  +- not Windows               -> 409, the git-checkout sentence
  |
  +- ok:
       1. free space >= 2x asset size          else fail, named
       2. GET release JSON (TLS)               -> asset url + sha256
       3. stream download, hashing             -> %LOCALAPPDATA%\fridgesheet\updates\
       4. digest match?                        else delete, fail loudly
       5. write update-pending.json
       6. spawn: cmd /c start "" /b
            FridgeSheet-Setup-X.Y.Z.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=<path>
       7. return; the page begins polling /health
  |
  (the installer kills this process)
  |
installer: PrepareToInstall ends the logon task, kills the app,
           [InstallDelete] clears old dist-info, [Files] copies,
           [Run] "service install" re-registers AND restarts
  |
new version starts -> reads update-pending.json -> reports the outcome
```

Two things about `[Run]` that make this work, both verified in `installer.iss` rather than
assumed:

- `service install` carries **no `skipifsilent`**, so it runs under `/VERYSILENT`; and
  `host/service_windows.install` ends with `schtasks /Run /TN "Fridge Sheet - web"` -- *"start
  it now; the trigger covers the next logon"*. A silent install therefore re-registers the
  task **and restarts the server**. No installer change is needed.
- The "Open Fridge Sheet" entry **does** carry `skipifsilent`, so no browser window ambushes
  the family mid-update. That is the behaviour we want, not a gap.

`[InstallDelete]` already clears `{app}\_internal\fridgesheet-*.dist-info` before `[Files]`,
which is what stops the upgraded app reporting its old version -- the bug seen live on
2026-09-18 when 0.3.0 kept calling itself 0.2.0. Self-update depends on that fix being
correct, because the version the new process reports is how the breadcrumb below decides
whether the upgrade worked.

## 6. When it goes wrong

The app cannot supervise its own replacement -- that is the accepted cost of the detached
handoff in §5. Three things carry the outcome across the gap instead.

**The page.** The polling is client-side and already loaded in the browser, so it outlives the
server that sent it. It polls `/health` for the new version. If that does not arrive within
the timeout it stops guessing and says to open Fridge Sheet from the desktop shortcut --
which works, because a no-args launch finds a running server or starts one
(`fridgesheet/web/__main__.py`'s `launch()`).

**The breadcrumb.** `%LOCALAPPDATA%\fridgesheet\update-pending.json` holds the from-version,
the to-version, when it started, and the paths of the installer and its log. On start the app
reads it:

| Breadcrumb says | Running version | Conclusion |
|---|---|---|
| 0.4.1 -> 0.5.0 | 0.5.0 | Worked. Archive it, report it once on Settings. |
| 0.4.1 -> 0.5.0 | 0.4.1 | Did not take. Keep it, warn on Diagnostics, name the log. |
| (absent) | anything | Normal start. |

**The installer itself is kept.** A parent who ends up stuck has a file on disk to
double-click, and the wizard they would have used anyway.

### The failure this feature makes worse

**Issue #39.** For a genuine standard (non-administrator) user, `schtasks /Create` fails with
`ERROR: Access is denied`, and Inno does not check a `[Run]` entry's exit code, so the wizard
still reports success. Today that household still has a desktop shortcut and a wizard they
watched run. After a *silent* self-update they would have a dead app, no window, and no idea
why -- the same defect with every affordance removed.

This design does not fix #39. It must not pretend the risk is unchanged either:

- The Settings page refuses to offer the button when the logon task is absent, and says so.
  `host/service.describe_service()` already answers that: `ServiceInfo.installed` and
  `.active`. This is the difference between "we shipped #39 into a silent path" and "we
  declined to start an update we can predict will strand you".
- The page's timeout message (above) is the second net, for the case the check passes and the
  re-registration fails anyway.

### Accounts: the CLI's own footgun

`ServiceInfo` carries `managed_by`, `installed`, `active` and `detail` -- **not the task's
owner**. It needs one, and `service_windows` already has the data: it runs
`schtasks /Query /TN "Fridge Sheet - web" /FO LIST /V` and parses only `Status` out of a
response that also contains `Run As User`. Adding an `owner` field is a new parse of an
existing call, not a new call.

It is needed because a per-user logon task only fires for its owner, and a per-user install
lives in that user's profile. Observed on `graphy`, 2026-09-22:

```
Run As User:  lakotarunner
Task To Run:  C:\Users\lakotarunner\AppData\Local\Programs\Fridge Sheet\FridgeSheet.exe web --no-browser
```

The task runs as `lakotarunner`; an SSH session to that machine arrives as `graphy\tony`.
(`docs/release-checklist.md` §0b still says the install is under `tony` and the console user
is `gdrunner`; both are stale and should be corrected there.)

So the two front doors differ, and the difference bites in only one of them:

- **The web button** already runs as the account serving the page -- the task's owner -- so it
  upgrades the install that is actually running. Nothing to decide.
- **The CLI over SSH** runs as whoever logged in. Run as `tony` against a `lakotarunner`
  install, a per-user installer would cheerfully create a *second* copy under
  `C:\Users\tony\...` and leave the running server untouched. The command would report
  success and change nothing anyone can see -- the worst possible failure, because it is
  silent.

**`fridgesheet self-update` therefore refuses when the current user is not the logon task's
owner**, naming both accounts and telling the operator to run it as the owner. `--force`
overrides for the case where there is deliberately no task. A refusal that names the two
accounts is the whole fix; guessing the owner's profile and installing into it is not, because
a per-user Inno install run by the wrong user cannot write there anyway.

**A bug in the updater cannot be fixed by the updater.** Whatever ships first is what every
household runs until someone installs a build by hand. This is the strongest argument for
keeping the mechanism small and for §8's test coverage.

## 7. Testing

What the suite can prove on a runner with no installer to run:

- A digest mismatch refuses and deletes; a truncated download refuses; a missing `digest`
  field refuses rather than silently skipping verification.
- Free-space refusal fires before any network call.
- PIN: set, verify, wrong, lockout after five, lockout expiry; a set PIN never appears in any
  rendered page or in `config.toml` as plaintext.
- The route: no PIN configured -> no button; wrong PIN -> 403 and counted; not Windows -> the
  refusal sentence; no update available -> 409.
- Breadcrumb: both rows of §6's table, plus a malformed file (treated as absent, never fatal).
- `selfupdate_linux` refuses with the checkout sentence.
- `ServiceInfo.owner` is parsed from a real `schtasks /Query /V` response (a captured one), and
  is empty rather than wrong when the field is absent.
- The CLI refuses when the current user is not the task's owner, and the message names both
  accounts; `--force` proceeds; no task installed plus no `--force` refuses too.
- Settings offers no button when `describe_service()` reports the task absent.
- The spawn is called with detached creation flags -- asserted against an injected fake, which
  is the only place a test can see it.

What only a Windows runner can prove, in `packaging/windows/smoke.ps1`: that the detached
spawn actually escapes `taskkill /T`. This is the one claim in §5 that unit tests cannot
reach, and it is the claim the whole design rests on.

What only a human on a real machine can prove, and so belongs in
`docs/release-checklist.md` rather than here: a real self-update, over a real running app,
on a real household PC -- including once with a Refresh in flight, per the existing §3.

`security-self-review` applies before merge: this change touches authorization, a stored
secret, and code execution, on a child-facing surface.

## 8. Out of scope

- **Automatic updates.** This is a button and a command, never a timer. A household that has
  not asked does not get a 286 MB download and a restart mid-homework.
- **Code signing.** It would remove the SmartScreen warning and raise the trust anchor above
  "GitHub account". Worth doing; a separate piece of work with a cost attached.
- **Rollback.** Inno copies over the old bundle and keeps no copy of it. Recovery is the
  retained installer for the *new* version, or a hand-installed old one. A real rollback means
  keeping a second 286 MB bundle on disk, which is its own design.
- **Linux self-update.** §1.
- **Updating anything but the app.** Not the database, not `config.toml`, not the credential
  store; the existing migration path in `fridgesheet/migrate.py` owns that.
