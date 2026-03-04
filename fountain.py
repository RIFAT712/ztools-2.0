import os
import re
import random
import json
import sqlite3
import asyncio
import aiohttp
import threading
import logging
import unicodedata
import hashlib
from queue import Queue
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import requests
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from sseclient import SSEClient as EventSource

# Load environment variables
load_dotenv()

# Constants and Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "ztools.db")
LOG_FILE = os.path.join(BASE_DIR, "monitor.log")

# Configure Logging
class LimitedFileHandler(logging.FileHandler):
    def __init__(self, filename, mode='a', encoding=None, delay=False, max_lines=100):
        super().__init__(filename, mode, encoding, delay)
        self.max_lines = max_lines

    def emit(self, record):
        super().emit(record)
        self.flush()
        try:
            with open(self.baseFilename, 'r', encoding=self.encoding) as f:
                lines = f.readlines()
            if len(lines) > self.max_lines:
                with open(self.baseFilename, 'w', encoding=self.encoding) as f:
                    f.writelines(lines[-self.max_lines:])
        except: pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        LimitedFileHandler(LOG_FILE, encoding='utf-8', max_lines=100),
        logging.StreamHandler()
    ]
)

WIKI_PREFIXES = {
    "wiki": "wikipedia", "wikt": "wiktionary", "b": "wikibooks",
    "voy": "wikivoyage", "q": "wikiquote", "s": "wikisource", "n": "wikinews"
}

# Identity
USER_AGENT = os.getenv("USER_AGENT")
if not USER_AGENT or "your_username" in USER_AGENT:
    USER_AGENT = "ZToolsEditathonManager/1.4 (https://github.com/shafayet/ztools; Community Tool)"

# Global Cache for metadata
cache = {"details": {}, "editathons": {"data": None, "expiry": 0}, "wordcounts": {}}

# --- Utility Functions (Must be defined early) ---

def normalize_title(title):
    if not title: return ""
    return unicodedata.normalize('NFC', str(title)).replace('_', ' ').strip()

def get_title_hash(title):
    if not title: return ""
    return hashlib.sha256(normalize_title(title).encode('utf-8')).hexdigest()

def get_wiki_url(code):
    prefix, lang = code.split(':', 1) if ':' in code else ("wikipedia", code)
    return f"{lang}.{WIKI_PREFIXES.get(prefix, 'wikipedia')}.org"

def fetch_fountain_data(code):
    now = time.time()
    if code in cache["details"] and cache["details"][code]["expiry"] > now: return cache["details"][code]["data"]
    resp = requests.get(f"https://fountain.toolforge.org/api/editathons/{code}", timeout=15)
    resp.raise_for_status(); data = resp.json()
    cache["details"][code] = {"data": data, "expiry": now + 300}
    return data

def get_bn_editathons():
    now = time.time()
    if cache["editathons"]["data"] and cache["editathons"]["expiry"] > now: return cache["editathons"]["data"]
    try:
        data = requests.get("https://fountain.toolforge.org/api/editathons", timeout=10).json()
        cutoff = datetime.now() - timedelta(days=365)
        result = []
        for e in data:
            wiki = e.get("wiki", "bn")
            if (wiki.split(':')[1] if ':' in wiki else wiki) != "bn": continue
            try:
                if datetime.strptime(e.get("finish"), "%Y-%m-%dT%H:%M:%SZ") < cutoff: continue
            except: pass
            result.append({"code": e.get("code"), "name": e.get("name"), "wiki": wiki, "finish": e.get("finish"), "site_url": get_wiki_url(wiki)})
        cache["editathons"] = {"data": result, "expiry": now + 3600}
        return result
    except: return []

# --- Database Logic ---

def init_db():
    db_dir = os.path.dirname(DB_FILE)
    if db_dir and not os.path.exists(db_dir): os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    cursor = conn.cursor()
    
    # Check if we need to alert the user about manual reset requirement (schema mismatch)
    cursor.execute("PRAGMA table_info(wordcount_cache)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if columns and "title_hash" not in columns:
        logging.warning("[DB] Database schema is outdated! Please run 'python reset_db.py' to reset the cache and start fresh with hashing.")
        # We don't drop automatically anymore to avoid user surprise.
    else:
        cursor.execute('''CREATE TABLE IF NOT EXISTS wordcount_cache (
            editathon_code TEXT, 
            title_hash TEXT,
            article_title TEXT, 
            words INTEGER, 
            actual_title TEXT, 
            is_redirect BOOLEAN, 
            last_updated TEXT,
            PRIMARY KEY (editathon_code, title_hash))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS monitor_status (
        key TEXT PRIMARY KEY, last_run TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

# --- Core Business Logic ---

BN_WORDS_RE = re.compile(r'[\u0980-\u09FF]+')
UNWANTED_CSS = [
    '.mw-empty-elt', '.mw-editsection', '.reference', '.references', '.reflist',
    '.mbox-small', '.ambox', '.navbox', '.catlinks', '.noprint', '.metadata',
    '.portal', 'style', 'script', '.thumbinner', '.listing-lastedit'
]

processing_lock = threading.Lock()
currently_processing = set()

def get_all_cached_for_editathon(code):
    conn = get_db_connection()
    rows = conn.cursor().execute('SELECT title_hash, words, actual_title, is_redirect, last_updated, article_title FROM wordcount_cache WHERE editathon_code = ?', (code,)).fetchall()
    conn.close()
    return {r[0]: {"words": r[1], "actual_title": r[2], "is_redirect": bool(r[3]), "last_updated": r[4], "article_title": r[5]} for r in rows}

def save_article_to_cache(code, res, conn=None):
    # Allow saving articles even if words are 0 (e.g., missing or empty)
    should_close = False
    if conn is None: conn = get_db_connection(); should_close = True
    title = normalize_title(res["title"])
    t_hash = get_title_hash(title)
    actual_title = normalize_title(res["actual_title"])
    conn.cursor().execute('''INSERT OR REPLACE INTO wordcount_cache (editathon_code, title_hash, article_title, words, actual_title, is_redirect, last_updated)
                             VALUES (?, ?, ?, ?, ?, ?, ?)''', (code, t_hash, title, res["words"], actual_title, res["is_redirect"], res["timestamp"]))
    logging.info(f"[DB] Saved: {title} ({res['words']} words) [Hash: {t_hash[:8]}]")
    if should_close: conn.commit(); conn.close()

async def count_words_async(session, api_url, title, site_url):
    data_to_send = {"action": "parse", "page": title, "prop": "text", "redirects": "true", "disabletoc": "1", "format": "json", "maxlag": "5"}
    for attempt in range(3):
        try:
            async with session.post(api_url, data=data_to_send) as res:
                if res.status != 200: 
                    await asyncio.sleep(2 * (attempt + 1)); continue
                data = await res.json()
                if "error" in data: return 0, title, False
                html = data["parse"]["text"]["*"]
                soup = BeautifulSoup(html, 'html.parser')
                for sel in UNWANTED_CSS:
                    for tag in soup.select(sel): tag.decompose()
                text = soup.get_text()
                words = len(BN_WORDS_RE.findall(text)) if site_url.startswith('bn.') else len(text.split())
                return words, data["parse"]["title"], data["parse"]["title"] != title
        except: await asyncio.sleep(1)
    return 0, title, False

async def get_metadata_async(session, api_url, titles):
    metadata = {}
    if not titles: return metadata
    meta_semaphore = asyncio.Semaphore(3)
    batch_size = 25
    batches = [titles[i:i+batch_size] for i in range(0, len(titles), batch_size)]
    async def fetch_batch(batch):
        async with meta_semaphore:
            data_to_send = {"action": "query", "titles": "|".join(batch), "prop": "revisions", "rvprop": "timestamp", "redirects": "true", "format": "json", "maxlag": "5"}
            try:
                async with session.post(api_url, data=data_to_send) as res:
                    if res.status == 200: return await res.json(), batch
                    logging.error(f"[API] Metadata fetch failed: {res.status} for {len(batch)} titles")
            except Exception as e: logging.error(f"[API] Metadata error: {str(e)}")
            return None, batch
    results = await asyncio.gather(*[fetch_batch(b) for b in batches])
    for data, batch in results:
        if not data: continue
        query = data.get("query", {})
        pages = query.get("pages", {})
        pages_by_title = {normalize_title(p.get("title")): p for p in pages.values() if "title" in p}
        norm = {normalize_title(n["from"]): normalize_title(n["to"]) for n in query.get("normalized", [])}
        redir = {normalize_title(r["from"]): normalize_title(r["to"]) for r in query.get("redirects", [])}
        for orig_raw in batch:
            orig = normalize_title(orig_raw)
            curr = norm.get(orig, orig)
            seen = {curr}
            while curr in redir:
                curr = redir[curr]
                if curr in seen: break
                seen.add(curr)
            p = pages_by_title.get(curr)
            if p and "revisions" in p:
                metadata[orig] = {"timestamp": p["revisions"][0]["timestamp"], "actual_title": curr}
    logging.info(f"[API] Metadata coverage: {len(metadata)}/{len(titles)} found.")
    return metadata

async def process_word_counts_async(code, queue=None, source="Monitor"):
    try:
        logging.info(f"[{source}] Update sequence started: {code}")
        fountain_data = fetch_fountain_data(code)
        wiki_code = fountain_data.get("wiki", "wiki:bn")
        site_url = get_wiki_url(wiki_code)
        api_url = f"https://{site_url}/w/api.php"
        if queue: queue.put({"type": "info", "site_url": site_url})

        all_titles = []
        user_articles = defaultdict(list)
        for article in fountain_data.get("articles", []):
            user, name_raw = article.get("user"), article.get("name", "")
            name = normalize_title(name_raw)
            marks = article.get("marks", [])
            status = "গৃহীত হয়নি" if any(r.get("marks", {}).get("0") in [1, 2] for r in marks) else "গৃহীত হয়েছে" if marks else "অপর্যালোচিত"
            if user and name:
                user_articles[user].append({"name": name, "status": status})
                all_titles.append(name)

        cached_data = get_all_cached_for_editathon(code)
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=300)) as session:
            metadata = await get_metadata_async(session, api_url, all_titles)
            up_to_date, tasks_to_run = [], []
            for user, articles in user_articles.items():
                for a in articles:
                    title = a["name"]
                    t_hash = get_title_hash(title)
                    m = metadata.get(title)
                    is_uptodate = False
                    
                    if t_hash in cached_data:
                        c = cached_data[t_hash]
                        if m:
                            if c["last_updated"] == m["timestamp"]:
                                is_uptodate = True
                        else:
                            # Article is missing from Wikipedia
                            if c["last_updated"] == "MISSING":
                                is_uptodate = True
                    
                    if is_uptodate:
                        c = cached_data[t_hash]
                        up_to_date.append({"user": user, "title": title, "actual_title": c["actual_title"], "status": a["status"], "words": c["words"], "is_redirect": c["is_redirect"]})
                    else:
                        tasks_to_run.append({"user": user, "title": title, "status": a["status"]})

            logging.info(f"[{source}] {code}: {len(up_to_date)} cached/up-to-date, {len(tasks_to_run)} require update.")

            if up_to_date and queue: queue.put({"type": "update", "articles": up_to_date})
            if tasks_to_run:
                logging.info(f"[{source}] {len(tasks_to_run)} articles require counting for {code}")
                conn = get_db_connection()
                semaphore = asyncio.Semaphore(10) 
                async def run_task(task):
                    title = task["title"]
                    t_hash = get_title_hash(title)
                    key = (code, t_hash)
                    with processing_lock:
                        if key in currently_processing: return None
                        currently_processing.add(key)
                    try:
                        async with semaphore:
                            m = metadata.get(title)
                            if m:
                                words, actual, redir = await count_words_async(session, api_url, title, site_url)
                                ts = m["timestamp"]
                            else:
                                # Mark as missing if metadata didn't find it
                                words, actual, redir, ts = 0, title, False, "MISSING"
                            
                            res = {"user": task["user"], "title": title, "actual_title": actual, "status": task["status"], "words": words, "is_redirect": redir, "timestamp": ts}
                            save_article_to_cache(code, res, conn=conn)
                            return res
                    finally:
                        with processing_lock: currently_processing.discard(key)
                
                processed_count = 0; results_buffer = []
                for coro in asyncio.as_completed([run_task(t) for t in tasks_to_run]):
                    res = await coro
                    if not res: continue
                    processed_count += 1
                    if processed_count % 20 == 0:
                        conn.commit(); logging.info(f"[{source}] Checkpoint: {processed_count} saved for {code}")
                    if queue:
                        results_buffer.append(res)
                        if len(results_buffer) >= 20:
                            queue.put({"type": "update", "articles": results_buffer}); results_buffer = []
                if results_buffer and queue: queue.put({"type": "update", "articles": results_buffer})
                conn.commit(); conn.close()
            else: logging.info(f"[{source}] No changes detected for {code}.")

        final_cache = get_all_cached_for_editathon(code)
        totals = defaultdict(lambda: {"accepted": 0, "unreviewed": 0, "rejected": 0, "total": 0, "articles": []})
        for user, articles in user_articles.items():
            u_s = totals[user]
            for a in articles:
                title = a["name"]
                t_hash = get_title_hash(title)
                c = final_cache.get(t_hash, {"words": 0, "actual_title": title, "is_redirect": False})
                w = c["words"]
                u_s["total"] += w
                if a["status"] == "গৃহীত হয়েছে": u_s["accepted"] += w
                elif a["status"] == "গৃহীত হয়নি": u_s["rejected"] += w
                else: u_s["unreviewed"] += w
                u_s["articles"].append({"title": title, "actualTitle": c["actual_title"], "status": a["status"], "words": w, "isRedirect": c["is_redirect"]})
        
        if queue: queue.put({"type": "complete", "data": (totals, site_url)})
        return (totals, site_url)
    except Exception as e:
        logging.error(f"[{source}] Fatal Error: {str(e)}")
        if queue: queue.put({"type": "error", "message": str(e)})
    finally:
        if queue: queue.put("DONE")

def get_word_counts(code):
    q = Queue()
    threading.Thread(target=lambda: asyncio.run(process_word_counts_async(code, q, source="UI"))).start()
    while True:
        item = q.get()
        if item == "DONE": break
        yield item

def background_monitor():
    logging.info("[Monitor] Service started.")
    while True:
        try:
            editathons = get_bn_editathons()
            now = datetime.now(); ongoing, recent_past = [], []
            one_month_ago = now - timedelta(days=30)
            for e in editathons:
                try:
                    finish = datetime.strptime(e['finish'], "%Y-%m-%dT%H:%M:%SZ")
                    if finish > now: ongoing.append(e)
                    elif finish > one_month_ago: recent_past.append(e)
                except: ongoing.append(e)
            logging.info(f"[Monitor] Cycle: {len(ongoing)} live, {len(recent_past)} history.")
            for e in ongoing + recent_past:
                asyncio.run(process_word_counts_async(e['code'], source="Monitor"))
                time.sleep(10)
            conn = get_db_connection()
            conn.execute("INSERT OR REPLACE INTO monitor_status (key, last_run) VALUES (?, ?)", ("main", now.isoformat()))
            conn.commit(); conn.close()
        except Exception as ex: logging.error(f"[Monitor] Cycle Error: {str(ex)}")
        time.sleep(900)

def realtime_stream_monitor():
    url = 'https://stream.wikimedia.org/v2/stream/recentchange'
    logging.info("[Realtime] Listener active. Subscribing to recentchange...")
    
    while True:
        try:
            # We use a longer timeout for the stream connection itself
            with requests.get(url, stream=True, timeout=(5, 300), headers={"User-Agent": USER_AGENT}) as response:
                if response.status_code != 200:
                    logging.error(f"[Realtime] Failed to connect: {response.status_code}")
                    time.sleep(30); continue
                
                client = EventSource(response)
                for event in client.events():
                    if not event.data: continue
                    
                    try:
                        change = json.loads(event.data)
                        
                        # Filter for bnwiki and namespace 0 (Main/Article)
                        if change.get('wiki') == 'bnwiki' and change.get('namespace') == 0:
                            title = normalize_title(change.get('title'))
                            t_hash = get_title_hash(title)
                            user = change.get('user', 'Unknown')
                            
                            logging.info(f"[Realtime Trace] bnwiki edit detected: {title} by {user}")
                            
                            # Check if this article exists in ANY of our tracked editathons
                            conn = get_db_connection()
                            exists = conn.execute('SELECT DISTINCT editathon_code FROM wordcount_cache WHERE title_hash = ?', (t_hash,)).fetchall()
                            conn.close()
                            
                            if exists:
                                codes = [row[0] for row in exists]
                                logging.info(f"[Realtime MATCH] Article '{title}' found in editathons: {codes}. Triggering updates...")
                                for code in codes:
                                    # Run in a new task to not block the listener
                                    asyncio.run(process_word_counts_async(code, source=f"Realtime:{user}"))
                    except Exception as json_e:
                        # logging.error(f"[Realtime] JSON Error: {str(json_e)}")
                        pass
        except Exception as e:
            logging.error(f"[Realtime] Loop error: {str(e)}")
            time.sleep(10)

threading.Thread(target=background_monitor, daemon=True).start()
threading.Thread(target=realtime_stream_monitor, daemon=True).start()

# --- Jury and Other logic ---

def get_jury_stats_data(code):
    data = fetch_fountain_data(code); stats = defaultdict(lambda: {"total": 0, "accepted": 0, "rejected": 0})
    for art in data.get("articles", []):
        for rev in art.get("marks", []):
            u = rev.get("user")
            if u:
                stats[u]["total"] += 1; m = rev.get("marks", {}).get("0")
                if m == 0: stats[u]["accepted"] += 1
                elif m in [1, 2]: stats[u]["rejected"] += 1
    sorted_j = sorted(stats.items(), key=lambda x: x[1]["total"], reverse=True)
    def to_bn(n): return "".join("০১২৩৪৫৬৭৮৯"[int(d)] if d.isdigit() else d for d in str(n))
    wt = '{| class="wikitable sortable"\n! # !! পর্যালোচক !! মোট !! গৃহীত !! বাতিল\n'
    t_t, t_a, t_r = 0, 0, 0
    for i, (j, s) in enumerate(sorted_j, 1):
        wt += f"|-\n| {to_bn(i)} || {j} || {to_bn(s['total'])} || {to_bn(s['accepted'])} || {to_bn(s['rejected'])}\n"
        t_t += s['total']; t_a += s['accepted']; t_r += s['rejected']
    return sorted_j, wt + f"|-\n! মোট ||  || {to_bn(t_t)} || {to_bn(t_a)} || {to_bn(t_r)}\n|}}"

def get_user_reviews(code, user):
    data = fetch_fountain_data(code); wiki = data.get("wiki", "wiki:bn"); reviews = []
    for art in data.get("articles", []):
        for rev in art.get("marks", []):
            if rev.get("user") == user:
                m = rev.get("marks", {}).get("0")
                reviews.append({"name": art.get("name"), "submitter": art.get("user"), "comment": rev.get("comment", ""), "timestamp": art.get("dateAdded"), "decision": "accepted" if m == 0 else "rejected" if m in [1, 2] else "unknown"})
                break
    return reviews, get_wiki_url(wiki)

def get_rejected_articles_data(code):
    data = fetch_fountain_data(code); rej = []
    for art in data.get("articles", []):
        if any(r.get("marks", {}).get("0") in [1, 2] for r in art.get("marks", [])): rej.append(art.get("name"))
    def to_bn(n): return "".join("০১২৩৪৫৬৭৮৯"[int(d)] if d.isdigit() else d for d in str(n))
    wt = '{| class="wikitable sortable"\n! ক্রমিক !! নিবন্ধের নাম\n'
    for i, n in enumerate(rej, 1): wt += f"|-\n| {to_bn(i)} || {n}\n"
    return rej, wt + "|}"

def get_user_jury_editathons(username):
    bn = get_bn_editathons(); recent = []
    six_mo = datetime.now() - timedelta(days=180)
    for e in bn:
        try:
            if datetime.strptime(e['finish'], "%Y-%m-%dT%H:%M:%SZ") > six_mo: recent.append(e)
        except: recent.append(e)
    def check(e):
        try:
            if username in fetch_fountain_data(e['code']).get("jury", []): return {"code": e['code'], "name": e['name']}
        except: pass
        return None
    with ThreadPoolExecutor(max_workers=20) as exe: return [r for r in list(exe.map(check, recent)) if r]
