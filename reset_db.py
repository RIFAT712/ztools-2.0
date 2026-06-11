import sqlite3
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from core.db import db
from core.config import DB_FILE, tracked_hashes

def wipe_and_init(force=False):
    if not force:
        print("WARNING: This will PERMANENTLY DELETE all data in the database.")
        print("To proceed, run: python reset_db.py --force")
        return

    print(f"Target Database: {DB_FILE}")

    if os.path.exists(DB_FILE):
        try:
            # First try to close any connections (not strictly possible across processes but good to try)
            os.remove(DB_FILE)
            # Also remove WAL/SHM files if they exist
            for ext in ['-wal', '-shm']:
                if os.path.exists(DB_FILE + ext):
                    os.remove(DB_FILE + ext)
            print("Successfully deleted existing database and temporary files.")
        except Exception as e:
            print(f"Error deleting database: {e}")
            print("Attempting to drop table instead...")
            try:
                conn = sqlite3.connect(DB_FILE)
                conn.execute("DROP TABLE IF EXISTS wordcount_cache")
                conn.commit()
                conn.close()
                print("Dropped wordcount_cache table successfully.")
            except Exception as e2:
                print(f"Failed to drop table: {e2}")
                return

    # Re-initialize
    db.init_db(tracked_hashes)
    print("Database re-initialized fresh with the title_hash schema.")


if __name__ == "__main__":
    force = "--force" in sys.argv
    wipe_and_init(force)
