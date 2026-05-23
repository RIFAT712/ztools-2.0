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
    "wiki": "wikipedia", "wikipedia": "wikipedia",
    "wikt": "wiktionary", "wiktionary": "wiktionary",
    "b": "wikibooks", "wikibooks": "wikibooks",
    "voy": "wikivoyage", "wikivoyage": "wikivoyage",
    "q": "wikiquote", "wikiquote": "wikiquote",
    "s": "wikisource", "wikisource": "wikisource",
    "n": "wikinews", "wikinews": "wikinews"
}

# Identity
USER_AGENT = os.getenv("USER_AGENT")
if not USER_AGENT or "your_username" in USER_AGENT:
    USER_AGENT = "ZToolsEditathonManager/1.4 (https://github.com/shafayet/ztools; Community Tool)"

# --- Utility Functions (Must be defined early) ---

def to_bn(n): return "".join("০১২৩৪৫৬৭৮৯"[int(d)] if d.isdigit() else d for d in str(n))

def normalize_title(title):
    if not title: return ""
    return unicodedata.normalize('NFC', str(title)).replace('_', ' ').strip()

def get_title_hash(title):
    if not title: return ""
    return hashlib.sha256(normalize_title(title).encode('utf-8')).hexdigest()

def get_wiki_url(code):
    prefix, lang = code.split(':', 1) if ':' in code else ("wikipedia", code)
    return f"{lang}.{WIKI_PREFIXES.get(prefix.lower(), 'wikipedia')}.org"

# --- Database Logic ---

def init_db():
    db_dir = os.path.dirname(DB_FILE)
    if db_dir and not os.path.exists(db_dir): os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(wordcount_cache)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if columns and "title_hash" not in columns:
        logging.warning("[DB] Database schema is outdated! Please run 'python reset_db.py' to reset the cache.")
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
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_editathon_code ON wordcount_cache (editathon_code)')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS monitor_status (
        key TEXT PRIMARY KEY, last_run TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS fountain_cache (
        code TEXT PRIMARY KEY, 
        data TEXT, 
        last_updated TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.execute("PRAGMA cache_size = -2000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

# --- Core Business Logic ---

def fetch_fountain_data(code, force_fresh=False):
    if not force_fresh:
        conn = get_db_connection()
        row = conn.execute("SELECT data FROM fountain_cache WHERE code = ?", (code,)).fetchone()
        conn.close()
        if row: return json.loads(row[0])

    try:
        resp = requests.get(f"https://fountain.toolforge.org/api/editathons/{code}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO fountain_cache (code, data, last_updated) VALUES (?, ?, ?)", 
                     (code, json.dumps(data), datetime.now().isoformat()))
        conn.commit(); conn.close()
        return data
    except Exception as e:
        conn = get_db_connection()
        row = conn.execute("SELECT data FROM fountain_cache WHERE code = ?", (code,)).fetchone()
        conn.close()
        if row: return json.loads(row[0])
        raise e

def get_bn_editathons():
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
        return result
    except: return []

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
    rows = conn.cursor().execute('''
        SELECT title_hash, words, actual_title, is_redirect, last_updated, article_title 
        FROM wordcount_cache INDEXED BY idx_editathon_code
        WHERE editathon_code = ?
    ''', (code,)).fetchall()
    conn.close()
    return {r[0]: {"words": r[1], "actual_title": r[2], "is_redirect": bool(r[3]), "last_updated": r[4], "article_title": r[5]} for r in rows}

def save_article_to_cache(code, res, conn=None):
    should_close = False
    if conn is None: conn = get_db_connection(); should_close = True
    title, t_hash = normalize_title(res["title"]), get_title_hash(res["title"])
    conn.cursor().execute('''INSERT OR REPLACE INTO wordcount_cache (editathon_code, title_hash, article_title, words, actual_title, is_redirect, last_updated)
                             VALUES (?, ?, ?, ?, ?, ?, ?)''', (code, t_hash, title, res["words"], res["actual_title"], res["is_redirect"], res["timestamp"]))
    logging.info(f"[DB] Saved: {title} ({res['words']} words)")
    if should_close: conn.commit(); conn.close()

async def count_words_async(session, api_url, title, site_url):
    data_to_send = {"action": "parse", "page": title, "prop": "text", "redirects": "true", "disabletoc": "1", "format": "json", "formatversion": "1", "maxlag": "10"}
    for attempt in range(3):
        try:
            await asyncio.sleep(0.5)
            async with session.post(api_url, data=data_to_send) as res:
                if res.status != 200: 
                    logging.warning(f"[API] HTTP {res.status} for {title}. Retrying...")
                    await asyncio.sleep(2 * (attempt + 1)); continue
                data = await res.json()
                if "error" in data:
                    err_code = data["error"].get("code")
                    if err_code == "missingtitle":
                        logging.info(f"[API] Article missing: {title}")
                        return 0, title, False, "MISSING"
                    logging.error(f"[API] Error for {title}: {data['error']}")
                    await asyncio.sleep(1); continue
                html = data["parse"]["text"]["*"]
                soup = BeautifulSoup(html, 'html.parser')
                for sel in UNWANTED_CSS:
                    for tag in soup.select(sel): tag.decompose()
                text = soup.get_text()
                words = len(BN_WORDS_RE.findall(text)) if site_url.startswith('bn.') else len(text.split())
                return words, data["parse"]["title"], data["parse"]["title"] != title, "LIVE"
        except Exception as e:
            logging.error(f"[API] Exception for {title}: {str(e)}")
            await asyncio.sleep(1)
    return None, title, False, "ERROR"

def calculate_leaderboard(data, current_cache):
    if not data: return None, None
    wiki_code = data.get("wiki", "wiki:bn")
    site_url = get_wiki_url(wiki_code)
    article_info = {}
    for art in data.get("articles", []):
        name = normalize_title(art.get("name", ""))
        marks = art.get("marks", [])
        decisions = [m.get("marks", {}).get("0") for m in marks if "0" in m.get("marks", {})]
        has_conflict = False
        if len(set(decisions)) > 1:
            if 0 in decisions and (1 in decisions or 2 in decisions): has_conflict = True
        juror_list = []
        is_multi_juror = len(marks) > 1
        if marks:
            def get_juror_name(m): return m.get("user") or m.get("userName") or m.get("user_name") or "N/A"
            try:
                ts_marks = sorted([m for m in marks], key=lambda m: m.get("timestamp", "9999-12-31T23:59:59Z"))
                ordinals = ["১ম", "২য়", "৩য়", "৪র্থ", "৫ম"]
                for idx, m in enumerate(ts_marks):
                    name_j = get_juror_name(m)
                    d_val = m.get("marks", {}).get("0")
                    d_str = "গৃহীত" if d_val == 0 else "বাতিল" if d_val in [1, 2] else "অনির্ধারিত"
                    suffix = ordinals[idx] if idx < len(ordinals) else f"{to_bn(idx+1)}ম"
                    juror_list.append(f"{name_j} ({suffix} {d_str})")
            except: juror_list = [get_juror_name(marks[0])]
        jurors_str = ", ".join(juror_list) if juror_list else "N/A"
        article_info[name] = {
            "status": "গৃহীত হয়নি" if any(d in [1, 2] for d in decisions) else "গৃহীত হয়েছে" if marks else "অপর্যালোচিত",
            "hasConflict": has_conflict, "multiJuror": is_multi_juror, "jurors": jurors_str,
            "firstJuror": get_juror_name(marks[0]) if marks else "N/A"
        }

    user_articles = defaultdict(list)
    for art in data.get("articles", []):
        user = art.get("user")
        name = normalize_title(art.get("name", ""))
        if user and name:
            info = article_info.get(name, {"status": "অপর্যালোচিত", "hasConflict": False, "multiJuror": False, "jurors": "N/A", "firstJuror": "N/A"})
            user_articles[user].append({"name": name, **info})

    totals = defaultdict(lambda: {"accepted": 0, "unreviewed": 0, "rejected": 0, "total": 0, "conflicts": 0, "articles": []})
    for user, articles in user_articles.items():
        u_s = totals[user]
        for a in articles:
            t_hash = get_title_hash(a["name"])
            c = current_cache.get(t_hash, {"words": 0, "actual_title": a["name"], "is_redirect": False})
            w = c["words"]; u_s["total"] += w
            if a["hasConflict"]: u_s["conflicts"] += 1
            if a["status"] == "গৃহীত হয়েছে": u_s["accepted"] += w
            elif a["status"] == "গৃহীত হয়নি": u_s["rejected"] += w
            else: u_s["unreviewed"] += w
            u_s["articles"].append({
                "title": a["name"], "actualTitle": c["actual_title"], "status": a["status"], "words": w, 
                "isRedirect": c.get("is_redirect", False), "hasConflict": a["hasConflict"],
                "multiJuror": a["multiJuror"], "jurors": a["jurors"], "firstJuror": a.get("firstJuror", "N/A")
            })
    return totals, site_url

def get_articles_data(code):
    data = fetch_fountain_data(code)
    cached = get_all_cached_for_editathon(code)
    return calculate_leaderboard(data, cached)

async def process_word_counts_async(code, queue=None, source="UI"):
    try:
        logging.info(f"[{source}] starting for {code}")
        conn = get_db_connection()
        f_row = conn.execute("SELECT data FROM fountain_cache WHERE code = ?", (code,)).fetchone()
        cached_wordcounts = get_all_cached_for_editathon(code)
        conn.close()
        if f_row:
            totals, site_url = calculate_leaderboard(json.loads(f_row[0]), cached_wordcounts)
            if queue and totals:
                queue.put({"type": "info", "site_url": site_url})
                queue.put({"type": "complete", "data": (totals, site_url)})
                logging.info(f"[{source}] Sent instant DB state for {code}")
        if source == "UI":
            threading.Thread(target=lambda: asyncio.run(refresh_editathon_data(code, queue)), daemon=True).start()
            if not f_row:
                data = await refresh_editathon_data(code, queue)
                if data:
                    totals, site_url = calculate_leaderboard(data, get_all_cached_for_editathon(code))
                    if queue: queue.put({"type": "info", "site_url": site_url}); queue.put({"type": "complete", "data": (totals, site_url)})
        else: await refresh_editathon_data(code, queue)
    except Exception as e:
        logging.error(f"[{source}] Error: {str(e)}")
        if queue: queue.put({"type": "error", "message": str(e)})
    finally:
        if queue: queue.put("DONE")

async def refresh_editathon_data(code, queue=None):
    try:
        data = fetch_fountain_data(code, force_fresh=True)
        wiki_code = data.get("wiki", "wiki:bn")
        site_url = get_wiki_url(wiki_code)
        api_url = f"https://{site_url}/w/api.php"
        cached_wordcounts = get_all_cached_for_editathon(code)
        tasks = []
        for article in data.get("articles", []):
            name, t_hash = normalize_title(article.get("name", "")), get_title_hash(article.get("name", ""))
            if name and (t_hash not in cached_wordcounts or cached_wordcounts[t_hash]["words"] == 0):
                tasks.append({"user": article.get("user"), "title": name})
        if tasks:
            logging.info(f"[Refresh] Processing {len(tasks)} articles for {code}")
            async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
                conn = get_db_connection()
                sem = asyncio.Semaphore(5)
                async def run_task(t):
                    async with sem:
                        words, actual, redir, status = await count_words_async(session, api_url, t["title"], site_url)
                        if words is not None:
                            save_article_to_cache(code, {"title": t["title"], "actual_title": actual, "words": words, "is_redirect": redir, "timestamp": status}, conn=conn)
                await asyncio.gather(*[run_task(t) for t in tasks])
                conn.commit(); conn.close()
            if queue:
                updated_totals, site_url = calculate_leaderboard(data, get_all_cached_for_editathon(code))
                queue.put({"type": "complete", "data": (updated_totals, site_url)})
        logging.info(f"[Refresh] Done for {code}")
        return data
    except Exception as e:
        logging.error(f"[Refresh] Error for {code}: {e}")
        return None

def get_word_counts(code):
    q = Queue()
    threading.Thread(target=lambda: asyncio.run(process_word_counts_async(code, q, source="UI"))).start()
    while True:
        item = q.get()
        if item == "DONE": break
        yield item

def background_monitor():
    while True:
        try:
            editathons = get_bn_editathons()
            cutoff_date = datetime(2026, 1, 1)
            relevant_editathons = []
            for e in editathons:
                try:
                    finish = datetime.strptime(e.get('finish', '1970-01-01T00:00:00Z'), "%Y-%m-%dT%H:%M:%SZ")
                    if finish >= cutoff_date: relevant_editathons.append(e)
                except: relevant_editathons.append(e)
            relevant_editathons.sort(key=lambda e: e.get('finish', ''), reverse=True)
            logging.info(f"[Monitor] Starting cycle for {len(relevant_editathons)} recent editathons (2026+)")
            for e in relevant_editathons:
                asyncio.run(process_word_counts_async(e['code'], source="Monitor"))
                time.sleep(5)
            conn = get_db_connection()
            conn.execute("INSERT OR REPLACE INTO monitor_status (key, last_run) VALUES (?, ?)", ("main", datetime.now().isoformat()))
            conn.commit(); conn.close()
            logging.info("[Monitor] Cycle complete.")
        except Exception as ex: 
            logging.error(f"[Monitor] Error: {str(ex)}")
        time.sleep(900)

def realtime_stream_monitor():
    url = 'https://stream.wikimedia.org/v2/stream/recentchange'
    while True:
        try:
            with requests.get(url, stream=True, timeout=(5, 300), headers={"User-Agent": USER_AGENT}) as response:
                if response.status_code != 200: time.sleep(30); continue
                client = EventSource(response)
                for event in client.events():
                    if not event.data: continue
                    try:
                        change = json.loads(event.data)
                        if change.get('wiki') == 'bnwiki' and change.get('namespace') == 0:
                            title = normalize_title(change.get('title'))
                            t_hash = get_title_hash(title)
                            conn = get_db_connection()
                            exists = conn.execute('SELECT DISTINCT editathon_code FROM wordcount_cache WHERE title_hash = ?', (t_hash,)).fetchall()
                            conn.close()
                            if exists:
                                for code in [row[0] for row in exists]:
                                    threading.Thread(target=lambda c=code: asyncio.run(process_word_counts_async(c, source=f"Realtime")), daemon=True).start()
                    except: pass
        except: time.sleep(10)

threading.Thread(target=background_monitor, daemon=True).start()
threading.Thread(target=realtime_stream_monitor, daemon=True).start()

def get_jury_stats_data(code):
    data = fetch_fountain_data(code); stats = defaultdict(lambda: {"total": 0, "accepted": 0, "rejected": 0})
    conflicts = []
    for art in data.get("articles", []):
        name = art.get("name")
        marks = art.get("marks", [])
        if not marks: continue
        
        decisions = [m.get("marks", {}).get("0") for m in marks if "0" in m.get("marks", {})]
        has_conflict = False
        if len(set(decisions)) > 1:
            if 0 in decisions and (1 in decisions or 2 in decisions): has_conflict = True
        
        # Add to multi-juror list if more than 1 mark exists
        if len(marks) > 1:
            juror_marks = []
            for i, m in enumerate(marks):
                u = m.get("user") or m.get("userName") or m.get("user_name") or "N/A"
                d_val = m.get("marks", {}).get("0")
                d_str = "গৃহীত" if d_val == 0 else "বাতিল" if d_val in [1, 2] else "অনির্ধারিত"
                juror_marks.append({
                    "user": u, 
                    "decision": d_str, 
                    "status": "accepted" if d_val == 0 else "rejected" if d_val in [1, 2] else "unknown",
                    "isFirst": i == 0
                })
            conflicts.append({"title": name, "jurors": juror_marks, "hasConflict": has_conflict})


        for rev in marks:
            u = rev.get("user")
            if u:
                stats[u]["total"] += 1; m = rev.get("marks", {}).get("0")
                if m == 0: stats[u]["accepted"] += 1
                elif m in [1, 2]: stats[u]["rejected"] += 1
    sorted_j = sorted(stats.items(), key=lambda x: x[1]["total"], reverse=True)
    wt = '{| class="wikitable sortable"\n! # !! পর্যালোচক !! মোট !! গৃহীত !! বাতিল\n'
    t_t, t_a, t_r = 0, 0, 0
    for i, (j, s) in enumerate(sorted_j, 1):
        wt += f"|-\n| {i} || {j} || {s['total']} || {s['accepted']} || {s['rejected']}\n"
        t_t += s['total']; t_a += s['accepted']; t_r += s['rejected']
    return {"stats": sorted_j, "conflicts": conflicts}, wt + f"|-\n! মোট ||  || {t_t} || {t_a} || {t_r}\n|}}"

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
    wt = '{| class="wikitable sortable"\n! ক্রমিক !! নিবন্ধের নাম\n'
    for i, n in enumerate(rej, 1): wt += f"|-\n| {i} || {n}\n"
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
