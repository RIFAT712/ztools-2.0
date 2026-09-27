import os
import secrets
from dotenv import load_dotenv

# Load env before anything reads it. Toolforge keeps .env in the tool's home directory.
load_dotenv(os.path.join(os.path.expanduser("~"), ".env"))
load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Toolforge containers have an ephemeral filesystem; TOOL_DATA_DIR is the tool's persistent NFS home.
DATA_DIR = os.getenv("TOOL_DATA_DIR", BASE_DIR)
DB_FILE = os.path.join(DATA_DIR, "ztools.db")
LOG_DIR = os.path.join(BASE_DIR, "logs")

USER_AGENT = os.getenv("USER_AGENT")
if not USER_AGENT or "your_username" in USER_AGENT:
    USER_AGENT = "ZToolsEditathonManager/1.4 (https://github.com/shafayet/ztools; Community Tool)"

# Without JWT_SECRET a random key is used, so admin logins reset on every restart (safe, just inconvenient).
JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_urlsafe(32)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 1 week

# Shared memory cache
tracked_hashes = set()
