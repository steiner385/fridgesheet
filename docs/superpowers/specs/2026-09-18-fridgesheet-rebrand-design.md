# Fridge Sheet: the rebrand (design)

Date: 2026-09-18. Decided by the maintainer ("rename everything across the board in the
app. this is a complete re-brand"). Repository already moved to
`github.com/steiner385/fridgesheet` with a fresh history the same day.

## 1. What the name is

- **Fridge Sheet** in prose and in the UI; **FridgeSheet** in file names (installer, exe,
  PyInstaller spec); **fridgesheet** for everything a machine reads: the Python package
  and distribution, the CLI command, the keyring service, the MCP server name, the data
  directory, the env-var prefix (`FRIDGESHEET_*`).
- "Lakota" survives only as the district defaults (`hac_base`, `onelogin_host`) and in
  the docs sentence that says those are defaults for one district and can be changed.
- Version becomes **0.4.0**: the first release under the new name.

## 2. Identity anchors that change (and what a running install sees)

| Anchor | Old | New |
|---|---|---|
| Package / dist / CLI | `lakota_grades` / `lakota-grades-mcp` / `lakota-grades` | `fridgesheet` / `fridgesheet` / `fridgesheet` |
| Data directory | `~/.lakota-grades`, `%LOCALAPPDATA%\lakota-grades` | `~/.fridgesheet`, `%LOCALAPPDATA%\fridgesheet` |
| Home override env | `LAKOTA_GRADES_HOME` | `FRIDGESHEET_HOME` |
| Env prefix | `LAKOTA_*` | `FRIDGESHEET_*` |
| Keyring service | `lakota-grades` | `fridgesheet` |
| Scheduled task / unit prefix | `Lakota Sheet - …` / `lakota-grades-…` | `Fridge Sheet - …` / `fridgesheet-…` |
| Inno AppId | `{B7E1C0E2-…}` | a new GUID |
| Install dir / exe / installer | `Programs\Lakota Sheet`, `LakotaSheet.exe`, `LakotaSheet-Setup-x.exe` | `Programs\Fridge Sheet`, `FridgeSheet.exe`, `FridgeSheet-Setup-x.exe` |
| Health `app` field | `lakota-grades` | `fridgesheet` |

## 3. Migration: automatic, once, on first start

`fridgesheet.migrate.run()` is called before anything opens the database, from the CLI
entry point and the web server start.

- **Home directory.** If the new home does not exist and the old one does: move it
  (`os.replace`, same filesystem). On Linux, leave a symlink at the old path pointing at
  the new one, because the maintainer's hand-written systemd units and Drive paths name
  `~/.lakota-grades/...` explicitly. On Windows nothing else names the directory, so no
  link. If both exist, do nothing and say so in `doctor`.
- **Credentials.** If the new keyring service has no password for the configured username
  and the old service does, copy it. The old entry is left alone (the old app may still be
  installed elsewhere).
- **Env vars.** At startup, every `LAKOTA_<X>` in the environment (and every one read from
  the `.env` file) also sets `FRIDGESHEET_<X>` when that is unset; `LAKOTA_GRADES_HOME`
  maps to `FRIDGESHEET_HOME`. Code reads only the new names.
- **Windows installer.** `[Code]` in `installer.iss` looks up the old AppId's uninstall
  key under HKCU and runs that uninstaller with `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`
  before installing. The old uninstaller keeps the data directory; the app then moves it.
  `[InstallDelete]` covers both `lakota_grades_mcp-*.dist-info` and
  `fridgesheet-*.dist-info`.
- **Scheduled task on Windows.** The app registers `Fridge Sheet - web` where it can. On
  graphy the old task was admin-registered and is removed and re-registered by hand
  (release checklist).

## 4. Shims kept for one release

- A `lakota-grades` console script that prints one line to stderr ("lakota-grades is now
  fridgesheet") and delegates to the same `main`.
- `LAKOTA_*` env vars honored through the aliasing above.
- `scripts/lakota-sheet-desktop.sh` kept as a two-line wrapper around
  `scripts/fridgesheet-desktop.sh`.
- `doctor` lists each shim in use under "Old names still in use", so they can be retired
  in the release after.

## 5. The mark

A sheet of paper held to a fridge by one round magnet: a white rounded rectangle with two
faint rule lines, a coral magnet dot near the top, on a slate background. Source of truth
is `fridgesheet/web/static/mark.svg`; `favicon.svg` is the same drawing. Rendered
artefacts committed alongside (`packaging/windows/FridgeSheet.ico`, PNGs at 32/64/256)
by `scripts/render_mark.py` (rsvg-convert + Pillow on the maintainer's machine; CI does not
render). The web header shows the mark next to the wordmark "Fridge Sheet".

## 6. Testing

- Unit tests for `migrate`: home move (new absent / old absent / both present), symlink on
  Linux only, keyring copy, env aliasing precedence (new name wins).
- Packaging tests updated for every renamed anchor; a test that the installer's `[Code]`
  references the old AppId and the silent flags; a test that no source or doc file outside
  this spec and the district defaults still contains `lakota` (case-insensitive), with an
  allowlist.
- Full suite green; Windows CI green; release build green; graphy upgrade verified from
  dobby with the same run history and flags as before.

## 7. Out of scope

- Retiring the shims (next release).
- Renaming the maintainer's own systemd units, desktop shortcuts, or clone directory on
  dobby; they keep working through the shims and the symlink.
