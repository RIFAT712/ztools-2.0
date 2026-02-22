import os
import re
import random
import json
import sqlite3
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import requests
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants and Configuration
DB_FILE = "ztools.db"

WIKI_PREFIXES = {
    "wiki": "wikipedia",
    "wikt": "wiktionary",
    "b": "wikibooks",
    "voy": "wikivoyage",
    "q": "wikiquote",
    "s": "wikisource",
    "n": "wikinews"
}

# Persistent Session for requests
session = requests.Session()
# Set a proper User-Agent as required by Wikimedia API
USER_AGENT = os.getenv("USER_AGENT", "ZTools/1.0 (https://github.com/yourusername/ztools) python-requests/2.32.3")
session.headers.update({
    'User-Agent': USER_AGENT
})

def init_db():
    """Initializes the SQLite database and migrates data from JSON if exists."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wordcount_cache (
            editathon_code TEXT,
            article_title TEXT,
            words INTEGER,
            actual_title TEXT,
            is_redirect BOOLEAN,
            last_updated TEXT,
            PRIMARY KEY (editathon_code, article_title)
        )
    ''')
    
    # Migration from JSON to SQLite
    json_file = "wordcount.json"
    if os.path.exists(json_file):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                for code, articles in old_data.items():
                    for title, info in articles.items():
                        cursor.execute('''
                            INSERT OR REPLACE INTO wordcount_cache 
                            (editathon_code, article_title, words, actual_title, is_redirect, last_updated)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (
                            code, title, info.get("words", 0), 
                            info.get("actual_title", ""), 
                            info.get("is_redirect", False), 
                            info.get("last_updated")
                        ))
            conn.commit()
            os.rename(json_file, json_file + ".bak") # Backup old file
            print("Migration from JSON to SQLite successful.")
        except Exception as e:
            print(f"Migration failed: {e}")
            
    conn.commit()
    conn.close()

# Initialize DB on import
init_db()

def get_cached_article(code, title):
    """Fetches a single article from the SQLite cache."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT words, actual_title, is_redirect, last_updated 
        FROM wordcount_cache 
        WHERE editathon_code = ? AND article_title = ?
    ''', (code, title))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "words": row[0],
            "actual_title": row[1],
            "is_redirect": bool(row[2]),
            "last_updated": row[3]
        }
    return None

def save_article_to_cache(code, res):
    """Saves a single article result to the SQLite cache."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO wordcount_cache 
        (editathon_code, article_title, words, actual_title, is_redirect, last_updated)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        code, res["title"], res["words"], 
        res["actual_title"], res["is_redirect"], res["timestamp"]
    ))
    conn.commit()
    conn.close()

def get_all_cached_for_editathon(code):
    """Fetches all cached articles for a specific editathon."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT article_title, words, actual_title, is_redirect, last_updated 
        FROM wordcount_cache WHERE editathon_code = ?
    ''', (code,))
    rows = cursor.fetchall()
    conn.close()
    
    result = {}
    for r in rows:
        result[r[0]] = {
            "words": r[1],
            "actual_title": r[2],
            "is_redirect": bool(r[3]),
            "last_updated": r[4]
        }
    return result

# Simple In-Memory Cache for fast repeated loads
cache = {
    "editathons": {"data": None, "expiry": 0},
    "details": {},  # code: {"data": None, "expiry": 0}
    "wordcounts": {} # code: {"data": None, "expiry": 0}
}



def get_articles_metadata(titles, site_url):
    """Fetches last revision timestamps for a list of article titles in parallel batches."""
    api_url = f"https://{site_url}/w/api.php"
    metadata = {}
    
    batches = [titles[i:i+50] for i in range(0, len(titles), 50)]
    
    def fetch_batch(batch):
        params = {
            "action": "query",
            "titles": "|".join(batch),
            "prop": "revisions",
            "rvprop": "timestamp",
            "format": "json",
            "redirects": "true"
        }
        try:
            res = session.get(api_url, params=params, timeout=10)
            if res.status_code == 200:
                return res.json(), batch
        except Exception as e:
            print(f"Batch fetch failed: {e}")
        return None, batch

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fetch_batch, batches))

    for data, batch in results:
        if not data: continue
        query = data.get("query", {})
        pages = query.get("pages", {})
        
        norm_map = {n["from"]: n["to"] for n in query.get("normalized", [])}
        redir_map = {r["from"]: r["to"] for r in query.get("redirects", [])}
        
        final_to_orig = defaultdict(list)
        for orig in batch:
            current = orig
            if current in norm_map: current = norm_map[current]
            while current in redir_map: current = redir_map[current]
            final_to_orig[current].append(orig)
        
        for page_id, page_info in pages.items():
            final_title = page_info.get("title")
            if "revisions" in page_info:
                timestamp = page_info["revisions"][0]["timestamp"]
                for orig in final_to_orig.get(final_title, []):
                    metadata[orig] = {
                        "timestamp": timestamp,
                        "actual_title": final_title
                    }
            
    return metadata


def get_wiki_url(fountain_wiki_code):
    """Parses Fountain wiki code and returns the site URL."""
    if ':' in fountain_wiki_code:
        prefix, lang = fountain_wiki_code.split(':', 1)
    else:
        prefix, lang = "wikipedia", fountain_wiki_code
    site_suffix = WIKI_PREFIXES.get(prefix, "wikipedia")
    return f"{lang}.{site_suffix}.org"


def fetch_fountain_data(code):
    """Fetches editathon data from Fountain API with caching."""
    now = time.time()
    if code in cache["details"] and cache["details"][code]["expiry"] > now:
        return cache["details"][code]["data"]

    resp = session.get(
        f"https://fountain.toolforge.org/api/editathons/{code}", timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # Cache for 5 minutes
    cache["details"][code] = {"data": data, "expiry": now + 300}
    return data


def get_articles_data(code):
    """Processes article data for a given editathon code."""
    fountain_data = fetch_fountain_data(code)
    wiki_code = fountain_data.get("wiki", "wiki:bn")
    site_url = get_wiki_url(wiki_code)

    user_articles = defaultdict(list)
    for article in fountain_data.get("articles", []):
        user = article.get("user")
        name = article.get("name")
        marks = article.get("marks", [])

        # Status logic
        status = "অপর্যালোচিত"
        if marks:
            rejected = any(review.get("marks", {}).get("0")
                           in [1, 2] for review in marks)
            status = "গৃহীত হয়নি" if rejected else "গৃহীত হয়েছে"

        if user and name:
            user_articles[user].append({
                "name": name,
                "status": status,
                "reviews": len(marks)
            })

    return user_articles, site_url


def count_article_words(title, site_url):
    """Counts words in a Wikipedia article after cleaning unwanted HTML tags."""
    api_url = f"https://{site_url}/w/api.php"
    params = {
        "action": "parse",
        "page": title,
        "format": "json",
        "prop": "text",
        "redirects": "true",
        "origin": "*"
    }
    
    # Retry logic
    for attempt in range(3):
        try:
            res = session.get(api_url, params=params, timeout=15)
            
            if res.status_code != 200:
                if res.status_code == 429:
                    # Longer, randomized wait for 429 to avoid thundering herd
                    wait_time = 5 + (random.random() * 5)
                else:
                    wait_time = 1
                
                print(f"Error {res.status_code} for {title} (Attempt {attempt+1}), waiting {wait_time:.1f}s")
                time.sleep(wait_time)
                continue

            try:
                data = res.json()
            except Exception as json_err:
                snippet = res.text[:200] if res.text else "(empty response)"
                print(f"JSON Error for {title}: {json_err}. Snippet: {snippet} (Attempt {attempt+1})")
                time.sleep(1)
                continue

            if "error" in data:
                return 0, title, False

            actual_title = data["parse"]["title"]
            html_content = data["parse"]["text"]["*"]
            soup = BeautifulSoup(html_content, 'html.parser')

            unwanted_selectors = [
                '.mw-empty-elt', '.mw-editsection', '.reference', '.references', '.reflist',
                '.mbox-small', '.ambox', '.navbox', '.catlinks', '.noprint', '.metadata',
                '.portal', 'style', 'script', '.thumbinner', '.listing-lastedit'
            ]
            for selector in unwanted_selectors:
                for tag in soup.select(selector):
                    tag.decompose()

            content_text = soup.get_text()

            if site_url.startswith('bn.'):
                words = len(re.findall(r'[\u0980-\u09FF]+', content_text))
            else:
                words = len(content_text.split())

            return words, actual_title, actual_title != title
        except Exception as e:
            print(f"Request failed for {title}: {e} (Attempt {attempt+1})")
            time.sleep(1)
            
    return 0, title, False


def get_word_counts(code):
    """Fetches all articles for an editathon and counts words with SQLite caching. Yields updates for live processing."""
    now = time.time()
    if code in cache["wordcounts"] and cache["wordcounts"][code]["expiry"] > now:
        yield {"type": "complete", "data": cache["wordcounts"][code]["data"]}
        return

    user_articles, site_url = get_articles_data(code)
    yield {"type": "info", "site_url": site_url}
    
    # Load cache for this editathon
    cached_data = get_all_cached_for_editathon(code)
    
    all_titles = []
    for user, articles in user_articles.items():
        for a in articles:
            all_titles.append(a["name"])

    # Fetch last revision metadata for all articles (parallelized)
    metadata = get_articles_metadata(all_titles, site_url)

    up_to_date_cached = []
    tasks_to_run = []
    for user, articles in user_articles.items():
        for a in articles:
            title = a["name"]
            is_uptodate = False
            
            m = metadata.get(title)
            if title in cached_data and m:
                if cached_data[title].get("last_updated") == m["timestamp"]:
                    is_uptodate = True

            if is_uptodate:
                c = cached_data[title]
                up_to_date_cached.append({
                    "user": user,
                    "title": title,
                    "actual_title": c["actual_title"],
                    "status": a["status"],
                    "words": c["words"],
                    "is_redirect": c["is_redirect"]
                })
            else:
                tasks_to_run.append({
                    "user": user,
                    "title": title,
                    "status": a["status"]
                })

    if up_to_date_cached:
        yield {"type": "update", "articles": up_to_date_cached}

    # Process only the articles that need counting
    def process_task(task):
        time.sleep(0.05)
        words, actual_title, is_redirect = count_article_words(task["title"], site_url)
        ts = None
        m = metadata.get(task["title"])
        if m:
            ts = m["timestamp"]
            actual_title = m["actual_title"]
        return {
            "user": task["user"],
            "title": task["title"],
            "actual_title": actual_title,
            "status": task["status"],
            "words": words,
            "is_redirect": is_redirect,
            "timestamp": ts
        }

    if tasks_to_run:
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_task = {executor.submit(process_task, t): t for t in tasks_to_run}
            for future in as_completed(future_to_task):
                try:
                    res = future.result()
                    # Instant SQLite save for each article
                    save_article_to_cache(code, res)
                    yield {"type": "update", "articles": [res]}
                except Exception as e:
                    print(f"Error processing article: {e}")

    # Build final summary for memory cache
    cached_data = get_all_cached_for_editathon(code) # Refresh after updates
    totals = defaultdict(lambda: {
        "accepted": 0, "unreviewed": 0, "rejected": 0, "total": 0, "articles": []
    })
    for user, articles in user_articles.items():
        user_stats = totals[user]
        for a in articles:
            title = a["name"]
            status = a["status"]
            c = cached_data.get(title, {"words": 0, "actual_title": title, "is_redirect": False})
            
            words = c["words"]
            user_stats["total"] += words
            if status == "গৃহীত হয়েছে":
                user_stats["accepted"] += words
            elif status == "গৃহীত হয়নি":
                user_stats["rejected"] += words
            else:
                user_stats["unreviewed"] += words

            user_stats["articles"].append({
                "title": title,
                "actualTitle": c["actual_title"] if c["actual_title"] != title else "",
                "status": status,
                "words": words,
                "isRedirect": c["is_redirect"]
            })

    cache["wordcounts"][code] = {"data": (totals, site_url), "expiry": time.time() + 300}
    yield {"type": "done"}




def get_rejected_articles_data(code):
    """Fetches articles and filters for those with 'গৃহীত হয়নি' status, generating a Wikitable."""
    user_articles, site_url = get_articles_data(code)
    rejected_articles = []
    for user, articles in user_articles.items():
        for a in articles:
            if a["status"] == "গৃহীত হয়নি":
                rejected_articles.append(a["name"])

    def to_bn_local(n):
        bn_digits = "০১২৩৪৫৬৭৮৯"
        return "".join(bn_digits[int(d)] if d.isdigit() else d for d in str(n))

    wikitable = '{| class="wikitable sortable"\n! ক্রমিক !! নিবন্ধের নাম\n'
    for i, name in enumerate(rejected_articles, 1):
        wikitable += f"|-\n| {to_bn_local(i)} || {name}\n"
    wikitable += "|}"

    return rejected_articles, wikitable


def get_jury_stats_data(code):
    """Processes jury statistics and generates a Wikitable string."""
    fountain_data = fetch_fountain_data(code)

    jury_stats = defaultdict(
        lambda: {"total": 0, "accepted": 0, "rejected": 0})
    for article in fountain_data.get("articles", []):
        for review in article.get("marks", []):
            jury = review.get("user")
            if not jury:
                continue

            stats = jury_stats[jury]
            stats["total"] += 1
            decision = review.get("marks", {}).get("0")
            if decision == 0:
                stats["accepted"] += 1
            elif decision in [1, 2]:
                stats["rejected"] += 1

    sorted_juries = sorted(
        jury_stats.items(), key=lambda x: x[1]["total"], reverse=True)

    # Generate Wikitable
    wikitable = '{| class="wikitable sortable"\n! # !! পর্যালোচক !! মোট !! গৃহীত !! বাতিল\n'
    t_tot, t_acc, t_rej = 0, 0, 0

    def to_bn_local(n):
        bn_digits = "০১২৩৪৫৬৭৮৯"
        return "".join(bn_digits[int(d)] if d.isdigit() else d for d in str(n))

    for i, (jury, stats) in enumerate(sorted_juries, 1):
        wikitable += f"|-\n| {to_bn_local(i)} || {jury} || {to_bn_local(stats['total'])} || {to_bn_local(stats['accepted'])} || {to_bn_local(stats['rejected'])}\n"
        t_tot += stats['total']
        t_acc += stats['accepted']
        t_rej += stats['rejected']

    wikitable += f"|-\n! মোট ||  || {to_bn_local(t_tot)} || {to_bn_local(t_acc)} || {to_bn_local(t_rej)}\n|}}"

    return sorted_juries, wikitable


def get_user_reviews(code, username):
    """Fetches articles reviewed by a specific user in an editathon."""
    fountain_data = fetch_fountain_data(code)
    wiki_code = fountain_data.get("wiki", "wiki:bn")
    site_url = get_wiki_url(wiki_code)

    user_reviews = []
    for article in fountain_data.get("articles", []):
        for review in article.get("marks", []):
            if review.get("user") == username:
                # Decision logic: 0 is accepted, 1 or 2 is rejected
                decision_val = review.get("marks", {}).get("0")
                decision = "accepted" if decision_val == 0 else "rejected" if decision_val in [
                    1, 2] else "unknown"

                user_reviews.append({
                    "name": article.get("name"),
                    "submitter": article.get("user"),
                    "comment": review.get("comment", ""),
                    "timestamp": article.get("dateAdded"),
                    "decision": decision
                })
                break  # Found the review by this user for this article

    return user_reviews, site_url


def get_user_jury_editathons(username):
    """Fetches editathons where the user is a jury member (recently active ones)."""
    bn_editathons = get_bn_editathons()

    # Only check editathons that finished in the last 6 months to save time
    six_months_ago = datetime.now() - timedelta(days=180)

    recent_bn = []
    for e in bn_editathons:
        finish_str = e.get("finish")
        try:
            # Fountain date format: 2026-02-28T06:00:00Z
            finish_date = datetime.strptime(finish_str, "%Y-%m-%dT%H:%M:%SZ")
            if finish_date > six_months_ago:
                recent_bn.append(e)
        except:
            # If no date, assume recent
            recent_bn.append(e)

    def check_jury(e):
        code = e.get("code")
        try:
            details = fetch_fountain_data(code)
            if username in details.get("jury", []):
                return {"code": code, "name": e.get("name")}
        except:
            pass
        return None

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(check_jury, recent_bn))

    return [r for r in results if r]


def get_bn_editathons():
    """Fetches and filters Bengali editathons from the last 1 year."""
    now = time.time()
    if cache["editathons"]["data"] and cache["editathons"]["expiry"] > now:
        return cache["editathons"]["data"]

    resp = session.get(
        "https://fountain.toolforge.org/api/editathons", timeout=10)
    resp.raise_for_status()
    data = resp.json()

    # Only show editathons from the last 365 days
    one_year_ago = datetime.now() - timedelta(days=365)
    result = []

    for e in data:
        wiki_code = e.get("wiki", "wiki:en")
        lang = wiki_code.split(':', 1)[1] if ':' in wiki_code else wiki_code

        if lang != "bn":
            continue

        finish_str = e.get("finish")
        try:
            finish_date = datetime.strptime(finish_str, "%Y-%m-%dT%H:%M:%SZ")
            if finish_date < one_year_ago:
                continue
        except:
            pass  # If date parsing fails, keep it

        result.append({
            "code": e.get("code"),
            "name": e.get("name"),
            "description": e.get("description"),
            "start": e.get("start"),
            "finish": e.get("finish"),
            "wiki": wiki_code,
            "site_url": get_wiki_url(wiki_code)
        })

    # Cache for 1 hour
    cache["editathons"] = {"data": result, "expiry": now + 3600}
    return result
