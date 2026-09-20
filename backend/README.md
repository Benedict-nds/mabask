# AetherQore backend

FastAPI system of record. Domain code lives in `app/modules`; shared infrastructure in `app/core`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python seed.py
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs
