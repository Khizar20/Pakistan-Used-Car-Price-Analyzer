# Daily operation

The worker collects Karachi, Lahore, Islamabad and Rawalpindi at **09:00
Asia/Karachi**. Observed city paths are pinned in `tracker.daily.CITY_PATHS`.
40 total search pages means ten per city; at most 60 new detail pages are fetched
per run. This is a bounded search window, not a census. Collection honors robots,
host rate limits and blocking. Source permission is required for automation and
photo reuse; the operator confirmed permission for this workstation.

## Configure and install on Windows

Use Python 3.10 and run `make check`. Create ignored `data/daily/config.json`
using your contact email and actual permission status:

```json
{
  "contact_email": "research@example.com",
  "source_permission_confirmed": true,
  "limit_pages": 40,
  "max_new_details": 60
}
```

Preview, then install the current-user task in PowerShell:

```powershell
powershell -NoProfile -File scripts/install_daily_task.ps1 -Preview
powershell -NoProfile -File scripts/install_daily_task.ps1
Get-ScheduledTask -TaskName 'Pakistan Used Car Tracker - Daily'
```

The installer requires Windows **Pakistan Standard Time**, runs with limited
privileges, prevents overlapping instances and catches missed runs at logon
after 09:00. Earlier logons wait for the daily trigger instead of preempting it.
The computer must be on, network available, and this user logged on. It cannot
collect while powered off. It uses the venv's Python windowless launcher to
avoid opening a console and stores no account passwords.

Run the same workflow manually:

```powershell
.venv/Scripts/python.exe -m tracker.cli refresh --config data/daily/config.json
.venv/Scripts/python.exe -m tracker.cli status
Get-Content data/daily/status.json
```

The worker uses an OS-released lock, backs up the database, collects, then exports
eight validated dashboard files. Large city comparisons are split losslessly into
hash-addressed JSON parts, each below 500 KB. The browser verifies their hashes,
schemas and bundle identity before displaying them. Failed collection does not
export. It retains seven automatic backups and preserves manual backups. One successful refresh per
Pakistan date/configuration is enough; `--force` permits a deliberate rerun.
Snapshot uniqueness uses UTC dates.

`data/daily/status.json` records progress, last success and photo-queue status.
Private step logs are in the same directory. Failed photo collection does not
discard a successful price refresh. Reload the dashboard or click **Refresh data**
after export. The job updates local files; it does not push or deploy Pages.

## Model photos

Collection retains allowlisted thumbnail references from observed vehicle cards.
The daily worker queues at most twelve previously unseen model references in
ignored `raw/photos`, with robots checks, rate limits, a 2 MB cap, format/dimension
validation and metadata rejection. Unchecked photos are never published. No seller
text, full-size galleries or external image URLs enter public exports.

```powershell
.venv/Scripts/python.exe -m tracker.cli photos --contact-email research@example.com
Get-Content raw/photos/candidates.json
.venv/Scripts/python.exe -m tracker.cli approve-photo SHA256_FROM_CANDIDATES
```

Inspect the actual candidate image for people, contact details, registration
plates and exact addresses before approval. Reject unsafe candidates. Approved
files are copied unchanged under content-hash filenames into
`web/public/images/cars`; `web/src/data/carPhotos.json` maps reviewed model photos.
The UI labels them as example listing photos via PakWheels with permission and
notes that year/trim/condition may differ. Failed/unavailable images are omitted.
Remove a rejected model's entry from the private candidate index to queue an
alternative next time. Public photo changes require a new frontend build.

## Failures and recovery

`tracker status --json` reports database run state. If a process was killed, first
verify no scraper is running, then explicitly recover the unfinished run:

```powershell
.venv/Scripts/python.exe -m tracker.cli recover-run RUN_ID
.venv/Scripts/python.exe -m tracker.cli refresh --config data/daily/config.json --force
```

Partial/failed/interrupted runs never advance disappearance counters. Absences
count only on distinct successful UTC days with the same exact ordered page
scope; reappearance resets them. A third eligible absence means disappearance
from this bounded window, not proof of sale. Changing budgets starts a different
scope. Never bypass an access denial or challenge.

For manual backups use `tracker backup --destination data/backups/manual.sqlite3`.
Backups include raw/normalized tables and committed WAL data. Restore to a new
database path while collection is stopped; inspect and test it before switching.
Retain the original and keep an off-machine backup too.

On Linux use a native Python 3.10 venv and a 09:00 local cron invoking
`.venv/bin/python -m tracker.cli refresh --config data/daily/config.json` from the
repository. The worker provides locking; confirm the host timezone separately.
Git commands use WSL Ubuntu. No scheduler needs a GitHub token. Never commit
private settings, raw files, databases, logs, backups or credentials.
