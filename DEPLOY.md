# Deploy Beaver (about 30 minutes)

## 0. Database (once)
In the Supabase SQL editor run, in order: `schema.sql`, `schema_task2.sql`, `schema_task3.sql`.
Make yourself admin: `update public.profiles set is_admin = true where email = 'you@example.com';`

## 1. Backend on Render
1. Render -> New -> Blueprint -> pick this GitHub repo (it reads `render.yaml`). Or New Web Service: root dir `backend`, build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`.
2. Paste the environment variables when asked: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`, `BACKUP_API_KEY` (a free Groq key works), and `FRONTEND_ORIGIN` (fill in after step 2; no trailing slash).
3. Open `https://<your-service>.onrender.com/health` -> `{"status":"ok"}`.

## 2. Frontend on Vercel
1. Vercel -> Add New Project -> same repo. Root directory `frontend`. Framework: Vite (build `npm run build`, output `dist`). `vercel.json` already makes page refreshes work.
2. Environment variables: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (anon key only!), `VITE_API_URL` = your Render address (no trailing slash).
3. Deploy. Copy the Vercel address (e.g. `https://beaver.vercel.app`).

## 3. Connect them
- Render: set `FRONTEND_ORIGIN` to the Vercel address. This is the only origin CORS allows. Redeploy.
- Supabase -> Authentication -> URL Configuration: Site URL = Vercel address; add it (and `http://localhost:5173`) to Redirect URLs.
- Google Cloud -> your OAuth client: add the Vercel address to Authorised JavaScript origins. (The Supabase callback URL stays as it was.)

## 4. Smoke test on the live site
- [ ] Sign up with email and with Google; both land on Home
- [ ] Upload an .xlsx, see "N sheets found"; a file over 10 MB is refused with a clear message
- [ ] Ask: total inventory value, low stock, "compare sales to last month"; numbers match Excel
- [ ] Ask a projection question: "Projections are coming soon"
- [ ] History reopens an answer and the question counter does not go up
- [ ] Refresh on /history works (no 404); install to phone/laptop; both themes look right
- [ ] Non-admin account: /admin redirects home and `GET /admin/overview` returns 403
- [ ] Bad Gemini key on Render: questions still answer (backup provider or rules)
