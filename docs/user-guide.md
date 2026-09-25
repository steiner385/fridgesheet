# Fridge Sheet user guide

Fridge Sheet puts your kids' open schoolwork in one place: a sheet on the fridge each school
day, and a small web app on your own computer. It reads **Canvas** (where teachers post and
collect work) and **Home Access Center** — **HAC**, the official gradebook — with your
district OneLogin parent login. It decides, one rule at a time, what actually happened to
every assignment, and keeps the short list of what can still be fixed in front of you.

This guide covers everything a household does with it, in the order you will meet it.
It describes version 0.5. Where the app has a known rough edge, the guide says so and links
the issue.

- [1. What it is, in one page](#1-what-it-is-in-one-page)
- [2. Install](#2-install) — [Windows](#21-windows), [Linux](#22-linux), [headless server](#23-a-server-with-no-desktop-linux), [another district](#24-another-school-district)
- [3. First-time setup](#3-first-time-setup)
- [4. Finding your way around](#4-finding-your-way-around)
- [4a. Your routine, once it is set up](#4a-your-routine-once-it-is-set-up)
- [5. Today (the dashboard)](#5-today-the-dashboard)
- [6. A child's pages: Check-in, Plan, Assignments](#6-a-childs-pages-check-in-plan-assignments)
- [7. Open work and Questions](#7-open-work-and-questions)
- [8. Answering: flags, answers and notes](#8-answering-flags-answers-and-notes)
- [9. The printed sheet](#9-the-printed-sheet)
- [10. Schedules: printing and refreshing on their own](#10-schedules-printing-and-refreshing-on-their-own)
- [11. Reports](#11-reports)
- [12. Runs, Changes and Trends](#12-runs-changes-and-trends)
- [13. Settings](#13-settings)
- [14. How Fridge Sheet decides](#14-how-fridge-sheet-decides)
- [15. Children's reading levels](#15-childrens-reading-levels)
- [16. Using it on a phone or tablet](#16-using-it-on-a-phone-or-tablet)
- [17. The command line](#17-the-command-line)
- [18. Using it from Claude (MCP)](#18-using-it-from-claude-mcp)
- [19. Files, backup and privacy](#19-files-backup-and-privacy)
- [20. Troubleshooting](#20-troubleshooting)
- [21. Updating and uninstalling](#21-updating-and-uninstalling)
- [Glossary](#glossary)

---

## 1. What it is, in one page

**Who it is for.** Written for one parent at a computer, used by a household: parents and
caregivers who want to know what is open, and kids who sit down with a parent for a short
weekly check-in. There are no accounts or logins inside the app; anyone who can open it can
use every page.

**What it does**

1. **Refreshes.** Signs in to OneLogin with your parent login, reads every child on the
   account from Canvas and HAC, and saves what it found. A refresh takes 1–3 minutes.
2. **Decides.** Pairs each Canvas assignment with its HAC twin, and gives every assignment
   one *outcome* (on time, late, not done, done on paper, unknown, not due yet…) from one
   written set of rules ([§14](#14-how-fridge-sheet-decides)).
3. **Shows.** The web app: a Today page, each child's pages, the Open work list, the few
   Questions only you can answer, trends and history.
4. **Prints.** A one-section-per-child sheet of what is open, on the school days and at the
   time you choose.
5. **Remembers.** Your answers ("it was handed in on paper"), notes, and the plans you
   agree with each child. A refresh never overwrites them.

**What it never does.** It never sends anything about your children anywhere. It talks
only to OneLogin, Canvas and HAC, plus a once-a-day check with GitHub for a newer version,
which sends nothing and can be turned off. Your password is kept in your computer's own
credential store (Windows Credential Manager or the GNOME keyring), never in a file.

**What it needs**

- A district that uses Canvas and Home Access Center behind OneLogin. The addresses default
  to Lakota Local Schools; another district's go in the `.env` file ([§13](#13-settings)).
- A OneLogin **parent** account *without* multi-factor sign-in. If a code is sent to your
  phone each time you sign in, automatic refreshes cannot work.
- A computer that is on, and signed in, at the times you want it to print.
- That computer's clock set to your time zone — or your zone picked under **Settings →
  Where you are** ([§13](#13-settings)). Due times, "today" and schedules all follow it.

---

## 2. Install

### 2.1 Windows

1. Download `FridgeSheet-Setup-<version>.exe` from the
   [Releases page](https://github.com/steiner385/fridgesheet/releases).
2. Run it. Because the installer is not code-signed, **SmartScreen** says "Windows
   protected your PC": click **More info**, then **Run anyway**. If your antivirus
   quarantines it, restore it and add an exclusion.
3. No administrator password is needed; it installs for your Windows user only
   (`%LOCALAPPDATA%\Programs\Fridge Sheet`), about 900 MB with its own copy of Chromium.
4. It registers a task, **Fridge Sheet - web**, that starts the app quietly whenever you
   sign in, and opens the app when it finishes.

> A standard (non-administrator) Windows account sometimes cannot create that task; the
> installer then falls back to a Startup-folder shortcut, which does not restart the app if
> it stops. See issue #10.

The desktop shortcut opens `http://127.0.0.1:8433/` and starts the app first if it is not
already running.

### 2.2 Linux

```bash
git clone https://github.com/steiner385/fridgesheet ~/fridgesheet
cd ~/fridgesheet
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
playwright install chromium
```

You need Python 3.11+, `secret-tool` (libsecret) with a running GNOME keyring for the
password, and CUPS (`lp`) for printing. `notify-send` and `evince` are optional.

To keep the web app running in the background: `fridgesheet service install` (a systemd
user service). To run it by hand: `fridgesheet web` (add `--no-browser` on a machine
without a desktop). Either way it answers at `http://127.0.0.1:8433/`.

### 2.3 A server with no desktop (Linux)

Fridge Sheet runs fine on a home server, with three things to arrange:

1. **Chromium's libraries.** On a minimal install run `playwright install-deps chromium`
   (needs sudo) after `playwright install chromium`.
2. **The password.** The GNOME keyring unlocks only when someone signs in to the desktop,
   so on a server it stays locked: `secret-tool` waits 20 seconds and the refresh fails.
   Use one of the other sources ([§13](#where-the-password-can-come-from)) instead. Both
   end up as a line in `~/.fridgesheet/.env`, readable only by you:
   - `FRIDGESHEET_ONELOGIN_USERNAME=…` and `FRIDGESHEET_ONELOGIN_PASSWORD=…` — simplest;
     the password is in plain text in that file.
   - a 1Password **service account**: `FRIDGESHEET_OP_USERNAME_REF=op://…`,
     `FRIDGESHEET_OP_PASSWORD_REF=op://…`, and `OP_SERVICE_ACCOUNT_TOKEN=…` scoped to a
     vault holding only this item. (Plain `op` without a service account asks the 1Password
     desktop app to approve each login, which a timer can't do.)
3. **Timers while signed out:** `loginctl enable-linger "$USER"`.

**First setup without a browser on the server.** The Settings page only answers at
`127.0.0.1` until you allow other devices, and that switch is *on* the Settings page. Either:

- tunnel it from your laptop: `ssh -L 8433:127.0.0.1:8433 server`, then open
  `http://127.0.0.1:8433/` on the laptop; or
- put `[web]` / `allow_lan = true` in `~/.fridgesheet/config.toml` and restart the service.

When the login comes from `.env` this way, the School login card on Settings says so
(*Username and password are supplied by the environment*) and **Save** does not ask for a
password — changing the printer or the network settings needs nothing typed in those boxes.

### 2.4 Another school district

The defaults are Lakota Local Schools'. For another district:

| What | Where |
|---|---|
| Canvas, HAC and OneLogin addresses | `.env`: `FRIDGESHEET_CANVAS_BASE=https://…`, `FRIDGESHEET_HAC_BASE=https://…`, `FRIDGESHEET_ONELOGIN_HOST=…` |
| The HAC tile on your OneLogin portal, if it isn't called "Home Access" or "HAC" | `.env`: `FRIDGESHEET_HAC_APP_PATTERN=…` (a name to look for), or pin it with `FRIDGESHEET_HAC_ONELOGIN_APP_URL=…` |
| School holidays | **Settings → Days the sheet does not print** — replace Lakota's dates. |
| Quarter end dates | **Settings → Late-work rules → Quarters** — replace Lakota's dates. |
| Time zone | This computer's, unless **Settings → Where you are → Time zone** says otherwise (or `FRIDGESHEET_TIMEZONE=America/Chicago` in `.env`). Due times, "today", the print window and schedules follow it: a sheet you want at 2 pm is **14:00**, wherever you are. |

If **Test login** fails, run `fridgesheet login` on a machine with a screen: it opens a
visible browser so you can watch where sign-in stops. A district whose OneLogin form differs
can override `FRIDGESHEET_ONELOGIN_USER_SELECTOR`, `_PASS_SELECTOR` and `_SUBMIT_SELECTOR`.

---

## 3. First-time setup

Do these once, in this order. Each takes a minute or two.

| # | Where | What to do |
|---|---|---|
| 1 | **Settings → School login** | Enter your **OneLogin username** and **OneLogin password**. Click **Save** at the bottom of the form. |
| 2 | **Settings → Test login** | **Save first** — Test login uses what you *saved*, not what is typed in the boxes. Takes up to a minute; progress appears on the page. Both lines must say OK. Nothing can be scheduled until this has passed once. |
| 3 | **Today → Refresh now** | Until the first refresh, each child's card says *No refresh yet* (and mentions a terminal command — ignore it on Windows). The **Refresh now** button is in the *Today's sheet* card further down. Reload the page when the job says OK. |
| 4 | **Settings → Printing** | Pick the **Printer** (or leave *System default*), **Days ahead** (how far forward the sheet looks, default 14) and **Overdue days** (how far back, default 14). If the sheet should say "Al" rather than "Alexander", add a line `Alexander=Al` under **Nicknames** (one per line, first name as the school lists it). **Save**. |
| 5 | **Schedules → Refresh the data** | Tick **Refresh on a schedule**. The default (every 3 hours, 06:00–21:00, every day) is a good start. **Save**. *Do not skip this* — see the box below. |
| 6 | **Schedules → Open Work Sheet** | Tick **Run this on a schedule**, set **Time** — it is a 24-hour clock, so 3 pm is **15:00** — and the **Days**, tick **Print it** (untick to keep only a PDF), **Save**. The state line should now say *next run …*. |
| 7 | **Settings → Late-work rules** and **Days the sheet does not print** | Both come filled in with Lakota's 2026-27 dates. Check them against your school calendar and each class's late policy ([§13](#late-work-rules)). |
| 8 | *Optional:* reading levels | Tell the app each child's school grade so their pages read at their level. This one is not on Settings yet; see [§15](#15-childrens-reading-levels) for how to add it. |

> **Why step 5 matters.** A scheduled print does **not** refresh the data itself; it prints
> from whatever the last refresh left behind. If nothing has refreshed in 24 hours, the
> print refuses to run ("snapshot is stale … nothing printed"). The Refresh schedule is what
> keeps a scheduled sheet current. If you skip step 5, step 6 turns the refresh on for you
> with the defaults and says so; the Schedules page warns, and Diagnostics fails, whenever
> a report is scheduled and the refresh is off.

**Setting up from a terminal (Linux)** — the same steps without a browser:

```bash
fridgesheet set-credentials                 # step 1: asks for the password, never echoes it
fridgesheet check                           # step 2: "Canvas: OK", "HAC: OK" — counts as a passed Test login
fridgesheet refresh --record                # step 3: --record is what fills the web app; plain `refresh` doesn't
fridgesheet schedule install data-refresh   # step 5: every 3 hours, 06:00–21:00, every day, unless [refresh] in config.toml says otherwise
fridgesheet schedule install open-work      # step 6: 14:00 Mon–Fri, unless [reports.open-work] says otherwise
```

`check` counts as a passed **Test login**: it leaves the same `login-ok.txt` the button does,
so the Schedules page and `schedule install` go ahead afterwards. (`schedule install` refuses
until one of the two has passed; `--force` overrides that.) For a server with no desktop,
read [§2.3 Headless server](#23-a-server-with-no-desktop-linux) first.

---

## 4. Finding your way around

Every page has a **left rail**:

| Group | Links |
|---|---|
| (top) | **Today** — the dashboard. Then one link per child, with how many questions are waiting for them. A child's link opens their Check-in. |
| **Work** | **Open work**, **Questions** (total waiting), **Reports**, **Schedules** |
| **Time** | **Changes**, **Trends** |
| **App** | **Runs**, **Settings**, **Diagnostics** |

On the pages of a child whose grade is set ([§15](#15-childrens-reading-levels)), the rail
shrinks to **Today**, that child, and one folded **App** section holding everything else,
so a child sitting at the screen sees less.

The **status bar** at the top of every page says:

- **Refreshed** *time*, and **Canvas OK** / **HAC OK** — or the error from the last
  attempt. "No refresh yet" before the first one. When Canvas answered but refused one
  class, it reads **Canvas OK (1 class carried from** *time*: *kid's class (error)***)** —
  that class is shown from the pull named, and nothing has been lost.
- **Last run** with an OK/FAIL badge — the last sheet or report built or printed (links to
  Runs).
- A badge while a job (refresh, build, print) is running.
- **Fridge Sheet X is available** when a newer version exists.
- A warning if one of your settings files cannot be read.

**The "old data" banner (⚠).** When the last *good* refresh — both Canvas and HAC
answering — is 24 hours old or more, every page says so: how old, when the last good one
was, and why the latest failed. Its **Refresh now** link takes you to Today; press
**Refresh now** there to actually refresh. 24 hours is also the point at which a scheduled
print refuses to run, so the banner and a missing sheet always agree.

---

## 4a. Your routine, once it is set up

Most weeks you need four screens. Everything else is for setup or for digging in.

| When | Do | Time |
|---|---|---|
| **Each evening** (phone is fine) | **Today** — each child's *N questions to answer* and *N still fixable*. Tap a number to see the rows. | 2 min |
| **When a question appears** | **Questions** — pick an answer, or **Email with these facts** to the teacher. | 1 min each |
| **Once a week, with each child** | Child → **Check-in** — review together, plan a few steps, **Finish check-in**. **Print plan** for the fridge. | 15–20 min |
| **When the sheet didn't print** | **Runs** — the reason is on the row. | 1 min |

### The same thing, in different words

The app and this guide use a few words that overlap. They mean:

| You see | It means |
|---|---|
| **still fixable** (Today, Open work) | Not done or unknown, still inside its late-work window, not already answered. The short list for tonight. |
| **Open** (the Assignments filter) | Still fixable, *plus* what is coming due. |
| **Open work** (the page) | The printed sheet on a screen: still fixable, then coming due. |
| **Questions** (page, check-in group, Assignments section) | The same question cards everywhere: only what *you* can settle. |
| **Waiting** / **Waiting on the school** | Nothing to do yet; the app will ask you if it drags on. |
| **To do** (check-in) | Work the child could act on — a question isn't needed. |
| **handled** | Answered *It's done*, *Excused*, *Let it go* or *Too late to submit*. |
| **Let it go** → *let go* → *Let go* | One answer in three forms: the button you press, the state it leaves the item in (the row badge, the *Your answer* filter and line, Changes) and the confirmation. Every answer works this way: *Ask the teacher* → *asked the teacher* → *Asked the teacher*; *Follow up* → *following up* → *Following up*. The stored name (`ignore`) never appears on a page. |

---

## 5. Today (the dashboard)

"**What needs our attention?**" One card per child:

- **Start check-in · Open plan · Assignments** — the three ways into that child's pages.
- The check-in line: *Check-in due (planned for Thu 9/24)*, *Next check-in …*, or *No
  check-in yet*; and *N steps planned today · M min*.
- **N questions to answer** → the Questions page for that child, or *Nothing to answer*.
- **N still fixable** → that child on Open work.
- *N due today · N due tomorrow · N new since yesterday.*
- **School record so far** (folded): *N on time · N late · N not done · N on paper · N
  unknown · of N due so far.* Each number opens the Assignments tab filtered to those rows.
  What the words mean is in [§14](#the-outcomes).

**Today's sheet** card:

| Control | What it does |
|---|---|
| **Refresh now** | Pulls Canvas and HAC (1–3 minutes). |
| **Refresh data first** | A checkbox that applies only to the next two buttons. Unticked, they use the last refresh and take seconds. |
| **Preview today's sheet** | Builds today's PDF as a separate `sheet-preview.pdf` and links it. Prints nothing and leaves the printed sheet alone. |
| **Print now** | Asks, then prints today's sheet. |

Progress streams into a job card under the buttons; when it finishes you get OK/FAIL, a
message, and **open the PDF** where there is one. Only one job runs at a time. Reload the
page after a refresh to see new counts.

> Known rough edges: the Print now confirmation names the Settings printer even when the
> Open Work Sheet has its own printer on Schedules (the report's printer is the one used);
> if you click while another job is running you may see "The app could not do that (error
> 409)" instead of "Busy: … is still running" — it just means wait for the first job ([#127](https://github.com/steiner385/fridgesheet/issues/127), [#142](https://github.com/steiner385/fridgesheet/issues/142)).

---

## 6. A child's pages: Check-in, Plan, Assignments

Each child has three tabs: **Check-in · Plan · Assignments**. Clicking the child's name in
the rail opens Check-in.

### 6.1 Check-in — a short conversation that ends with a plan

The check-in is built for a parent and child sitting together for 10–20 minutes. It keeps
three things apart and never lets one overwrite another:

- **The school record** — what Canvas and HAC say, stated as facts.
- **The family account** — the child's own words: "handed it in on paper Friday".
- **The agreed next step** — one concrete step, who does it, which day.

**Step 1 — Review together.** Three folded groups, each with a count:

| Group | What is in it |
|---|---|
| **Questions** | The records disagree or say too little, and you can settle it ([§7](#questions)). |
| **Waiting on the school** | Nothing to do yet — a grade is expected, HAC is catching up. |
| **To do** | Work that is not done, or not due yet, that the child could act on. |

Each card shows the class, the assignment (links to its row), its **School record**, any
answer you gave before, how long late work is accepted ("Late work is usually accepted until
… (from your late-work rules)"), and **Plan a step**. Work past its late-credit window is
still shown, but below work that can still earn credit — the rule is your guess at the
teacher's policy, not the teacher's last word. "These are possibilities, not tonight's
obligations": pick a few. Anything not in the queue can be planned from **Browse all
work**.

> **Doing this with a younger child.** The *School record* block is written in the app's
> words, not the teacher's — "marked missing · 0 of 10" is a fact to check, not a verdict on
> the child — and it reads the same on the check-in card and the assignment's detail. A
> child on the early reading level gets the same facts in plainer words ("the teacher
> hasn't got it"), never fewer of them. Read it
> aloud in your own words and let them tell you what they know. The Questions are for the
> grown-up to settle; the child helps with the facts. Start with what went well: the
> *Done so far* line on the Assignments tab is a good opener.

**Step 2 — Plan a step.** The form asks:

- **Agreed next step** — e.g. "Redo problems 4–9 and hand in Monday".
- **Planned date** (or **When will you check again?** for a step that is waiting or needs
  help).
- **Who will do this?**
- **Family account** (optional) — prefilled from your last answer or note.
- Under **More**: **State** (*Work to do / Waiting / Need help / Step complete*),
  **Estimated minutes**, **Order within this day**, **Recorded by**.

**Save step**. The assignment leaves the review queue while it has a step.

**Step 3 — Our next steps.** The plan so far, in **Work to do**, **Need help** and
**Waiting**, with *M min estimated for today* against the time you last agreed ("X min over.
Move a step to another day."). **Add a task** adds a step not tied to any assignment
("pack gym clothes"). **Edit or complete step** opens a step again. A step whose school
facts changed since it was saved says *School evidence changed since this step was saved*.

> Completing a step records the **family's** commitment, not the school's record. The
> assignment comes back to review until Canvas or HAC shows it handed in or graded.

**Step 4 — Agree and wrap up.**

- **Time available today (minutes)** — required, defaults to last time's (else 40).
- **Next check-in** — a date; Today shows *Check-in due* once it arrives.
- **What we agreed** — a sentence or two, required.
- **Recorded by** — since there are no logins, this tells a second caregiver whose words
  they are reading.

**Finish check-in** saves an *agreement*: those fields plus a snapshot of the plan as it
stood. Later edits show as *Edited since* or *Added since* that check-in instead of
rewriting it. Past agreements are listed under **Previous agreements**; they cannot be
edited or deleted from the app.

### 6.2 Plan

The current steps against the agreed time budget, without the review queue and wrap-up.
Steps can still be added and edited from here (doing so currently returns you to the Check-in tab — [#128](https://github.com/steiner385/fridgesheet/issues/128)). **Print plan** opens a clean page with that child's steps, owners, dates and
the agreed summary, and **Print / save PDF** sends it to your browser's print dialog —
good for the fridge next to the school sheet.

### 6.3 Assignments

Everything the school lists for this child, with what needs your answer at the top.

1. **Done so far: X of Y due · Z on time.**
2. **Questions** — the same question cards as the Questions page ([§7](#questions)).
3. **Settled by the records** — what the app decided for you, each with a reason and a
   **Not right?** button. Older than a week folds under **Earlier**.
4. **Waiting, nothing to do yet** (folded) — waiting on a teacher or on HAC, plus things
   you asked about. *Asks you on Thu 9/24* says when it will turn into a question.
   **Ask now** skips the wait.
5. **Filters**, applied as you click:
   - **Open / Everything**. *Open* = past due and still inside its late-work window, or
     coming due, and not handled.
   - **Class**.
   - **More filters**: **Which gradebook** (either / in Canvas / in HAC / in both),
     **Kind of work** (online / paper / in class), **Your answer**, **What the app says**
     (needs your answer / decided for you / waiting), **Outcome** ([§14](#the-outcomes)).
     Choosing an answer, verdict or outcome shows *every* matching row, not just open ones.
6. **The work table** — **Due · Assignment · Where it stands**. Click a heading to sort,
   again to reverse. Badges beside the name: your flag, **question**, **in plan**, *N
   notes*. The class name links to the class page. Click the assignment name to open its
   detail: the record, **Plan a step**, **History** (every change, marked Canvas or HAC),
   notes, and under **More**, the answer menu ([§8](#8-answering-flags-answers-and-notes)).

### 6.4 A class page

Reached from the class name under any assignment.

- **Grade** — the official one first (HAC's marking-period average by default).
- **Teacher** — name and email when the school lists one.
- **Sources for this class** — which gradebook this *one class for this one child* reads
  **Assignment scores** and **Class average** from. **Save** writes a rule immediately
  ([§14](#which-gradebook-wins)).
- **Grade history**, a chart, notes, and every item from both gradebooks.

---

## 7. Open work and Questions

### Open work

The printed sheet, on a screen. Per child:

- **Still fixable** — past due, not handed in, and still inside its late-work window (and
  no more than *Overdue days* back). Soonest-closing first, each with *Credit thru Thu 9/24
  · 50%*.
- **Coming due** — not yet handed in, due within *Days ahead*.
- *Nothing open. Nice work.* when both are empty.
- **Not shown:** a count of work past its window and of open work you marked handled. Each
  count is a link to exactly the items it counts.

### Questions

"Where the school's records disagree, or say too little to act on. Answer one and it leaves
this page." Fridge Sheet only asks when *you* can do something. Each card shows the
assignment, the facts in one sentence, the question in bold, and two to four answers.
**See the record** unfolds the raw facts from each gradebook, how long this class usually
takes to grade, and **Email with these facts** — a pre-written email to the teacher.

| Question | When you see it | Answers |
|---|---|---|
| **Which is right?** | HAC has a grade, but Canvas marked it missing *after* that. | *HAC is right, it's done* · *Ask the teacher* |
| **Ask the teacher to fix HAC?** | HAC's score is lower than Canvas's, and neither the grading scale nor your late rule explains it. | *Ask the teacher* · *HAC is right* |
| **Tell the teacher?** | Handed in on Canvas, but HAC counts a zero. | *Ask the teacher* · *The zero is right* |
| **Ask to have it excused in HAC?** | Excused in Canvas, but HAC counts a zero. | *Ask the teacher* · *Leave it* |
| **Ask the teacher to enter it?** | Graded in Canvas, still blank in HAC longer than HAC usually takes. | *Ask the teacher* · *It's fine* |
| **Was it handed in?** | Paper, in-class or HAC-only work with no grade for longer than this class usually takes. | *Yes, handed in* · *Today* · *Tomorrow* · *Ask the teacher* |
| **Still done?** | You said it was done, and the school now says missing or zero. | *Yes, still done* · *No, reopen it* · *Ask the teacher* |
| **Is it settled?** | You asked the teacher (or were following up) and a grade has since appeared. | *Yes, it's done* · *Not settled, keep asking* |

**Today** and **Tomorrow** add a step to the child's plan for that day. Every answer can be
**Undo**ne right after.

Under each child, **Waiting on the teacher** lists what you have asked about, and **Can't
pair these** lists probable Canvas/HAC twins the app would not guess at (nothing is asked
of you).

**Let all N go.** When a child has two or more assignments past their late-credit window,
a bar offers to mark them all *Let it go* at once. These are "too late for credit" work,
not the question cards on this page, so the bar names each one (class and due date) and the
confirm names them again. They stop counting as open work; nothing is deleted. Afterwards
the page says which went, with one **Undo** that puts back exactly those items (an item you
answered since keeps your answer).

---

## 8. Answering: flags, answers and notes

Every assignment can carry **one answer** from you at a time (on the item's **More** menu the current one is shown as *Your answer: …*, in the same words as the row's badge).
Open an assignment's detail and look under **More → Correct the school record**, or answer
a question card.

| Answer | Means | Effect |
|---|---|---|
| **It's done** | Handed in; the school just hasn't recorded it. | Handled — off Open work, the sheet and the Questions count. |
| **Excused** | The teacher excused it. | Handled. |
| **Let it go** | You've decided not to chase it. | Handled. |
| **Too late to submit** | The teacher no longer accepts it. | Handled. |
| **Follow up** | You're keeping an eye on it. | Stays listed, with a marker (FOLLOW UP on the sheet). |
| **Ask the teacher** | You're asking. | Stays listed, with a marker (ASK THE TEACHER on the sheet); moves to *Waiting on the teacher*. |

- **Why (optional)** records a reason next to the answer.
- **clear** removes the answer.
- Answers change what is *listed*, never the outcome counts on the School record line.
- Answers, notes and plan steps are kept in the app's database and survive every refresh.
- If the school later contradicts your answer, the app asks **Still done?** rather than
  silently keeping or dropping it.
- **Not right?** on a *Settled by the records* line opens that item's question card, with
  its answers, in place of the line. Nothing changes until you pick one, and a reason you
  gave earlier is kept.

**Notes** can go on an assignment or a class: **Add a note**, then **Add note**; each has
**edit** and **delete** (deleting is permanent). The newest note appears on the check-in
card and prefills the family account.

> Two HAC-only assignments with exactly the same title in one class (e.g. weekly
> "Participation") can lose an answer when the second one appears. Canvas assignments do not have this problem ([#136](https://github.com/steiner385/fridgesheet/issues/136)).

---

## 9. The printed sheet

US Letter, portrait, printed two-sided, one section per child.

**Section header:** *Name — open work*, the date, the window ("next 14 days plus overdue
within 14"), and counts of open, new and cleared since the last sheet.

**Each row:** ☐ · **NEW** or *was …* (compared with the last sheet) · due date and when it
was given · class · assignment · points · where it was read (Canvas / HAC / Both) and how it
is handed in (online / paper / in class) · status.

**Status words**

| Word | Colour | Means |
|---|---|---|
| MISSING | red | Past due and not handed in (or the teacher marked it missing). |
| ZERO | red | A 0 was entered in either gradebook. |
| LATE | amber | Handed in late, not yet graded. |
| PAPER — CHECK | purple | Paper work, past due, no grade anywhere yet — ask. |
| HAC — NO GRADE | purple | Listed only in HAC, past due, no grade. |
| DUE TODAY / DUE TOMORROW | blue | |
| DUE *Mon* … | black | Due later in the window. |

Overdue rows add *50% until Fri* — the last day your late-work rule says it is still
accepted. FOLLOW UP / ASK THE TEACHER mark your answers. A child on the early or middle reading
level gets their own words instead of the capitals ("Teacher hasn't got it" for MISSING). A child on the older level, or with no grade set, sees the capitals in red — the fridge is a shared surface, so decide whether that suits your teenager.

**Under each table:** *Cleared since last sheet*, *Handled: n items marked done, excused or
ignored in the app*, and *Not shown: n items past the late window or older than …* A child
with nothing open still gets a section: *Nothing open. Nice work.* The legend ends with
*Data as of …*; a red note appears if the sheet was built from data older than the last
attempted refresh.

**What never prints:** work you marked handled; work past its late window or older than
*Overdue days*; paper work with a grade in HAC (it's done); anything due before August 1 of
the current school year (last year's course copies).

**When it prints** — see [§10](#10-schedules-printing-and-refreshing-on-their-own). A day
already printed is not printed again (except by **Reprint**); a day listed in *Days the
sheet does not print* is skipped.

> The screen and the paper are meant to list the same rows. A few edge cases still differ:
> in-class work with no grade shows as *unknown* on screen but MISSING on paper; a HAC-only
> item shows on screen the moment it is past due but on paper a day later; Canvas work with
> no due date never prints; and an assignment the screen pairs by date and points (because
> the two teachers typed different titles) prints as PAPER — CHECK ([#137](https://github.com/steiner385/fridgesheet/issues/137)).

---

## 10. Schedules: printing and refreshing on their own

**Schedules** has one form for the data refresh and one per report.

### Refresh the data

- **Refresh on a schedule**, **Every [N] hours**, **Between** [start] **and** [end], the
  days. The page previews the times ("Refreshes at 06:00, 09:00, …"). At most 12 a day; the
  window cannot cross midnight.
- Installs a systemd timer (`fridgesheet-data-refresh`) on Linux or a task (**Fridge Sheet -
  data-refresh**) on Windows.

### Each report (the built-in *Open Work Sheet*, then any you saved)

> A report schedule prints from the last refresh; it does not refresh first. Keep **Refresh the data** (above) turned on, or the sheet stops printing after a day. Saving a report schedule while the refresh is off turns the refresh on with its current settings (the defaults, unless you changed them) and says so in the saved message; the page shows a warning, and Diagnostics fails, while any report is scheduled with the refresh off.

- **Run this on a schedule**, **Time** (24-hour), **Days**.
- **Printer** — *(the printer on the Settings page)*, or a different one for this report.
- **Print it (off: keep the PDF only)** — untick to build a PDF you can check before it
  goes on the fridge.
- **Save** writes your settings *and* installs or removes the OS task. The state line says
  when it next runs.

**How a scheduled run behaves**

1. Skips a date listed in *Days the sheet does not print*.
2. Skips a date already printed.
3. Uses the latest refresh; refuses if that is more than 24 hours old.
4. Builds the PDF, saves a copy to your archive folder if set, prints (unless PDF only),
   records the run, and shows a desktop notification.

Runs missed while the computer was asleep or signed out start when it wakes; if that is
already the next day, it logs "outside print window" instead of printing yesterday's sheet.
On Windows the computer must be **on and signed in** (a locked screen is fine).

**Things to know**

- Nothing is installed until **Test login** (or `fridgesheet check`) has passed once.
- To stop a schedule: untick **Run this on a schedule** and Save — this removes the task,
  not just the tick. (Leave at least one day ticked when you do.)
- Weekends print if you tick Sat or Sun.
- A report time that coincides with a refresh time (e.g. refreshing every 2 or 4 hours
  from 06:00 lands on 14:00) is fine: the report waits for the refresh to finish (up to
  10 minutes) and then prints from the fresh data; `print-sheet.log` says how long it
  waited. Saving either form tells you when the two coincide. If a run is still going
  after 10 minutes the report gives up with a notification and a FAIL row, not a silent
  skip. The scheduled refresh waits the same way for a print in progress.
- A schedule written by hand (outside the app) is shown disabled, with the `systemctl`
  command to turn it off yourself.

---

## 11. Reports

The **Open Work Sheet** is built in. You can build your own on **Reports**.

- **Add the starter reports** (shown when you have none) adds four: *Open work*, *Recent
  changes*, *Grade trend*, *Quarter recap*.
- **New report** opens the builder:
  - **Name** and **Title on the page**.
  - **Rows come from**: *items* (assignments), *grades* (class averages over time) or
    *changes* (the change feed).
  - **Rows from**: any time, the last 7/30/90 days, this school year, or a custom range.
  - **Kids** (none ticked = every kid), **Columns**, **Group by**, up to two **Sort**
    keys, up to three **Filters** (*is / is not / contains / ≥ / ≤*).
  - **Chart**: none, line, bar or stacked bar.
  - **Page**: portrait or landscape; each group on its own page.
  - **Preview** shows the table live below the form (up to 2000 rows); **Save** keeps it.
- In the **Yours** list: **Edit**, **CSV**, **JSON**, **Preview** (builds the PDF),
  **Print** (with **Refresh first**), **Delete** (also removes its schedule).
- The report's own page has **Print / save PDF** for your browser's print dialog.
- To print a report on a schedule, use its section on **Schedules**.

---

## 12. Runs, Changes and Trends

**Runs** — the last 100 sheets and reports built or printed: when, which, *Started by*
(you, the schedule, the command line), OK/FAIL/SKIP and why, the PDF, and **Reprint**.

**Reprint** sends that row's stored PDF to the printer again, exactly as it was — it does
not rebuild from today's data. A Preview or a `--kid`/`--date` build has its own file
([§19](#19-files-backup-and-privacy)), so it never replaces the sheet a day printed.

**Changes** — everything that moved: *New, Grade posted, Grade changed, Now missing,
Cleared, You answered, You cleared a flag, Class average*. Choose the window (*Since
yesterday*, 3 days, a week, a month), a child and kinds. Click an item to expand it.

**Trends** — per child, 4, 8 or 16 weeks:
- **On-time hand-ins** — on time ÷ (on time + late + not done), over work due so far.
- **Open the longest** — what has sat open longest.
- **Grades** — each class's average over time; the line from your chosen source is
  marked *official*.
- **How the work due each week came out** — outcomes by the week work was *due*.

---

## 13. Settings

One form with one **Save** at the bottom, then separate editors below it.

| Card | Fields |
|---|---|
| **School login** | **OneLogin username**, **OneLogin password** (blank keeps the stored one). |
| **Printing and the report window** | **Printer**, **Days ahead**, **Overdue days** (1–60, for the Open Work Sheet), **Archive folder** (a second copy of every PDF, e.g. a Google Drive folder, filed as `2026-27/2026-09-11 Open Work.pdf`), **Nicknames**. |
| **Where you are** | **Time zone** — blank means this computer's zone, which the page names; pick a US zone from the list or type any name such as `America/Chicago`. Due times, "today", the print window and schedules follow it. On Windows a scheduled task fires on the PC's clock, so the app writes it converted from this zone when the two differ (the Schedules page's next run is then in the PC's time). |
| **Gradebook sources** | **Assignment scores come from** (default Canvas) and **Class averages come from** (default HAC). |
| **Network** | **Port** (default 8433), **Allow other devices on this network** ([§16](#16-using-it-on-a-phone-or-tablet)). |
| **Updates** | Version and update status, **Check for updates now**, **Check GitHub once a day for a newer version**, **Update PIN** (at least 4 characters; **Remove the update PIN** appears once one is stored). On Linux the card says how to update the checkout instead of offering the Windows button. |

Buttons: **Save**, **Test login**.

Below the form:

- **Gradebook overrides** — per-child/per-class source rules you set on class pages, each
  with **Remove**.
- **Late-work rules** (see below) — **Save late-rules.toml**.
- **Days the sheet does not print** — one row per day or date range (*start* through
  *end*, optional note), **Add date**, **Save no-print-days.txt**. Seeded with Lakota Local Schools'
  2026-27 calendar; replace it with your district's.

Saving either editor rewrites its whole file, so comments you typed into the file by hand
are not kept.

### Late-work rules

How long after the due date each class still takes work, and for what credit. The printed
sheet and Open work drop overdue work once its window closes.

- **Default** — *Accepted late for [14] days*, *Credit shown* (free text, e.g. `50%`).
- **Quarters** — the grading-period end dates, for "through end of quarter" rules.
- **Rules**, checked top to bottom, **first match wins**: **Kid** (optional),
  **Course contains** (optional), **Late for (days)** or **Through end of quarter**,
  **Credit shown**, and a private **Source** note ("from the syllabus"). Use ↑ ↓ to order
  them.

Matching tips: *Course contains* matches any class name containing that text, so
`Algebra I` also matches *Algebra II* — put the more specific rule first. *Kid* matches
by the start of the name, so `Max` also covers *Maxine*. Use the child's first name as the
school lists it, not a nickname.

If *Credit shown* starts with a percentage, the app also uses it to explain a lower HAC
score on late work (Canvas 10, HAC 5 under "50%" = expected, not a question).

### What Settings doesn't show

Some settings live only in files in the data folder ([§19](#19-files-backup-and-privacy)):

- `config.toml`: `[kids] grades`, `[web] extra_hosts`, per-report options,
  `[[sources.rule]]` (also editable per class).
- `.env`: district addresses (`FRIDGESHEET_CANVAS_BASE`, `FRIDGESHEET_HAC_BASE`,
  `FRIDGESHEET_ONELOGIN_HOST`), and overrides such as `FRIDGESHEET_PRINTER` and
  `FRIDGESHEET_TIMEZONE`. A value in the environment or `.env` **beats** the same setting on
  the Settings page, and the page says so beside the box.

### Where the password can come from

In order: `FRIDGESHEET_ONELOGIN_USERNAME` / `_PASSWORD` in the environment or `.env`
(plain text — only if you manage that file carefully); the OS credential store (the
default, what Settings writes); 1Password `op://` references
(`FRIDGESHEET_OP_USERNAME_REF` / `_PASSWORD_REF`, with `OP_SERVICE_ACCOUNT_TOKEN` for
unattended runs).

---

## 14. How Fridge Sheet decides

The full rules, with the reasoning, are in [outcomes.md](outcomes.md). The short version:

### The outcomes

Every assignment gets exactly one. The first that applies wins.

| Outcome | Means |
|---|---|
| **excused** | The teacher excused it in Canvas. Counted nowhere. |
| **unpublished** | The teacher unpublished it. Counted nowhere. |
| **not done** | Canvas marked it missing; *or* a 0 was entered in either gradebook; *or* it is online work, past due, with no submission and no grade. |
| **late** | Handed in on Canvas after the deadline. |
| **on time** | Handed in on Canvas by the deadline. |
| **done on paper** | A grade above zero with no online hand-in. Its timing can't be known, so it is neither on time nor late. |
| **unknown** | Past due, paper or in-class work, no grade anywhere yet. *The list to ask teachers about.* |
| **not due yet** | Due later, not handed in. |

Two things that surprise people: **a teacher's 0 counts as not done** (it is how many
teachers record missed work), and **graded paper work counts as done** even though Canvas
lists it as unsubmitted forever.

**Open** = not done or unknown, plus late work not yet graded. **Still fixable** = open,
inside its late-work window, within *Overdue days*, and not answered as handled.

### Decide, wait, or ask

On top of the outcome, the app gives each item a *verdict*:

- **Decided for you** — the records settle it. E.g. HAC has 9/10 and Canvas's automatic
  "missing" is left over: *Done · 9 of 10 in HAC*. Or HAC's lower score is exactly the late
  penalty. Shown under *Settled by the records* with **Not right?**.
- **Waiting** — time will settle it: graded in Canvas and not yet in HAC; handed in and not
  graded; paper work still inside the class's usual grading time.
- **Asks you** — only the questions in [§7](#questions).

**"Usually takes"** is Fridge Sheet's own count: from this class's earlier assignments, how
many days until a grade appeared (the 80th percentile, between 1 and 21 days). With fewer
than three earlier grades it allows 7 days. The card always says which.

### Which gradebook wins

By default **assignment scores come from Canvas** and **class averages from HAC** (the
gradebook of record). Change either for the family on Settings, or for one child's one
class on its class page. The preferred source wins when both have a number; the other fills
gaps. *Handed in*, *late* and *excused* always come from Canvas, because HAC doesn't record
them.

### How Canvas and HAC are paired

Classes are matched by name (ignoring term, section and teacher; numbers must agree, so
Math 7 never pairs with Math 8). Assignments are matched by title (numbers must agree, so
Quiz 1 never pairs with Quiz 2), then, for titles typed differently, by the same due date
and points when there is exactly one candidate. An assignment that fails to pair shows up
twice — once from each gradebook. Two Canvas assignments with the same title are always two
pieces of work.

---

## 15. Children's reading levels

This isn't on the Settings page yet. Open `config.toml` in the data folder — on Windows, paste `%LOCALAPPDATA%\fridgesheet` into File Explorer's address bar and open `config.toml` with Notepad — and add a `grades` line under `[kids]` (0 = kindergarten; use
the first names as the school lists them). If you have nicknames there is already a `[kids]`
line: add only the `grades` line beneath it, since a second `[kids]` line breaks the file.
Then restart Fridge Sheet.

```toml
[kids]
grades = { Alex = 9, Sam = 4 }
```

| Grade | Level | What changes on their pages |
|---|---|---|
| K–5 | early | Largest type, calmer colours, plain words: "Teacher hasn't got it", "evening" for 11:59pm. |
| 6–8 | middle | Medium type, "Marked missing". |
| 9–12 | older | Standard type and wording. |
| not set | — | Exactly as before this existed. |

It changes type size, spacing, colour and wording on the child's pages, check-in, plan,
Open work and their Questions section, and the words in their section of the printed sheet.
It **never** changes which assignments or buttons appear. The rail folds away on their
pages.

---

## 16. Using it on a phone or tablet

1. **Settings → Allow other devices on this network**, **Save**.
2. Restart Fridge Sheet (Windows: sign out and back in; Linux:
   `systemctl --user restart fridgesheet-web`). Settings says when a restart is needed.
3. Settings now shows **Other devices: http://192.168.x.x:8433/** and a **QR code** — point
   the phone's camera at it. Tailscale users also get an *On your tailnet* address.

The app has no password and no HTTPS. Anyone on your network who has the address can use
every page, and the OneLogin password typed on Settings from a phone crosses the network
unencrypted. Only turn this on at home.

The app only answers at its own addresses. A computer name like `http://dobby:8433/` is
refused ("Fridge Sheet only answers at …") unless you list it under `[web] extra_hosts` in
`config.toml`.

---

## 17. The command line

Everything the web app does, plus a few things it doesn't. On Windows the command is
`FridgeSheet.exe`; commands that ask for a password need a console.

| Command | Does |
|---|---|
| `fridgesheet set-credentials` | Stores the username and password. |
| `fridgesheet check` | Test login; a pass counts the same as the button's. |
| `fridgesheet login` | Opens a visible browser to sign in by hand — for diagnosing a changed login form. |
| `fridgesheet refresh [--record]` | Pulls the data. `--record` also updates the app's database — what the refresh schedule runs. |
| `fridgesheet status` | Data age and each source's health, as JSON. |
| `fridgesheet run open-work` | Refresh, build, print — like **Print now** with **Refresh data first**. Flags: `--dry-run` (build only), `--no-refresh`, `--kid NAME`, `--date YYYY-MM-DD`, `--days N`, `--overdue-days N`, `--printer P`, `--force` (ignore no-print days and time of day), `--reprint`. |
| `fridgesheet run view:<id>` | The same for a saved report. |
| `fridgesheet print-sheet` | The original name for `run open-work`; always uses 14/14 days. |
| `fridgesheet reports` | Every report and its schedule. |
| `fridgesheet schedule install\|remove\|show <key>` | Install/remove/show a report's OS schedule; `install data-refresh` is the refresh schedule. `install` refuses until a login has passed (`check` or Test login) unless `--force`. `remove --all` removes every one. |
| `fridgesheet printers` | Lists printers; `*` = default. |
| `fridgesheet web` | Runs the web app in the foreground; `--no-browser` on a machine with no desktop. |
| `fridgesheet service install\|remove\|show` | Keeps the web app running in the background. |
| `fridgesheet doctor` | Diagnostics (same as the Diagnostics page). |
| `fridgesheet self-update [--check]` | Windows only: install the newest release. |
| `fridgesheet serve` | The MCP server for Claude ([§18](#18-using-it-from-claude-mcp)). |

`run --dry-run`, `--kid` and `--date` build a side file (`sheet-preview.pdf`, or
`sheet-<kid>.pdf`) beside the day's sheet and never touch `sheet.pdf`, what it was compared
against, or the archive copy — so running them after the day's print changes nothing on
paper. A dry run prints nothing and shows no notification, but it is still listed on Runs.

**Linux desktop shortcuts** (`desktop/`): *Kids' Sheet (PDF only)* and *Kids' Sheet (Send
to Printer)* — see the README.

---

## 18. Using it from Claude (MCP)

`fridgesheet serve` lets Claude Desktop read the same data without a browser. Add the block
in `claude_desktop_config.example.json` to Claude Desktop's config (quit Claude Desktop
first), and restart it. Tools: `list_students`, `grades`, `missing_work`, `upcoming`,
`assignments`, `hac_classwork`, `status`, `refresh`. Claude never sees your password. A read
may start a refresh (minutes) if the data is older than 3 hours. The MCP tools do not see
your answers from the app.

---

## 19. Files, backup and privacy

The data folder is `%LOCALAPPDATA%\fridgesheet` on Windows and `~/.fridgesheet` on Linux
(or `FRIDGESHEET_HOME`).

| File | What |
|---|---|
| `config.toml` | Your settings (no password). |
| `.env` | Optional overrides and district addresses. |
| `late-rules.toml`, `no-print-days.txt` | The two files edited on Settings. |
| `fridgesheet.db` (+ `-wal`, `-shm`) | Everything the app remembers: history, answers, notes, plans, check-ins, reports, runs. **Back up all three together, with the app stopped.** Deleting it loses history, not sheets. |
| `cache/snapshot.json` | The latest refresh. |
| `sheets/<date>/` | Each day's `sheet.pdf`, what was on it (`rows.json`), and whether it printed (`printed.txt`) — written only by the day's real run. A Preview, dry run, `--kid` or `--date` build writes `sheet-preview.pdf` or `sheet-<kid>.pdf` beside them instead (the newest preview replaces the last). |
| `reports/` | Saved reports' PDFs. |
| `browser-profile/` | Sign-in cookies. Treat it like a password. |
| `print-sheet.log` | One line per run. |
| `app.log` | The web app's log (Windows). On Linux: `journalctl --user -u fridgesheet-web`. |
| `doctor.txt` | The last diagnostics report. |

**Privacy.** Grades stay on this computer. Nothing is uploaded. The browser profile and the
data files are readable only by your user.

---

## 20. Troubleshooting

Start with **Diagnostics → Run diagnostics**. Any `FAIL` line is where to look.

| Symptom | Likely cause and fix |
|---|---|
| Test login: **Login failed** | Wrong username/password, or OneLogin wants multi-factor sign-in. Fix, **Save**, Test login again. |
| ⚠ *This data is N hours old* | Refreshes are failing or not scheduled. Check the status bar's Canvas/HAC text; turn on **Refresh on a schedule**. |
| Nothing printed at the scheduled time | Open **Runs**: SKIP (no-print day, already printed, outside the print window, another job was running) or FAIL (stale data, printer). Also: computer off or signed out; Test login never passed. |
| *snapshot is stale … nothing printed* | No refresh in 24 h. Turn on the refresh schedule, or press Refresh now. |
| Printed on the wrong printer | The report's printer on Schedules beats Settings; `FRIDGESHEET_PRINTER` in the environment beats both. |
| *Fridge Sheet only answers at http://127.0.0.1:8433/* | You used another address (a computer name, a port-forward). Use `127.0.0.1`, or the address/QR from Settings on a phone ([§16](#16-using-it-on-a-phone-or-tablet)). |
| The shortcut does nothing / browser can't connect | The app didn't start. On Windows, paste `%LOCALAPPDATA%\fridgesheet` into File Explorer's address bar and open `app.log` in Notepad; the last lines say why. On Linux: `journalctl --user -u fridgesheet-web`. Signing out and in, or running the shortcut again, restarts it. |
| An assignment appears twice | Canvas and HAC titles didn't pair. Look under **Questions → Can't pair these**. Answer the duplicate *Let it go*. |
| The status bar says *Canvas OK (1 class carried from …)* | Canvas refused that one class on the last refresh (the error is in the parentheses). Its work is still shown, from the pull named; it will be current again the next time the class answers. *1 class not fetched* means there was no earlier copy to show — refresh again. |
| Settings or Schedules shows an error page | A hand edit made `config.toml` invalid (e.g. `time = "25:99"`). Fix or remove the line. |
| The keyring prompt hangs a refresh (Linux) | The login keyring is locked; sign in to the desktop. |

### Known issues worth knowing

- Work due at exactly midnight reads *Due tomorrow* the evening before ([#139](https://github.com/steiner385/fridgesheet/issues/139)).
- A class whose Canvas page failed to load during a refresh drops out until the next good refresh, with no warning ([#140](https://github.com/steiner385/fridgesheet/issues/140)).
- Two assignments with nearly the same title ("Unit 3 Test", "Unit 3 Test Retake") can be paired wrongly ([#132](https://github.com/steiner385/fridgesheet/issues/132)).
- The full list from the review that produced this guide: issues [#120–#154](https://github.com/steiner385/fridgesheet/issues?q=is%3Aissue+120..154).
- A few cases where the screen and the printed sheet disagree ([§9](#9-the-printed-sheet)).
- The open issue list: <https://github.com/steiner385/fridgesheet/issues>.

---

## 21. Updating and uninstalling

**Updating (Windows).** Once a day the app checks GitHub; *Fridge Sheet X is available*
appears in the header and on Settings. Either download and run the new installer over the
old one, or set an **Update PIN** on Settings (at least 4 characters; a **Remove the
update PIN** box appears once one is stored) and use **Update to X** (shown when the
background task is installed). The PIN only guards the button — it crosses the network
unencrypted. From a console: `FridgeSheet.exe self-update`.

**Updating (Linux).** `git pull && pip install -e .`, then restart the web service. The
Settings card says the same and offers no button, because the release asset is a Windows
installer.

**Uninstall (Windows).** Settings → Apps → Fridge Sheet → **Uninstall**. It removes every
task it installed and leaves your data folder and the Credential Manager entry
*fridgesheet* for you to delete. Afterwards, check Task Scheduler for anything still named
*Fridge Sheet - …*.

**Upgrading from a version before 0.4, when the app had another name.** Install Fridge
Sheet over it. The first start moves your data and password to the new names; notes, flags,
runs, sheets and schedules carry over. The details are in
[windows.md](windows.md), under *Upgrading*.

---

## Glossary

| Term | Meaning |
|---|---|
| **Canvas** | Where teachers post and collect online work. Knows whether and when something was handed in. |
| **HAC** | Home Access Center, the official gradebook. Its class average is the report-card grade. |
| **Refresh** | One pull of both gradebooks for every child. |
| **Outcome** | What happened to an assignment: on time, late, not done, done on paper, unknown, not due yet, excused, unpublished. |
| **Open** | Not done or unknown, or late and not yet graded. |
| **Still fixable** | Open, inside its late-work window, and not answered as handled. |
| **Handled** | Answered *It's done*, *Excused*, *Let it go* or *Too late to submit*. |
| **Verdict** | Decided / Waiting / Asks you. |
| **Late-work window** | How long after the due date the class still takes work, from your late-work rules. |
| **Check-in** | A short parent–child review that ends with a few agreed steps. |
| **Step** | One agreed action: what, who, which day. |
| **Agreement** | A finished check-in: time budget, next date, summary, and a snapshot of the plan. |
| **Family account** | The child's own words about what happened, kept apart from the school record. |
| **Report** | The built-in Open Work Sheet, or one you built on Reports. |
| **Run** | One build (and maybe print) of a report. |
