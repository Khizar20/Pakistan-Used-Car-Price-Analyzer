# Agent working agreement

Read `docs/PLAN.md` completely before changing this repository. Work one phase at a
time and in order. Do not start the next phase until the current phase's "Done when"
criteria are met and `make check` passes. Write tests before or alongside every
module; default tests must be offline, deterministic, and use anonymized fixtures.

## Python

- This repository uses Python 3.10, overriding the Python 3.11+ statement in the
  original plan. Never fall back to or install another Python version.
- Locate it with `py -3.10 --version` on Windows or `python3.10 --version` on Linux.
- Create `.venv` explicitly with Python 3.10 and install packages only through the
  venv interpreter using `python -m pip`; never use bare or global `pip`.
- Keep `requires-python = ">=3.10"`, Ruff `target-version = "py310"`, and mypy
  `python_version = "3.10"`. Code must remain Python 3.10 compatible.
- Do not use `tomllib`, `typing.Self`, `enum.StrEnum`, `ExceptionGroup`, `except*`,
  `datetime.UTC`, or `asyncio.TaskGroup`. Use `datetime.timezone.utc` and `tomli`
  when TOML parsing is required.
- All Make targets must use the `PYTHON` variable pointing to the venv interpreter.

## Data collection and privacy

Respect `robots.txt` and site terms. Access public pages only, rate-limit requests,
and never bypass logins, CAPTCHAs, or blocking. Do not collect or export seller
names, phone numbers, exact addresses, or other personal data. Never commit raw
HTML, the full SQLite database, secrets, or files over 5 MB. Live network tests must
be explicitly opted into with the `live` marker.

Do not invent selectors. In Phase 2, inspect live pages and save small, anonymized
fixtures. If pages cannot be fetched, stop and request the required fixtures.

## Quality and commits

Run `make check` before every commit. A module may be committed only when its code
and tests are complete and all checks pass, with no TODOs, debug prints, commented
code, or unfinished files. Use one commit per finished module.

Use WSL Ubuntu for every Git command; never run native Windows Git. Review status
and diffs, stage explicit paths (never `git add .`), then commit with
`<area>: <what was done>` and a body listing tests. Push each commit to `origin main`.
Never force-push. If push fails, report the exact error and stop.
