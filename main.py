import os
import json
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import StreamingResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import fountain
from auth_fastapi import auth_router
import requests

load_dotenv()

app = FastAPI()

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], # Vite default
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "ztools_permanent_secret_123"),
    session_cookie="ztools_session",
)

# Include Auth Router
app.include_router(auth_router, prefix="/api")

@app.get("/api/editathons")
async def get_editathons():
    try:
        result = fountain.get_bn_editathons()
        return {"editathons": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fetch_articles")
async def fetch_articles(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
    try:
        user_articles, site_url = fountain.get_articles_data(code)
        return {"articles": user_articles, "site_url": site_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/jury_stats")
async def jury_stats(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
    try:
        sorted_juries, wikitable = fountain.get_jury_stats_data(code)
        return {"raw": sorted_juries, "wikitable": wikitable}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rejected_articles")
async def rejected_articles(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
    try:
        rejected_articles, wikitable = fountain.get_rejected_articles_data(code)
        return {"rejected_articles": rejected_articles, "wikitable": wikitable}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/count_words")
async def count_words(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")

    async def generate():
        try:
            # fountain.get_word_counts is a generator
            for chunk in fountain.get_word_counts(code):
                yield json.dumps(chunk) + "\n"
        except Exception as e:
            yield json.dumps({"error": str(e)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")

@app.post("/api/user_reviews")
async def user_reviews(request: Request):
    username = request.session.get('username')
    if not username:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    data = await request.json()
    code = data.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
    try:
        reviews, site_url = fountain.get_user_reviews(code, username)
        return {"reviews": reviews, "site_url": site_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jury_editathons")
async def jury_editathons(request: Request):
    username = request.session.get('username')
    if not username:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        result = fountain.get_user_jury_editathons(username)
        return {"editathons": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve static files for the React frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.exception_handler(404)
async def not_found(request: Request, exc: HTTPException):
    # SPA fallback: return index.html for all non-API 404s
    if not request.url.path.startswith("/api"):
        return FileResponse("static/index.html")
    return JSONResponse(status_code=404, content={"detail": "Not Found"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
