import os
import logging
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, "ztools.db")
LOG_DIR = os.path.join(BASE_DIR, "logs")
CLEANED_LOG_DIR = os.path.join(LOG_DIR, "articles")

USER_AGENT = os.getenv("USER_AGENT")
if not USER_AGENT or "your_username" in USER_AGENT:
    USER_AGENT = "ZToolsEditathonManager/1.4 (https://github.com/shafayet/ztools; Community Tool)"

JWT_SECRET = os.getenv("JWT_SECRET", "ztools_secret_key_change_me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 1 week

# Shared memory cache
tracked_hashes = set()

# UNWANTED_CSS moved to processor as it's logic-specific
