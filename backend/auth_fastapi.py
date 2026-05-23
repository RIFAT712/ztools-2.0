import os
import time
import json
import threading
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from dotenv import load_dotenv
import httpx

# Load environment variables
load_dotenv()

auth_router = APIRouter()

# --- Configuration ---
CONSUMER_KEY = os.getenv("CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("CONSUMER_SECRET")
USER_AGENT = os.getenv("USER_AGENT")

# Wikimedia OAuth 2.0 Endpoints
AUTHORIZE_URL = "https://meta.wikimedia.org/w/rest.php/oauth2/authorize"
TOKEN_URL = "https://meta.wikimedia.org/w/rest.php/oauth2/access_token"
PROFILE_URL = "https://meta.wikimedia.org/w/rest.php/oauth2/resource/profile"
API_URL = "https://bn.wikipedia.org/w/api.php"

# --- Logging Setup ---
LOG_FILE = "sent_logs.json" # Simplified for now, or keep existing path
LOG_DIR = os.path.dirname(LOG_FILE)
if LOG_DIR:
    os.makedirs(LOG_DIR, exist_ok=True)

log_lock = threading.Lock()

# --- OAuth Setup ---
config = Config(environ=os.environ)
oauth = OAuth(config)
oauth.register(
    name='wikimedia',
    client_id=CONSUMER_KEY,
    client_secret=CONSUMER_SECRET,
    access_token_url=TOKEN_URL,
    authorize_url=AUTHORIZE_URL,
    token_endpoint_auth_method='client_secret_basic',
)

# --- Helper Functions ---

def load_logs():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading logs: {e}")
            return {}
    return {}

def save_log(editathon, article, recipient, sender):
    with log_lock:
        logs = load_logs()
        if editathon not in logs:
            logs[editathon] = {}

        logs[editathon][article] = {
            "recipient": recipient,
            "sender": sender,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving log: {e}")
            raise e

# --- Routes ---

@auth_router.get("/get_sent_logs")
async def get_sent_logs():
    return load_logs()

@auth_router.post("/post_talk")
async def post_talk(request: Request):
    session = request.session
    token_data = session.get('access_token_data')
    if not token_data:
        raise HTTPException(status_code=401, detail="Unauthorized: No access token found in session.")

    data = await request.json()
    target_user = data.get("user")
    subject = data.get("subject")
    message = data.get("message")
    editathon = data.get("editathon")
    article = data.get("article")

    if not target_user or not message:
        raise HTTPException(status_code=400, detail="Missing data")

    try:
        access_token = token_data['access_token']
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT
        }

        async with httpx.AsyncClient() as client:
            # 1. Get CSRF Token
            params = {
                "action": "query",
                "meta": "tokens",
                "type": "csrf",
                "format": "json",
                "formatversion": "2"
            }
            res = await client.post(API_URL, data=params, headers=headers)
            res_data = res.json()

            if "error" in res_data:
                raise HTTPException(status_code=403, detail={"error": "Wiki API Error (Token)", "details": res_data["error"]})

            csrftoken = res_data.get("query", {}).get("tokens", {}).get("csrftoken")

            # 2. Post Message
            post_params = {
                "action": "edit",
                "title": f"User talk:{target_user}",
                "section": "new",
                "summary": subject,
                "text": message,
                "token": csrftoken,
                "format": "json",
                "formatversion": "2"
            }
            res = await client.post(API_URL, data=post_params, headers=headers)
            res_json = res.json()

            # 3. Log the success
            if res_json.get("edit", {}).get("result") == "Success":
                try:
                    save_log(editathon, article, target_user, session.get('username'))
                except Exception as log_error:
                    print(f"Failed to save log: {log_error}")

            return res_json

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "Internal Server Error", "details": str(e)})

@auth_router.get("/login")
async def login(request: Request):
    redirect_uri = request.url_for('oauth_callback')
    # If running behind a proxy or local dev with different port, might need to adjust redirect_uri
    return await oauth.wikimedia.authorize_redirect(request, str(redirect_uri))

@auth_router.get("/auth/callback")
async def oauth_callback(request: Request):
    try:
        token = await oauth.wikimedia.authorize_access_token(request)
        resp = await oauth.wikimedia.get(PROFILE_URL, token=token)
        user_info = resp.json()

        request.session['access_token_data'] = token
        request.session['username'] = user_info.get('username')

        # Redirect to the frontend app (will be fixed once I know the frontend URL)
        # For now, redirect to a generic success page or back to root
        return RedirectResponse(url="/") 
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth 2.0 callback error: {str(e)}")

@auth_router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")

@auth_router.get("/me")
async def get_me(request: Request):
    return {"username": request.session.get("username")}
