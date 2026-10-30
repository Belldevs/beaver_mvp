import logging
import os
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote

import httpx
from pathlib import Path

from dotenv import load_dotenv

# Load .env from this file's own folder, no matter where the server is started from.
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import answer  # noqa: E402
import db  # noqa: E402
from parsing import ParseError, parse_file, to_parquet_bytes  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("beaver")

LIMIT_BYTES = 10 * 1024 * 1024  # 10 MB total per user
BUCKET = "sheets"

app = FastAPI(title="Beaver API", version="0.3.0")

# CORS: allow only your own frontend address.
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(db.SupabaseError)
def supabase_error_handler(_request, exc: db.SupabaseError):
    return JSONResponse(status_code=502, content={"detail": f"Storage problem: {exc} Please try again."})


@app.get("/health")
def health():
    return {"status": "ok", "service": "beaver-api"}


# ------------------------------------------------------------------ helpers
def current_user(authorization: str = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please log in.")
    uid = db.get_user_id(authorization[7:].strip())
    if not uid:
        raise HTTPException(401, "Your session has expired. Please log in again.")
    return uid


def active_user(uid: str = Depends(current_user)) -> str:
    """Logged in AND not suspended. Also records last activity."""
    p = db.select("profiles", {"select": "suspended", "id": f"eq.{uid}"})
    if p and p[0].get("suspended"):
        raise HTTPException(403, "Your account is suspended. Please contact support.")
    db.update("profiles", {"id": f"eq.{uid}"}, {"last_active_at": datetime.now(timezone.utc).isoformat()})
    return uid


def admin_user(uid: str = Depends(current_user)) -> str:
    p = db.select("profiles", {"select": "is_admin", "id": f"eq.{uid}"})
    if not p or not p[0].get("is_admin"):
        raise HTTPException(403, "Not allowed.")
    return uid


def mb(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB"


def used_bytes(uid: str) -> int:
    rows = db.select("files", {"select": "size_bytes", "user_id": f"eq.{uid}"})
    return sum(int(r["size_bytes"]) for r in rows)


def too_big(size, remaining: int) -> HTTPException:
    if size:
        msg = f"This file is {mb(size)} but you only have {mb(remaining)} left of your 10 MB."
    else:
        msg = f"This file is bigger than the {mb(remaining)} you have left of your 10 MB."
    return HTTPException(413, msg + " Delete a file on the Sheets tab to free up space.")


def ingest(uid: str, filename: str, source: str, data: bytes) -> dict:
    """Parse, store each sheet as Parquet, save profile cards. Nothing is saved if parsing fails."""
    try:
        parsed = parse_file(data, filename)
        parquets = [to_parquet_bytes(p.df) for p in parsed]
    except ParseError as e:
        raise HTTPException(422, str(e))

    file_row = db.insert("files", {"user_id": uid, "name": filename, "source": source, "size_bytes": len(data)})
    uploaded: list[str] = []
    out_sheets = []
    try:
        for p, pq in zip(parsed, parquets):
            sheet_id = str(uuid.uuid4())
            path = f"{uid}/{file_row['id']}/{sheet_id}.parquet"
            db.storage_upload(BUCKET, path, pq, "application/octet-stream")
            uploaded.append(path)
            db.insert("sheets", {"id": sheet_id, "file_id": file_row["id"], "user_id": uid, "name": p.name,
                                 "storage_path": path, "row_count": p.profile["row_count"], "profile": p.profile})
            out_sheets.append({"id": sheet_id, "name": p.name, "row_count": p.profile["row_count"],
                               "mapped_fields": p.profile["mapped_fields"]})
    except Exception:
        log.exception("ingest failed; cleaning up")
        try:
            db.storage_delete(BUCKET, uploaded)
            db.delete("files", {"id": f"eq.{file_row['id']}"})
        except Exception:
            log.exception("cleanup failed")
        raise

    currency = next((p.profile["currency"] for p in parsed if p.profile["currency"]), None)
    return {"file": {"id": file_row["id"], "name": filename, "size_bytes": len(data)},
            "sheets": out_sheets, "detected_currency": currency}


# ------------------------------------------------------------------ routes
@app.post("/files/upload")
def upload_file(file: UploadFile = File(...), uid: str = Depends(active_user)):
    filename = os.path.basename(file.filename or "").strip()
    if not filename.lower().endswith((".xlsx", ".csv")):
        raise HTTPException(415, "Only .xlsx and .csv files are supported.")
    remaining = LIMIT_BYTES - used_bytes(uid)
    if remaining <= 0:
        raise HTTPException(413, "You've used all 10 MB. Delete a file on the Sheets tab to free up space.")
    if file.size is not None and file.size > remaining:
        raise too_big(file.size, remaining)
    data = file.file.read(remaining + 1)  # never read more than the user has room for
    if len(data) > remaining:
        raise too_big(None, remaining)
    if not data:
        raise HTTPException(400, "That file is empty.")
    return ingest(uid, filename, "upload", data)


class SheetLink(BaseModel):
    url: str


@app.post("/files/google-sheet")
def add_google_sheet(body: SheetLink, uid: str = Depends(active_user)):
    m = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", body.url)
    if not m:
        raise HTTPException(400, "That doesn't look like a Google Sheets link. Copy it from the browser address bar.")
    sheet_id = m.group(1)
    remaining = LIMIT_BYTES - used_bytes(uid)
    if remaining <= 0:
        raise HTTPException(413, "You've used all 10 MB. Delete a file on the Sheets tab to free up space.")

    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    not_public = HTTPException(400, 'Beaver couldn\'t open that sheet. Share it as "Anyone with the link can view" and try again.')
    try:
        with httpx.Client(follow_redirects=True, timeout=30) as c, c.stream("GET", export_url) as r:
            if r.status_code != 200:
                raise not_public
            chunks, total = [], 0
            for chunk in r.iter_bytes():
                total += len(chunk)
                if total > remaining:
                    raise too_big(None, remaining)
                chunks.append(chunk)
            disposition = r.headers.get("content-disposition", "")
    except httpx.HTTPError:
        raise HTTPException(502, "Couldn't reach Google Sheets. Please try again.")
    data = b"".join(chunks)
    if data[:2] != b"PK":  # a login page (HTML) instead of a spreadsheet
        raise not_public

    name = f"Google Sheet {sheet_id[:6]}.xlsx"
    star = re.search(r"filename\*=UTF-8''([^;]+)", disposition)
    plain = re.search(r'filename="([^"]+)"', disposition)
    if star:
        name = unquote(star.group(1))
    elif plain:
        name = plain.group(1)
    if not name.lower().endswith(".xlsx"):
        name += ".xlsx"
    return ingest(uid, name, "google_sheet", data)


@app.delete("/files/{file_id}")
def delete_file(file_id: str, uid: str = Depends(current_user)):
    try:
        uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(400, "Invalid file id.")
    if not db.select("files", {"select": "id", "id": f"eq.{file_id}", "user_id": f"eq.{uid}"}):
        raise HTTPException(404, "File not found.")
    sheets = db.select("sheets", {"select": "storage_path", "file_id": f"eq.{file_id}", "user_id": f"eq.{uid}"})
    db.storage_delete(BUCKET, [s["storage_path"] for s in sheets if s["storage_path"]])
    db.delete("files", {"id": f"eq.{file_id}", "user_id": f"eq.{uid}"})  # sheets rows cascade
    return {"deleted": file_id}


# ------------------------------------------------------------------ ask
class Question(BaseModel):
    question: str


@app.post("/ask")
def ask(body: Question, uid: str = Depends(active_user)):
    prof = db.select("profiles", {"select": "questions_used,currency", "id": f"eq.{uid}"})
    if not prof:
        raise HTTPException(404, "Profile not found. Please log out and back in.")
    return answer.ask(uid, prof[0], body.question)


# ------------------------------------------------------------------ admin (checked here, not just hidden in the UI)
STORAGE_LIMIT = int(os.getenv("STORAGE_LIMIT_BYTES", str(1_000_000_000)))  # Supabase free plan: 1 GB


@app.get("/admin/overview")
def admin_overview(_: str = Depends(admin_user)):
    profiles = db.select("profiles", {"select": "id,email,is_admin,questions_used,suspended,last_active_at,created_at",
                                      "order": "created_at.desc", "limit": "1000"})
    files = db.select("files", {"select": "user_id,size_bytes", "limit": "20000"})
    per: dict = {}
    for f in files:
        per[f["user_id"]] = per.get(f["user_id"], 0) + int(f["size_bytes"])
    total = sum(per.values())
    return {"users": [{**p, "storage_bytes": per.get(p["id"], 0)} for p in profiles],
            "storage_used_bytes": total, "storage_limit_bytes": STORAGE_LIMIT,
            "questions_today": answer.questions_today(), "global_daily_cap": answer.GLOBAL_DAILY_CAP}


class Suspend(BaseModel):
    suspended: bool


@app.post("/admin/users/{user_id}/suspend")
def admin_suspend(user_id: str, body: Suspend, admin: str = Depends(admin_user)):
    try:
        uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user id.")
    if user_id == admin:
        raise HTTPException(400, "You can't suspend your own account.")
    db.update("profiles", {"id": f"eq.{user_id}"}, {"suspended": body.suspended})
    return {"id": user_id, "suspended": body.suspended}
