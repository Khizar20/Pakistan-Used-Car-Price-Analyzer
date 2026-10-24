# Daily collection and database maintenance

Use one local daily worker. Local collection is preferable to a cloud cron job,
where source blocking may be more likely. Scheduling is documented here, not
installed by the application. Review the source's current access rules and inspect
any access challenge rather than retrying around it.

## Before scheduling

1. Verify Python 3.10 and run `make check` using the project's venv interpreter.
2. Run a small manual scrape with your real contact email, then check `tracker status`.
3. Run `tracker backup` before a manual `tracker migrate` on an existing database.
4. Pick a fixed page budget. `--limit-pages` is a total budget across models, not a
   budget for each model. Discovery is an additional page read.
5. Keep the machine awake and network available at the chosen time. Windows time
   should be set to Pakistan Standard Time (Asia/Karachi) for the 09:00 example.

Every command below runs through the venv's Python 3.10. Git operations must still
use WSL Ubuntu. No scheduled task needs a GitHub token: data stays local and is
not automatically committed or pushed.

## Windows Task Scheduler (recommended for this workstation)

Create a task named `Pakistan used-car tracker` in Task Scheduler. Use your normal
user account, without elevated privileges. For initial verification, run only
when that user is logged on.

- Trigger: daily at 09:00 in the machine's local Pakistan time.
- Action / Program: `D:\Data Analysis Projects\Local Price Tracker\.venv\Scripts\python.exe`
- Action / Arguments: `-m tracker.cli scrape --source pakwheels --limit-pages 30 --contact-email YOUR_EMAIL`
- Action / Start in: `D:\Data Analysis Projects\Local Price Tracker`
- Settings / If the task is already running: **Do not start a new instance**.
- Avoid automatic repeat-on-failure loops. Inspect `tracker status` after failures.
- Allow enough time for rate-limited detail collection on the first run; hundreds
  of new vehicles take time at one request per two seconds plus jitter.

Use **Run** once and inspect Task History, Last Run Result, and the tracker's status.
Set Start in explicitly: Task Scheduler otherwise defaults to a system directory,
which would make relative data/cache paths resolve incorrectly. The overlap policy
corresponds to `IgnoreNew`. See Microsoft's
[task action documentation](https://learn.microsoft.com/powershell/module/scheduledtasks/new-scheduledtaskaction)
and [task settings documentation](https://learn.microsoft.com/powershell/module/scheduledtasks/new-scheduledtasksettingsset).

## Keep the comparison scope stable

Default discovery picks ten models from the site's displayed counts. Changes in
ranking or page budget change the observed window and its scope key. For a stable
comparison, use repeated `--model-path` options with paths you have inspected.
For example, these ten paths were observed in the saved source fixtures:

```powershell
.venv/Scripts/python.exe -m tracker.cli scrape --contact-email YOUR_EMAIL --limit-pages 30 --model-path /used-cars/toyota-corolla/688 --model-path /used-cars/honda-civic/642 --model-path /used-cars/honda-city/664 --model-path /used-cars/suzuki-mehran/661 --model-path /used-cars/suzuki-cultus/660 --model-path /used-cars/suzuki-alto/658 --model-path /used-cars/suzuki-wagon-r/801 --model-path /used-cars/suzuki-swift/778 --model-path /used-cars/toyota-vitz/781 --model-path /used-cars/kia-sportage/715
```

Review these paths against the current source before setting up a long-term task;
they are examples of observed links, not a guarantee of permanent site structure.
Copy the chosen arguments into the scheduled task. Thirty pages across ten models
means up to three pages per model. This remains a bounded window, not a census.

## Linux cron alternative

Use this only with a native Linux Python 3.10 venv. A Windows `.venv/Scripts`
environment is not a Linux environment; do not silently select another Python.
First confirm `python3.10 --version` and `.venv/bin/python --version`. Ensure
`data/` exists, and check the machine's local timezone before choosing a cron time.

Example crontab entry, with paths and email replaced:

```cron
0 9 * * * cd /absolute/path/to/tracker && /usr/bin/flock -n data/scrape.lock .venv/bin/python -m tracker.cli scrape --source pakwheels --limit-pages 30 --contact-email YOUR_EMAIL >> data/scrape.log 2>&1
```

Append the inspected `--model-path` options to keep the same scope each day.
`flock -n` exits instead of overlapping an existing worker. The database run guard
also prevents overlapping application runs. See the
[flock command manual](https://man7.org/linux/man-pages/man1/flock.1.html).

## Failures, interrupted processes and inactivity

`tracker status` reports counts, the last run, errors, and any unfinished run.
`tracker status --json` exposes the same fields for a local monitoring script.
Run page counters describe logical page reads, including cached reads and scope
discovery; HTTP retries and robots checks are not separate page observations.
Raw page progress survives failures, but normalized publication rolls back as a
unit. Error summaries store exception classes instead of raw HTTP responses.

If a process is killed, its run remains `running` as evidence of interruption.
First verify no worker still uses the database, then run:

```powershell
.venv/Scripts/python.exe -m tracker.cli recover-run RUN_ID
```

This marks the run interrupted; it does not fabricate normalized data. Retry the
scrape only after recovery. A normal keyboard interruption is audited directly.

Absences count only on distinct successful UTC days in the same exact source and
ordered page scope. Partial/failed/interrupted runs and same-day repeats do not
advance counters. A sighting resets absence state and reactivates the listing.
The third eligible absence creates an inactive, unknown-price marker. Because
listings can move beyond a page window, call this disappearance from the tracked
scope, never proof of a sale. Scheduling time uses local time; snapshot dates use UTC.

## Backup and restore

```powershell
.venv/Scripts/python.exe -m tracker.cli backup
.venv/Scripts/python.exe -m tracker.cli backup --destination data/backups/manual-copy.sqlite3
```

Default filenames contain a UTC timestamp. Existing destinations are never
overwritten. A backup includes both raw staging and normalized tables, including
committed WAL data. Keep a copy outside this repository for actual disaster recovery.

To restore: stop collection, back up the current database, and restore a verified
backup to a **new** database path. Inspect it with `tracker status --database PATH`
and run a manual scrape with `--database PATH` before changing the scheduled task.
Do not replace an open database or delete its journal sidecars. Keep the original
and backup until the restored copy has been checked.

Old raw staging is retained on migration. It is not silently promoted into
historical normalized runs because complete run scope and failure metadata were
not recorded then. Normalized daily history starts with the first Phase 4 run.

Future weekly analyze/export/publication work belongs to later phases. Do not
commit databases, raw caches, journal files, logs, backups, credentials or tokens.
