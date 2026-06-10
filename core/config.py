import os
import logging
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, "ztools.db")
LOG_DIR = os.path.join(BASE_DIR, "logs")

USER_AGENT = os.getenv("USER_AGENT")
if not USER_AGENT or "your_username" in USER_AGENT:
    USER_AGENT = "ZToolsEditathonManager/1.4 (https://github.com/shafayet/ztools; Community Tool)"

# Shared memory cache
tracked_hashes = set()

# UNWANTED_CSS moved to processor as it's logic-specific
