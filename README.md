# AetherQore POS

AI-assisted pharmacy operating system: inventory, purchasing, receiving, point of sale, returns, reports, and an operations copilot.

The Next.js app is the pharmacist UI. The FastAPI service is the system of record. Totals, stock, and permissions are enforced on the server.

## Architecture

```
frontend (Next.js 16)  →  REST + JWT  →  backend (FastAPI)
                                           │
                                           ├─ app/core        config, db, auth, RBAC
                                           ├─ app/models      SQLAlchemy models
                                           ├─ app/modules     domain routers + services
                                           └─ app/ai          optional copilot
```

- Business logic lives in `backend/app/modules/`.
- Routers authenticate, authorize, and call services.
- Inventory never changes without a `stock_movements` row.
- Sales and receiving run in a single database transaction.
- AI is optional. Without `AI_API_KEY` the copilot still answers from live queries.

## Tech stack

| Layer | Stack |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind 4 |
| Backend | FastAPI, SQLAlchemy 2, Alembic, Pydantic, JWT |
| Database | SQLite on a single Windows PC. PostgreSQL 16 (Docker Compose) for future multi-user |
| Auth | bcrypt passwords, access + refresh tokens, permission RBAC |

## Folder structure

```
aetherOS/
├── .github/workflows/
├── backend/
│   ├── alembic/
│   ├── app/
│   │   ├── ai/
│   │   ├── core/
│   │   ├── models/
│   │   ├── modules/          # auth, users, inventory, sales, purchases, …
│   │   ├── main.py
│   │   └── serve.py          # python -m app serve
│   ├── tests/
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/
│   ├── public/assets/
│   ├── src/
│   │   ├── app/              # Next.js routes (thin)
│   │   ├── components/ui/
│   │   ├── features/         # auth, command-center, inventory, pos, purchases, ai-copilot
│   │   ├── layouts/AppShell.tsx
│   │   └── lib/api/
│   └── package.json
├── deploy/windows/           # one-click start / stop / backup / install
├── docs/WINDOWS_INSTALL.md
├── docker-compose.yml
└── README.md
```

The UI stays on Next.js App Router. Feature pages live under `frontend/src/features`; route files in `frontend/src/app` re-export them.

## Setup

### 1. Database

```bash
docker compose up -d postgres
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit SECRET_KEY in .env
alembic upgrade head
python seed.py
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 3. Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

From the repo root you can also run `npm run dev`, which proxies into `frontend/`.

UI: http://localhost:3000

### SQLite instead of Docker

Set in `backend/.env`:

```
DATABASE_URL=sqlite:///./aetherqore.db
```

Then `alembic upgrade head` and `python seed.py` as above.

## Windows pharmacy PC (offline after install)

First real installation is a **local production web app**, not a cloud deploy and not Electron/Tauri.

See [docs/WINDOWS_INSTALL.md](docs/WINDOWS_INSTALL.md) for hardware, one-click start, backups, and first login.

```powershell
cd deploy\windows
.\install.ps1
# then double-click the AetherQore desktop shortcut
```

Live SQLite, backups, and logs live in `%LOCALAPPDATA%\AetherQore\`, not in the git folder.

Production API: `python -m app serve` (migrates, binds `127.0.0.1`, no `--reload`).
Production UI: `npm run build` then `npm run start -- -H 127.0.0.1 -p 3000`.

## Environment variables

See [backend/.env.example](backend/.env.example) and [frontend/.env.example](frontend/.env.example).

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy URL |
| `SECRET_KEY` | JWT signing key |
| `CORS_ORIGINS` | Comma-separated frontend origins |
| `AI_PROVIDER` / `AI_API_KEY` | Optional OpenAI-compatible copilot |
| `NEXT_PUBLIC_API_URL` | Frontend → backend base URL |

Never commit `.env` files.

## Seed credentials

| Role | Email | Password |
| --- | --- | --- |
| Admin | amara@brightcare.pharmacy | pharmacy123 |
| Pharmacist | grace@brightcare.pharmacy | pharmacy123 |
| Cashier | lena@brightcare.pharmacy | pharmacy123 |

# Commands
```bash
# backend tests
cd backend && .venv/bin/pytest -q

# frontend typecheck
cd frontend && npx tsc --noEmit

# production-local API (after init-config)
cd backend && python -m app serve

# migrations
cd backend && python -m app migrate
# or: alembic upgrade head

# seed demo catalog (training only)
cd backend && python seed.py
```

## Receiving invoices

Upload a CSV with columns `name,quantity,unit_cost,batch,expiry`.
A sample file is at [backend/fixtures/sample-invoice.csv](backend/fixtures/sample-invoice.csv).
If `AI_PROVIDER` and `AI_API_KEY` are set, free-form invoices can be extracted through the same endpoint.

## Decision notes

- The existing Next.js UI was kept (not rewritten to Vite). The spec’s Flask stack was implemented as FastAPI, which matches the requested Python/Pydantic/Alembic/JWT backend more closely than Flask while staying a single service.
- Offline: POS cart is persisted in `localStorage` and sales send an idempotency key. Full multi-device offline sync is an extension point, not faked. `backend/app/modules/sync` and `finance` are reserved packages. A single Windows PC running SQLite locally is the supported first install; see [docs/WINDOWS_INSTALL.md](docs/WINDOWS_INSTALL.md).
