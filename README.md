# Beaver

Ask your spreadsheets anything. Vue 3 PWA (Vercel) + FastAPI (Render) + Supabase.

## Run locally

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```
Check: http://localhost:8000/health returns `{"status":"ok",...}`

**Frontend**
```bash
cd frontend
cp .env.example .env     # fill in VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY
npm install
npm run dev
```
Open http://localhost:5173

**Database**: in the Supabase SQL editor run `supabase/schema.sql`, then `supabase/schema_task2.sql` (each once).

**Backend tests**: `cd backend && python test_parsing.py`

## Blank white page?
1. Open the browser console (F12). A message about `VITE_SUPABASE_URL` means `frontend/.env` is missing or wrongly named (must be exactly `.env`, inside `frontend/`, not `.env.example` or `.env.txt`).
2. Restart `npm run dev` after any `.env` change.
3. Beaver now shows a red "couldn't start" box with the reason instead of a blank page.
