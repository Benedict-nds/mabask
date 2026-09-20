# AetherQore Windows desktop installation

This guide is for a technician installing AetherQore on **one Windows pharmacy PC** that will run **without internet** after setup.

Do not deploy this first installation to Vercel, Render, AWS, or any other cloud host.

## Recommended architecture

Use a **local production web app with a one-click launcher** (option A).

Keep the current Next.js UI and FastAPI API. On the pharmacy PC they bind only to `127.0.0.1`:

| Process | URL | How it starts |
| --- | --- | --- |
| FastAPI | http://127.0.0.1:8000 | `python -m app serve` (no `--reload`) |
| Next.js production server | http://127.0.0.1:3000 | `npm run start -- -H 127.0.0.1 -p 3000` |
| Browser | http://127.0.0.1:3000 | opened by the Start shortcut |

**Do not wrap this first install in Electron or Tauri.** A desktop wrapper would add another runtime, another updater, and a large rewrite risk. Revisit a packaged `.exe` later if you need a single binary; the current launcher preserves the working architecture.

PostgreSQL remains the future multi-user option. This first site uses **SQLite** in a stable application-data folder.

## What must be true after install

- The pharmacist double-clicks **AetherQore** on the desktop.
- Backend and frontend start, the script waits until both respond, then Edge/Chrome opens `http://127.0.0.1:3000`.
- Login, inventory, batches, expiry, FEFO sales, purchasing, CSV receiving, suppliers, POS, local payments, receipts, returns, reports, dashboard, audit, and users work **offline**.
- Cloud AI is optional. With no `AI_API_KEY`, the app still starts. Copilot answers from the local database only.

## Hardware and Windows

| Item | Minimum | Notes |
| --- | --- | --- |
| OS | Windows 10 22H2 or Windows 11 | 64-bit |
| CPU | Dual-core | Any recent Intel/AMD |
| RAM | 8 GB | 16 GB is more comfortable |
| Disk | 10 GB free | SSD preferred |
| Display | 1366×768 | 1920×1080 preferred |
| Network | Not required at run time | Needed once to install Python, Node, and npm packages |

A printer for receipts can be the Windows default printer. There is no cloud payment gateway; tenders are recorded locally.

## Runtime dependencies (install while the PC can reach the internet)

1. **Python 3.11 or 3.12** (3.13 is fine) from [python.org](https://www.python.org/downloads/windows/). Tick **Add python.exe to PATH**.
2. **Node.js 20 LTS** from [nodejs.org](https://nodejs.org/). This includes `npm`.
3. Copy the AetherQore project folder to a stable path, for example `C:\AetherQore\aetherOS`. Avoid Desktop if OneDrive will move it.

The first `pip install` and `npm install` / `npm run build` need internet. After that, core pharmacy work does not.

## Data directory

Live data is **not** stored in the source tree.

```
%LOCALAPPDATA%\AetherQore\
  config\app.env              production settings (SECRET_KEY lives here)
  config\FIRST_LOGIN.txt      first admin password (delete after first login)
  data\aetherqore.db          live SQLite database
  data\aetherqore.db-wal      WAL sidecar (normal)
  backups\aetherqore-*.db     verified rotating backups
  logs\aetherqore.log         API log
  logs\backend.*.log         process stdout/stderr
  logs\frontend.*.log
  uploads\                    reserved for future file uploads
  run\*.pid                   process ids for stop/restart
```

Override the location with the `AETHERQORE_HOME` environment variable if you need the data on another drive.

## Installation steps

Open PowerShell **in the project folder** (or right-click `deploy\windows\install.ps1` → Run with PowerShell):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
cd C:\AetherQore\aetherOS\deploy\windows
.\install.ps1
```

The installer will:

1. Create `backend\.venv` and install Python packages.
2. Run `npm install` and `npm run build` in `frontend` with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`.
3. Generate a strong `SECRET_KEY` into `%LOCALAPPDATA%\AetherQore\config\app.env`.
4. Set `ENVIRONMENT=production`, `DEBUG=false`, localhost CORS, SQLite in the data folder, and empty AI keys.
5. Run Alembic migrations (`python -m app migrate`).
6. Create roles, default settings, a Walk-in customer, and the first admin (`python -m app bootstrap`).
7. Place **AetherQore** and **Stop AetherQore** shortcuts on the desktop.

It will **not** load BrightCare demo medicines. Add the real catalog in Inventory after login. To load sample data on a training PC only:

```powershell
cd C:\AetherQore\aetherOS\backend
.\.venv\Scripts\python.exe seed.py
```

Do not run `seed.py` against a live pharmacy that already has real stock.

## Environment configuration

Edit `%LOCALAPPDATA%\AetherQore\config\app.env` if you need to change the pharmacy name or token lifetime. Never commit this file.

Important keys:

| Key | Production-local value |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `SECRET_KEY` | generated; not a development placeholder |
| `DATABASE_URL` | SQLite file under `data\` |
| `HOST` / `PORT` | `127.0.0.1` / `8000` |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` |
| `AI_PROVIDER` / `AI_API_KEY` | empty for offline |

The frontend URL baked into the production build is `http://127.0.0.1:8000` (`frontend/.env.production`). Rebuild the frontend if that URL must change.

## First startup

Double-click **AetherQore** on the desktop.

That runs `deploy\windows\start.ps1`, which:

1. Stops any previous backend/frontend on ports 8000 and 3000.
2. Starts FastAPI with `python -m app serve` (migrates, bootstraps if needed, writes a daily backup, **no reload**).
3. Starts `next start` on `127.0.0.1:3000`.
4. Waits for `http://127.0.0.1:8000/health` and the UI.
5. Opens the default browser.

Health example: `{"status":"ok","database":"ok","ai":{"enabled":false,"mode":"local-data"}}`.

## First login

Open `%LOCALAPPDATA%\AetherQore\config\FIRST_LOGIN.txt` for the generated admin email and password (or the values you typed during install).

Sign in at http://127.0.0.1:3000. Then:

1. Settings → pharmacy name, license, phone, tax.
2. Users → create pharmacist and cashier accounts. Do not keep using the generated password.
3. Delete `FIRST_LOGIN.txt`.
4. Inventory → add medicines and opening batches.

## Daily use

- **Start:** desktop **AetherQore**
- **Stop:** desktop **Stop AetherQore** (or `deploy\windows\Stop-AetherQore.bat`)
- **Restart:** Stop, then Start. The start script kills duplicates first.
- **Manual backup:** `deploy\windows\Backup-AetherQore.bat`

A rotating SQLite backup is also written on each successful backend start (one per UTC day, last 14 kept).

## Backup and restore

Backups use SQLite’s backup API (safe with WAL). They are **not** a raw copy of a locked file.

Location: `%LOCALAPPDATA%\AetherQore\backups\aetherqore-YYYYMMDD-HHMMSS.db`

Verify a file:

```powershell
cd C:\AetherQore\aetherOS\backend
$env:AETHERQORE_HOME="$env:LOCALAPPDATA\AetherQore"
.\.venv\Scripts\python.exe -m app verify
.\.venv\Scripts\python.exe -m app verify "C:\path\to\aetherqore-20260915-120000.db"
```

Restore (AetherQore must be stopped):

```powershell
cd C:\AetherQore\aetherOS\deploy\windows
.\restore.ps1 -BackupFile "$env:LOCALAPPDATA\AetherQore\backups\aetherqore-20260915-120000.db"
```

Then start AetherQore again. Confirm a known sale or product still exists.

Copy the `backups` folder to an external USB weekly.

## Update procedure

1. Stop AetherQore.
2. Backup (`Backup-AetherQore.bat`) and copy that file off the PC.
3. Replace the application folder with the new source (keep `%LOCALAPPDATA%\AetherQore` untouched).
4. Run `install.ps1` again (venv + `npm run build` + migrate). Existing `app.env` and the database are not overwritten by `init-config`.
5. Start AetherQore and smoke-test login, a sale, and inventory.

## Commands (technician)

From `backend\` with the venv active, after `AETHERQORE_HOME` is set:

```text
python -m app init-config   # generate app.env and SECRET_KEY
python -m app migrate       # alembic upgrade head
python -m app bootstrap     # RBAC + first admin if missing
python -m app serve         # production API on 127.0.0.1:8000
python -m app backup
python -m app restore PATH
python -m app verify [PATH]
```

Frontend production:

```text
cd frontend
npm run build
npm run start -- -H 127.0.0.1 -p 3000
```

Do not use `npm run dev` or `uvicorn --reload` on the pharmacy PC.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Shortcut does nothing | Right-click → Run with PowerShell on `start.ps1`. Read the error. |
| Browser shows cannot connect | `%LOCALAPPDATA%\AetherQore\logs\backend.err.log` and `frontend.err.log` |
| `SECRET_KEY must be set` | `config\app.env` missing or still a placeholder. Re-run `python -m app init-config` only if the file is absent. |
| Port already in use | Stop AetherQore, or close another app using 3000/8000. |
| Frontend 404 on refresh | `next start` is not running; the production server is required for deep links. |
| Login fails after restore | Restore a backup from *this* pharmacy. A different `SECRET_KEY` invalidates existing JWT cookies only; passwords are in the database. |
| Copilot says cloud AI is off | Expected offline. Local stock/sales answers still work. |
| CSV receive works, photo invoice does not | Expected offline. Use CSV columns `name,quantity,unit_cost,batch,expiry`. |

Logs:

- `%LOCALAPPDATA%\AetherQore\logs\aetherqore.log`
- `%LOCALAPPDATA%\AetherQore\logs\backend.err.log`
- `%LOCALAPPDATA%\AetherQore\logs\frontend.err.log`

## Contact / inspect

The developer who installed the machine should keep a copy of this folder and the latest backup. There is no cloud support channel built into the product. Inspect logs in the folder above and the health URL http://127.0.0.1:8000/health while AetherQore is running.

## Remaining internet dependencies (runtime)

These are **not** required for selling or stock:

- Cloud LLM (`AI_PROVIDER` + `AI_API_KEY`) — copilot prose and free-form invoice OCR.
- Anything you later add (email, SMS, card acquirers, license servers). None of those are wired in now.

Build/install time (needs internet **once**):

- `pip install` / `npm install`
- `next build` (JavaScript tooling). Fonts are system fonts so a rebuild does not call Google Fonts.

Vercel Analytics was removed from the UI so production does not phone home.

POS cart `localStorage` survives a refresh on this PC only. There is **no multi-device offline sync**. That is still an extension point (`backend/app/modules/sync`).
