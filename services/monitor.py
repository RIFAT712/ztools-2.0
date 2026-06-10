import time
import json
import asyncio
import threading
import requests
from datetime import datetime
from sseclient import SSEClient as EventSource
from concurrent.futures import ThreadPoolExecutor
from core.config import USER_AGENT, tracked_hashes
from core.logger import smart_log, log_raw
from core.db import db
from core.utils import normalize_title, get_title_hash
from core.api import get_bn_editathons, close_session
from core.processor import process_word_counts_async

# Worker Pool for background processing (controlled resource usage)
realtime_worker_pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="RealtimeWorker")

async def run_sync_cycle(relevant):
    try:
        for e in relevant:
            await process_word_counts_async(e['code'], source="Monitor")
            await asyncio.sleep(5) # Delay between editathons
    finally:
        await close_session()

def background_monitor():
    while True:
        try:
            editathons = get_bn_editathons()
            relevant = []
            for e in editathons:
                try:
                    if datetime.strptime(e.get('finish', '1970-01-01T00:00:00Z'), "%Y-%m-%dT%H:%M:%SZ") >= datetime(2026, 1, 1):
                        relevant.append(e)
                except: relevant.append(e)
            
            relevant.sort(key=lambda e: e.get('finish', ''), reverse=True)
            smart_log(f"[Sync] Cycle started for {len(relevant)} active editathons", component="sync")
            
            asyncio.run(run_sync_cycle(relevant))
            
            with db as conn:
                conn.execute("INSERT OR REPLACE INTO monitor_status (key, last_run) VALUES (?, ?)", ("main", datetime.now().isoformat()))
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
                            user = change.get('user')
                            
                            log_raw.info(f"[{wiki_dbname}] {change_type.upper()} (ns:{ns}): {title} by {user}")
                            
                            if ns == 0 and change_type in ['edit', 'new']:
                                normalized_title = normalize_title(title)
                                t_hash = get_title_hash(normalized_title)
                                track_key = f"{wiki_dbname}:{t_hash}"
                                
                                if track_key not in tracked_hashes:
                                    # Fallback check for missing hashes in set
                                    with db as conn:
                                        exists_in_db = conn.execute('SELECT 1 FROM wordcount_cache WHERE wiki = ? AND title_hash = ? LIMIT 1', (wiki_dbname, t_hash)).fetchone()
                                    if exists_in_db:
                                        smart_log(f"[Stream] Hash mismatch! Found in DB but not in tracked_hashes: {track_key} ({normalized_title})", component="live")
                                        tracked_hashes.add(track_key)
                                    else:
                                        continue
                                
                                smart_log(f"[Stream] Match found for: {normalized_title} (Mainspace) on {wiki_dbname}", component="live")
                                
                                with db as conn:
                                    exists = conn.execute('SELECT DISTINCT editathon_code FROM wordcount_cache WHERE wiki = ? AND title_hash = ?', (wiki_dbname, t_hash)).fetchall()
                                if exists:
                                    for code in [row[0] for row in exists]:
                                        smart_log(f"[Stream] Submitting task for {normalized_title} ({wiki_dbname}) in {code}", component="live")
                                        def run_sync_safe(c, t, w):
                                            try:
                                                asyncio.run(run_realtime_task(c, f"Realtime({w})", t))
                                            except Exception as task_err:
                                                smart_log(f"[Stream] Task execution error for {t} on {w}: {str(task_err)}", "ERROR", component="live")
                                        
                                        realtime_worker_pool.submit(run_sync_safe, code, normalized_title, wiki_dbname)
                                else:
                                    smart_log(f"[Stream] Article tracked but no editathons found for: {track_key}", "ERROR", component="live")
                    except Exception as e:
                        smart_log(f"[Stream] Event error: {str(e)}", "ERROR", component="live")
        except Exception as conn_err:
            smart_log(f"[Stream] Connection lost: {str(conn_err)}. Reconnecting in 15s...", "ERROR", component="live")
            time.sleep(15)

def start_background_services():
    threading.Thread(target=background_monitor, name="FullSyncMonitor", daemon=True).start()
    threading.Thread(target=realtime_stream_monitor, name="LiveUpdateMonitor", daemon=True).start()
