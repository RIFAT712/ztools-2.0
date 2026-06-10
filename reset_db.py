
import fountain
import sqlite3
import os
import sys

# Add current directory to path so we can import fountain
sys.path.append(os.getcwd())


def wipe_and_init():
    print(f"Target Database: {fountain.DB_FILE}")

    if os.path.exists(fountain.DB_FILE):
        try:
            # First try to close any connections (not strictly possible across processes but good to try)
            os.remove(fountain.DB_FILE)
            # Also remove WAL/SHM files if they exist
            for ext in ['-wal', '-shm']:
                if os.path.exists(fountain.DB_FILE + ext):
                    os.remove(fountain.DB_FILE + ext)
            print("Successfully deleted existing database and temporary files.")
        except Exception as e:
            print(f"Error deleting database: {e}")
            print("Attempting to drop table instead...")
            try:
                conn = sqlite3.connect(fountain.DB_FILE)
                conn.execute("DROP TABLE IF EXISTS wordcount_cache")
                conn.commit()
                conn.close()
                print("Dropped wordcount_cache table successfully.")
            except Exception as e2:
                print(f"Failed to drop table: {e2}")
                return

    # Re-initialize
    fountain.db.init_db(fountain.tracked_hashes)
    print("Database re-initialized fresh with the title_hash schema.")


if __name__ == "__main__":
    wipe_and_init()
