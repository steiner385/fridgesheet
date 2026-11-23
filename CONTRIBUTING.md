# Contributing to Fridge Sheet

Thanks for helping. Fridge Sheet is a small project run by one parent for a few households,
so the process is light: open an issue or a draft pull request, keep the tests green, and
keep real family data out of the repository.

Where things are documented:

- [docs/user-guide.md](docs/user-guide.md): for parents using the app (install, every page,
  the printed sheet, troubleshooting).
- [README.md](README.md): the developer and operator reference (credentials, the CLI, the
  MCP server, files, schedules, releasing).
- [docs/outcomes.md](docs/outcomes.md): the one definition of "done" every page and the sheet
  share. Read it before changing how an item is classified.
- [PRODUCT.md](PRODUCT.md) and [DESIGN.md](DESIGN.md): who it is for and how it should look
  and read.

## Set up a development checkout (Linux)

You need Python 3.11 or newer.

```bash
git clone https://github.com/steiner385/fridgesheet ~/fridgesheet
cd ~/fridgesheet
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
playwright install-deps chromium      # once, needs sudo, on a minimal install
sudo apt-get install -y poppler-utils # pdftotext, used by the sheet tests
```

Then:

```bash
python -m pytest -q                   # the whole suite, a few minutes
fridgesheet doctor                    # what this machine has and lacks
fridgesheet web                       # the browser app at http://127.0.0.1:8433/
```

You do not need a school account to work on most of the app. The tests build every page from
made-up fixtures (`tests/web_fixtures.py`, `tests/conftest.py`). To try the app against
your own district, follow the user guide's install and "Another school district" sections.

Keep your own data out of the checkout: set `FRIDGESHEET_HOME` to a directory outside it if
you like, and never point the tests at a real snapshot.

### On Windows

`pip install -e ".[dev,windows]"` instead, then the same `playwright install chromium` and
`python -m pytest -q`. To build the installer yourself, run
`packaging\windows\build.ps1` (needs Python 3.12 and Inno Setup 6); it is exactly what the
release workflow runs.

## Before you open a pull request

- `python -m pytest -q` passes. CI runs the suite on both Ubuntu and Windows
  (`.github/workflows/ci.yml`), so a path, a line ending or a shell call that only works on
  one of them will show up there.
- New behaviour comes with a test. The suite is the spec for most of the app.
- No real data from any family: no real children's, teachers' or schools' names, no
  student or course IDs, no grades, no snapshots, no `.env`, no browser profile, no
  screenshots of a real account. Use made-up names (the tests use Alex, Sam, Maya and
  similar) and `example.org` addresses. `.gitignore` already keeps `.env`, `snapshot*.json`,
  `browser-profile/` and `cache/` out; check `git status` before you commit anyway.
- Nothing logs or prints a credential. Logins happen inside the server process, with the
  password read from the OS credential store at the moment it is typed.
- Write user-facing words the way the rest of the app does: plain, specific, for a parent
  reading at the fridge. DESIGN.md has the details.

Open the pull request as a draft until it is ready for review, and say in its description
what a parent would see before and after the change.

## Releases

Every merge to `main` publishes a Windows release automatically, and installed copies offer
it within a day (README, "Releasing the Windows installer"). So a change that should not
reach parents' PCs on its own, such as a docs-only change or one half of a two-part change,
gets `[skip release]` on a line of its own in the merge commit message. Only the maintainer
merges to `main`.

## License

By contributing you agree that your contribution is licensed under the
[MIT License](LICENSE), like the rest of the project.
