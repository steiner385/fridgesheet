# lakota-grades-mcp

A local MCP server that gives Claude clean JSON from **Canvas** (assignments, due dates, missing/late flags) and **Home Access Center** (official grades) for all three kids, so the weekly check-in reports can be built without driving Chrome.

Design goals:

- **Claude never sees a password.** Logins happen inside this server's process. Credentials come from 1Password at the moment they're typed and are not written anywhere.
- **Log in rarely.** One persistent Chromium profile holds the OneLogin, Canvas and HAC cookies; a login only happens when a site bounces us to a login page.
- **One pull, many tools.** A refresh writes a JSON snapshot; the tools read from it (cache TTL 3 h by default), so Thursday's report doesn't hit the sites more than once.

## 1. Install (Linux)

```bash
git clone <this folder> ~/lakota-grades-mcp   # or just copy it
cd ~/lakota-grades-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium
```

## 2. Credentials via 1Password

You have two good options. Both keep the password out of Claude, out of the repo, and off disk.

### Option A — 1Password Environments (uses the official 1Password MCP)

1. In the 1Password desktop app: **Settings → Labs → Enable local MCP server**, and **Settings → Developer → Integrate with MCP clients** (you already have this one on).
2. Add the official server to Claude Desktop (see step 4). Then, in Claude, ask it to create an Environment named `lakota-grades` with two variables, `LAKOTA_ONELOGIN_USERNAME` and `LAKOTA_ONELOGIN_PASSWORD`. Enter the values yourself in the 1Password app when it prompts — the 1Password MCP is built so the agent cannot read secret values back, which is exactly what we want.
3. Ask Claude (or do it in the app) to create a **locally mounted `.env`** for that Environment at `~/.lakota-grades/.env`. The file resolves secrets on demand through the desktop app; nothing plaintext lands on disk.
4. `lakota-grades` loads that file automatically (it also honors `LAKOTA_ENV_FILE=/path/to/.env`).

### Option B — `op` CLI secret references

If you'd rather point at an existing Login item:

```bash
export LAKOTA_OP_USERNAME_REF="op://Private/Lakota OneLogin/username"
export LAKOTA_OP_PASSWORD_REF="op://Private/Lakota OneLogin/password"
```

The server calls `op read` when a login is actually needed (desktop-app integration prompts to unlock if locked). For fully unattended runs, use a **1Password service account** instead: set `OP_SERVICE_ACCOUNT_TOKEN` in the systemd unit's environment from your OS keyring, scoped to a vault that holds only this item.

You can also run any command through 1Password without a mount: `op run --env-file=env.tpl -- lakota-grades refresh` where `env.tpl` contains `LAKOTA_ONELOGIN_USERNAME="op://..."` lines.

## 3. First login and check

```bash
lakota-grades login    # opens a visible browser; sign in to OneLogin once; Enter; Enter
lakota-grades check    # headless: "Canvas: OK", "HAC: OK"
lakota-grades refresh  # pulls all three kids into ~/.lakota-grades/cache/snapshot.json
```

`login` is optional — `check`/`refresh` will log in automatically using the credentials — but doing it once by hand is the easiest way to confirm the OneLogin form selectors work for your tenant. If OneLogin ever changes its form, override with `LAKOTA_ONELOGIN_USER_SELECTOR`, `LAKOTA_ONELOGIN_PASS_SELECTOR`.

## 4. Point Claude Desktop at it

Add both servers to `~/.config/Claude/claude_desktop_config.json` (see `claude_desktop_config.example.json`):

```json
{
  "mcpServers": {
    "1password": { "command": "1password-mcp" },
    "lakota-grades": {
      "command": "/home/tony/lakota-grades-mcp/.venv/bin/lakota-grades",
      "args": ["serve"],
      "env": { "LAKOTA_ENV_FILE": "/home/tony/.lakota-grades/.env" }
    }
  }
}
```

Restart Claude Desktop. In a linked Cowork session the tools appear as `lakota-grades: grades`, `missing_work`, `upcoming`, `assignments`, `hac_classwork`, `list_students`, `status`, `refresh`.

## 5. Pre-fetch on a schedule (optional, recommended)

So the noon Thursday task finds a fresh snapshot and doesn't wait on logins:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/lakota-grades-refresh.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now lakota-grades-refresh.timer
systemctl --user list-timers | grep lakota
```

Edit the `.service` file if your venv or env-file path differs.

## Tools

| Tool | Returns |
|---|---|
| `list_students()` | Kids on the account, Canvas IDs, which sources have data |
| `grades(student)` | Per class: HAC marking-period average (official), HAC last-updated, category subtotals, Canvas current/final, teacher/TA contacts |
| `missing_work(student)` | Missing, late, zero, past-due-unsubmitted (Canvas) + blank-score past-due rows (HAC); assessments first; total points at stake |
| `upcoming(student, days=7)` | Unsubmitted items due in the window, Eastern time |
| `assignments(student, course=None)` | Full Canvas assignment list with flags |
| `hac_classwork(student, course=None)` | Raw HAC rows and category subtotals |
| `status()` / `refresh(kids, hac, canvas)` | Snapshot age & source health / pull now |

All dates are `America/New_York` ISO strings (Canvas `due_at` is UTC and is converted).

## Notes and known quirks (Lakota, Sept 2026)

- Canvas API token generation is disabled for parent accounts, which is why this uses the browser session's cookies against the REST API instead.
- `/api/v1/users/<kid>/courses` returns 403 for observers; enrollments with `include[]=observed_users` is the working route.
- Algebra II's Canvas grade is hidden by the teacher; Band and parts of Latin/Biology are graded only in HAC. HAC is the gradebook of record.
- HAC Classwork renders inside an iframe; class blocks are `.AssignmentClass`, rows `tr.sg-asp-table-data-row`.
- Honors English 9 closes late work one week after the due date.

## Security notes

- The browser profile in `~/.lakota-grades/browser-profile` contains session cookies. Treat it like a password: `chmod 700 ~/.lakota-grades`.
- The snapshot JSON contains the kids' grades. Same treatment.
- Nothing here ever prints or logs a credential. `Settings.credentials()` is the only reader.
