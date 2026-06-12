import sqlite3
import os
import threading
from core.config import DB_FILE
from core.logger import smart_log

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self._ensure_dir()
        self._local = threading.local()

    def _ensure_dir(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=60, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size = -2000")
        return conn

    def __enter__(self):
        self._local.conn = self.connect()
        return self._local.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        conn = getattr(self._local, 'conn', None)
        if conn:
            try:
                if exc_type: conn.rollback()
                else: conn.commit()
            except: pass
            finally:
                conn.close()
                self._local.conn = None

    def _migrate_table(self, cursor, table_name, required_columns):
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_columns = [info[1] for info in cursor.fetchall()]
        for col_name, col_def in required_columns.items():
            if col_name not in existing_columns:
                smart_log(f"[DB] Migration: Adding '{col_name}' column to {table_name}")
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}")

    def init_db(self, tracked_hashes_set):
        with self as conn:
            cursor = conn.cursor()
            
            # 1. wordcount_cache
            cursor.execute('''CREATE TABLE IF NOT EXISTS wordcount_cache (
                editathon_code TEXT, title_hash TEXT, article_title TEXT, 
                words INTEGER, actual_title TEXT, is_redirect BOOLEAN, last_updated TEXT,
                PRIMARY KEY (editathon_code, title_hash))''')
            self._migrate_table(cursor, "wordcount_cache", {"wiki": "TEXT"})
            
            # 2. Indices
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_editathon_code ON wordcount_cache (editathon_code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_title_hash ON wordcount_cache (title_hash)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_wiki_hash ON wordcount_cache (wiki, title_hash)')
            
            # 3. Other tables
            cursor.execute('''CREATE TABLE IF NOT EXISTS monitor_status (key TEXT PRIMARY KEY, last_run TEXT)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS fountain_cache (code TEXT PRIMARY KEY, data TEXT, last_updated TEXT)''')
            
            # 4. Admin and Banning tables
            cursor.execute('''CREATE TABLE IF NOT EXISTS admins (
                username TEXT PRIMARY KEY, 
                password_hash TEXT
            )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS banned_users (
                editathon_code TEXT, 
                username TEXT,
                PRIMARY KEY (editathon_code, username)
            )''')
            
            # 5. Enabled Editathons (Selective tracking)
            cursor.execute('''CREATE TABLE IF NOT EXISTS enabled_editathons (
                code TEXT PRIMARY KEY,
                name TEXT,
                wiki TEXT,
                site_url TEXT
            )''')
            
            # 6. Load memory cache
            cursor.execute("SELECT DISTINCT wiki, title_hash FROM wordcount_cache")
            rows = cursor.fetchall()
            for row in rows:
                if row[0] and row[1]:
                    tracked_hashes_set.add(f"{row[0]}:{row[1]}")
                elif row[1]: # Legacy without wiki
                    tracked_hashes_set.add(row[1])
                    
            smart_log(f"[DB] Initialized with {len(tracked_hashes_set)} tracked hashes")

db = DatabaseManager(DB_FILE)
