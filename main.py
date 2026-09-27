import os
import json
import asyncio
from datetime import datetime
from typing import Annotated
from fastapi import FastAPI, Request, HTTPException, Response, Depends
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, StringConstraints
from services.monitor import start_background_services
from core.db import db
from core.logger import smart_log
from core.config import tracked_hashes
from core.api import fetch_fountain_data
from core.processor import (
    get_all_cached_for_editathon,
    get_banned_users,
    get_jury_stats_core,
    get_daily_stats_core,
    process_word_counts_async
)
from core.auth import get_password_hash, verify_password, create_access_token, get_current_user

db.init_db(tracked_hashes)

def ensure_admin():
    # First admin comes from the environment only; no credentials live in the code.
    with db as conn:
        if conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]: return
        user, password = os.getenv("ADMIN_USER"), os.getenv("ADMIN_PASS")
        if not (user and password):
            smart_log("[Auth] No admin account: set ADMIN_USER and ADMIN_PASS to create one", "ERROR")
            return
        conn.execute("INSERT INTO admins (username, password_hash) VALUES (?, ?)", (user, get_password_hash(password)))
    smart_log(f"[Auth] Created admin user from environment: {user}")

ensure_admin()

app = FastAPI()
start_background_services()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server; production is same-origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CodeReq(BaseModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

# Admin APIs
@app.post("/api/admin/login")
async def admin_login(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    try:
        with db as conn:
            row = conn.execute("SELECT password_hash FROM admins WHERE username = ?", (form_data.username,)).fetchone()
            if not row or not verify_password(form_data.password, row[0]):
                raise HTTPException(status_code=401, detail="Invalid username or password")
            if not row[0].startswith("scrypt$"):  # upgrade legacy SHA-256 hash
                conn.execute("UPDATE admins SET password_hash = ? WHERE username = ?", (get_password_hash(form_data.password), form_data.username))
            token = create_access_token({"sub": form_data.username})

            # Determine if we should set secure cookie based on protocol
            is_secure = request.headers.get("x-forwarded-proto", "http") == "https" or request.url.scheme == "https"

            response.set_cookie(
                key="admin_token",
                value=token,
                httponly=True,
                max_age=60 * 60 * 24 * 7,
                samesite="strict",
                secure=is_secure
            )
            return {"access_token": token, "token_type": "bearer"}
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/check-auth")
async def check_auth(user: str = Depends(get_current_user)):
    return {"status": "authenticated", "user": user}

@app.post("/api/admin/logout")
async def logout(response: Response):
    response.delete_cookie("admin_token")
    return {"status": "ok"}

@app.get("/api/admin/participants/{code}")
def get_participants(code: str, user: str = Depends(get_current_user)):
    f_data = fetch_fountain_data(code)
    participants = {art.get("user") for art in f_data.get("articles", []) if art.get("user")}
    banned = set(get_banned_users(code))
    return {"participants": sorted([{"username": u, "isBanned": u in banned} for u in participants], key=lambda x: x["username"].lower())}

@app.post("/api/admin/ban")
async def ban_user(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    code, target_user = data.get("code"), data.get("username")
    if not code or not target_user: raise HTTPException(status_code=400, detail="Missing code or username")
    try:
        with db as conn:
            conn.execute("INSERT OR IGNORE INTO banned_users (editathon_code, username) VALUES (?, ?)", (code, target_user))
        return {"status": "success", "message": f"User {target_user} banned from {code}"}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/unban")
async def unban_user(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    code, target_user = data.get("code"), data.get("username")
    if not code or not target_user: raise HTTPException(status_code=400, detail="Missing code or username")
    try:
        with db as conn:
            conn.execute("DELETE FROM banned_users WHERE editathon_code = ? AND username = ?", (code, target_user))
        return {"status": "success", "message": f"User {target_user} unbanned from {code}"}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

# Every recent bn Fountain contest is tracked automatically (services/monitor.sync_contest_list).
def ensure_enabled_editathon(code: str):
    with db as conn:
        row = conn.execute("SELECT 1 FROM enabled_editathons WHERE code = ?", (code,)).fetchone()
        if not row:
            raise HTTPException(status_code=403, detail=f"Editathon {code} is not a tracked Bengali contest")

@app.get("/api/editathons")
def get_editathons():
    with db as conn:
        rows = conn.execute("SELECT code, name, wiki, site_url FROM enabled_editathons ORDER BY finish DESC").fetchall()
    return {"editathons": [{"code": r[0], "name": r[1], "wiki": r[2], "site_url": r[3]} for r in rows]}

# Plain `def` endpoints: FastAPI runs them in its threadpool, so blocking fetches are fine here.
@app.post("/api/jury_stats")
def jury_stats(req: CodeReq):
    sorted_juries, conflicts = get_jury_stats_core(fetch_fountain_data(req.code))
    return {"raw": {"stats": sorted_juries, "conflicts": conflicts}}

@app.post("/api/rejected_articles")
def rejected_articles(req: CodeReq):
    f_data = fetch_fountain_data(req.code)
    return {"rejected_articles": [
        art.get("name") for art in f_data.get("articles", [])
        if any(r.get("marks", {}).get("0") in [1, 2] for r in art.get("marks", []))
    ]}

@app.post("/api/daily_stats")
def daily_stats(req: CodeReq):
    return get_daily_stats_core(fetch_fountain_data(req.code), get_all_cached_for_editathon(req.code))

@app.post("/api/count_words")
async def count_words(req: CodeReq):
    ensure_enabled_editathon(req.code)
    q = asyncio.Queue()
    asyncio.create_task(process_word_counts_async(req.code, q, source="UI"))
    async def generate():
        try:
            while True:
                item = await q.get()
                if item == "DONE": break
                yield json.dumps(item) + "\n"
        except Exception as e: yield json.dumps({"error": str(e)}) + "\n"
    return StreamingResponse(generate(), media_type="application/x-ndjson")

app.mount("/", StaticFiles(directory="static", html=True), name="static")

# SPA fallback: any non-API path (e.g. /admin, /admin/dashboard) serves the React app.
@app.exception_handler(404)
async def not_found(request: Request, exc: HTTPException):
    if not request.url.path.startswith("/api"): return FileResponse("static/index.html")
    return JSONResponse(status_code=404, content={"detail": "Not Found"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
