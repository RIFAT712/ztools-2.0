import os
import requests
import time
import json
import threading
from flask import Blueprint, request, redirect, url_for, session, jsonify
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

auth = Blueprint('auth', __name__)

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
# Using HOME_DIR ensures we are outside the restricted source code folders
HOME_DIR = os.path.expanduser("~")
LOG_DIR = os.path.join(HOME_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "sent_logs.json")

# Create the logs directory immediately if it doesn't exist
os.makedirs(LOG_DIR, exist_ok=True)

# Thread lock to prevent concurrent writes from corrupting the JSON file
log_lock = threading.Lock()

# --- OAuth Setup ---
oauth = OAuth()
oauth.register(
    name='wikimedia',
    client_id=CONSUMER_KEY,
    client_secret=CONSUMER_SECRET,
    access_token_url=TOKEN_URL,
    authorize_url=AUTHORIZE_URL,
    token_endpoint_auth_method='client_secret_basic',
)

# --- Helper Functions ---


def get_access_token():
    return session.get('access_token_data')


def load_logs():
    """Reads the JSON log file safely."""
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            print(f"Error loading logs: {e}")
            return {}
    return {}


def save_log(editathon, article, recipient, sender):
    """Writes to the JSON log file using a thread lock to prevent corruption."""
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


@auth.route("/get_sent_logs", methods=["GET"])
def get_sent_logs():
    return jsonify(load_logs())


@auth.route("/post_talk", methods=["POST"])
def post_talk():
    token_data = get_access_token()
    if not token_data:
        return jsonify({
            "error": "Unauthorized",
            "details": "No access token found in session."
        }), 401

    data = request.json
    target_user = data.get("user")
    subject = data.get("subject")
    message = data.get("message")
    editathon = data.get("editathon")
    article = data.get("article")

    if not target_user or not message:
        return jsonify({"error": "Missing data"}), 400

    try:
        access_token = token_data['access_token']
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT
        }

        # 1. Get CSRF Token
        params = {
            "action": "query",
            "meta": "tokens",
            "type": "csrf",
            "format": "json",
            "formatversion": "2"
        }
        res = requests.post(API_URL, data=params, headers=headers)
        res_data = res.json()

        if "error" in res_data:
            return jsonify({"error": "Wiki API Error (Token)", "details": res_data["error"]}), 403

        csrftoken = res_data.get("query", {}).get(
            "tokens", {}).get("csrftoken")

        # 2. Post Message
        post_params = {
            "action": "edit",
            "title": f"User talk:R1F4T/{target_user}",  # for testing purpose
            "section": "new",
            "summary": subject,
            "text": message,
            "token": csrftoken,
            "format": "json",
            "formatversion": "2"
        }
        res = requests.post(API_URL, data=post_params, headers=headers)
        res_json = res.json()

        # 3. Log the success
        if res_json.get("edit", {}).get("result") == "Success":
            try:
                save_log(editathon, article, target_user,
                         session.get('username'))
            except Exception as log_error:
                print(f"Failed to save log: {log_error}")

        return jsonify(res_json)

    except Exception as e:
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500


@auth.route("/login")
def login():
    session.permanent = True
    redirect_uri = url_for('auth.oauth_callback', _external=True)
    return oauth.wikimedia.authorize_redirect(redirect_uri)


@auth.route("/auth/callback")
def oauth_callback():
    try:
        token = oauth.wikimedia.authorize_access_token()
        resp = oauth.wikimedia.get(PROFILE_URL, token=token)
        user_info = resp.json()

        session['access_token_data'] = token
        session['username'] = user_info.get('username')

        return redirect(url_for('comment'))
    except Exception as e:
        return f"OAuth 2.0 callback error: {str(e)}", 500


@auth.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('comment'))
