import time
import json
import asyncio
import threading
import requests
from datetime import datetime, timedelta
from sseclient import SSEClient as EventSource
from concurrent.futures import ThreadPoolExecutor
from core.config import USER_AGENT, tracked_hashes
from core.logger import smart_log
from core.db import db
from core.utils import normalize_title, get_title_hash
from core.api import close_session, get_bn_editathons
from core.processor import process_word_counts_async, RULES_VERSION

# Worker Pool for background processing (controlled resource usage)
realtime_worker_pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="RealtimeWorker")

ACTIVE_GRACE = timedelta(days=30)  # jury keeps reviewing after the finish date, so keep syncing every cycle
IDLE_RESYNC = timedelta(days=1)    # long-finished contests: one refresh a day is plenty

def sync_contest_list():
    """Mirror every recent bn Fountain contest into the tracked table. Raises (keeping the old list) on failure."""
    contests = get_bn_editathons()
    if not contests: raise RuntimeError("Fountain returned no bn contests")
    codes = {e["code"] for e in contests}
    with db as conn:
        conn.executemany("INSERT OR REPLACE INTO enabled_editathons (code, name, wiki, site_url, finish) VALUES (?, ?, ?, ?, ?)",
                         [(e["code"], e["name"], e["wiki"], e["site_url"], e["finish"]) for e in contests])
        gone = [c for (c,) in conn.execute("SELECT code FROM enabled_editathons").fetchall() if c not in codes]
        for c in gone:
            # Aged out of Fountain's 365-day window: drop re-derivable caches, keep admin bans
            conn.execute("DELETE FROM enabled_editathons WHERE code = ?", (c,))
            conn.execute("DELETE FROM wordcount_cache WHERE editathon_code = ?", (c,))
            conn.execute("DELETE FROM fountain_cache WHERE code = ?", (c,))
    if gone:
        smart_log(f"[Sync] Dropped {len(gone)} aged-out contests: {', '.join(gone)}", component="sync")
        db.refresh_tracked_hashes(tracked_hashes)

def due_contests(now=None):
    now = now or datetime.now()
    with db as conn:
        rows = conn.execute("SELECT e.code, e.finish, f.last_updated FROM enabled_editathons e LEFT JOIN fountain_cache f ON f.code = e.code").fetchall()
        # Counts made under older counting rules need one recount right away, however old the contest
        old_rules = {c for (c,) in conn.execute("SELECT DISTINCT editathon_code FROM wordcount_cache WHERE rules_v IS NOT ?", (RULES_VERSION,))}
    due = []
    for code, finish, last in rows:
        try: active = datetime.strptime(finish, "%Y-%m-%dT%H:%M:%SZ") > now - ACTIVE_GRACE
        except (TypeError, ValueError): active = True
        if active or code in old_rules or not last or datetime.fromisoformat(last) < now - IDLE_RESYNC:
            due.append(code)
    return due

async def run_sync_cycle(codes):
    try:
        for code in codes:
            await process_word_counts_async(code, source="Monitor")
            await asyncio.sleep(5) # Delay between editathons
    finally:
        await close_session()

def background_monitor():
    while True:
        try:
            try: sync_contest_list()
            except Exception as ex: smart_log(f"[Sync] Contest list refresh failed, keeping current list: {ex}", "ERROR", component="sync")
            due = due_contests()
            smart_log(f"[Sync] Cycle started for {len(due)} due editathons", component="sync")
            if due: asyncio.run(run_sync_cycle(due))
            smart_log("[Sync] Cycle complete", component="sync")
        except Exception as ex: 
            smart_log(f"Monitor Error: {str(ex)}", "ERROR", component="sync")
        time.sleep(900)

async def run_realtime_task(code, source, title):
    try:
        await process_word_counts_async(code, source=source, target_article=title)
    finally:
        await close_session()

def realtime_stream_monitor():
    bengali_wikis = ['bnwiki', 'bnwiktionary', 'bnwikisource', 'bnwikibooks', 'bnwikiquote', 'bnwikivoyage']
    wiki_filter = ",".join(bengali_wikis)
    url = f'https://stream.wikimedia.org/v2/stream/recentchange?wiki={wiki_filter}'
    
    smart_log(f"[Stream] Starting monitor with {len(tracked_hashes)} tracked titles", component="live")
    
    while True:
        try:
            with requests.get(url, stream=True, timeout=(5, 300), headers={"User-Agent": USER_AGENT}) as response:
                if response.status_code != 200:
                    smart_log(f"[Stream] Connection failed (HTTP {response.status_code})", "ERROR", component="live")
                    time.sleep(30); continue
                
                smart_log("[Stream] Connected to Bengali Wikimedia EventStream", "INFO", component="live")
                client = EventSource(response)
                
                last_heartbeat = 0
                for event in client.events():
                    now = time.time()
                    if now - last_heartbeat > 600: # Every 10 minutes
                        smart_log(f"[Stream] Monitor heartbeat: tracking {len(tracked_hashes)} hashes", component="live")
                        last_heartbeat = now
                    if not event.data: continue
                    try:
                        change = json.loads(event.data)
                        wiki_dbname = change.get('wiki')
                        if change.get('bot'): continue

                        if wiki_dbname in bengali_wikis:
                            change_type = change.get('type', 'edit')
                            ns = change.get('namespace')
                            title = change.get('title')
                            
                            # NS 0 is Mainspace (Articles)
                            if ns == 0 and change_type in ['edit', 'new']:
                                normalized_title = normalize_title(title)
                                t_hash = get_title_hash(normalized_title)
                                track_key = f"{wiki_dbname}:{t_hash}"
                                
                                if track_key not in tracked_hashes:
                                    continue
                                
                                smart_log(f"[Stream] Match found: {normalized_title} ({wiki_dbname})", component="live")
                                
                                with db as conn:
                                    exists = conn.execute('SELECT DISTINCT editathon_code FROM wordcount_cache WHERE wiki = ? AND title_hash = ?', (wiki_dbname, t_hash)).fetchall()
                                
                                if exists:
                                    for code in [row[0] for row in exists]:
                                        def run_sync_safe(c, t, w):
                                            try:
                                                asyncio.run(run_realtime_task(c, f"Realtime({w})", t))
                                            except Exception as task_err:
                                                smart_log(f"[Stream] Task error for {t}: {str(task_err)}", "ERROR", component="live")
                                        
                                        realtime_worker_pool.submit(run_sync_safe, code, normalized_title, wiki_dbname)
                    except Exception as e:
                        smart_log(f"[Stream] Event error: {str(e)}", "ERROR", component="live")
        except Exception as conn_err:
            smart_log(f"[Stream] Connection lost: {str(conn_err)}. Reconnecting in 15s...", "ERROR", component="live")
            time.sleep(15)

def start_background_services():
    threading.Thread(target=background_monitor, name="FullSyncMonitor", daemon=True).start()
    threading.Thread(target=realtime_stream_monitor, name="LiveUpdateMonitor", daemon=True).start()
