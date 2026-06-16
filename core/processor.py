import re
import asyncio
import aiohttp
import json
import logging
import random
import time
from collections import defaultdict
from core.config import USER_AGENT, tracked_hashes
from core.logger import smart_log, log_cleaned_article
from core.db import db
from core.utils import normalize_title, get_title_hash, get_wiki_url, get_article_status, to_bn, get_wiki_dbname
from core.api import fetch_fountain_data, fetch_fountain_data_async, get_session

# Task Deduplication Registry Helper
def get_pending_refreshes():
    loop = asyncio.get_running_loop()
    if not hasattr(loop, "_pending_refreshes"):
        loop._pending_refreshes = {}
    return loop._pending_refreshes

def save_article_to_cache(code, res, wiki=None, conn=None):
    title, t_hash = normalize_title(res["title"]), get_title_hash(res["title"])
    if wiki:
        tracked_hashes.add(f"{wiki}:{t_hash}")
    else:
        tracked_hashes.add(t_hash) # Legacy fallback
        
    sql = '''INSERT OR REPLACE INTO wordcount_cache (editathon_code, title_hash, article_title, words, actual_title, is_redirect, last_updated, wiki)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''
    vals = (code, t_hash, title, res["words"], res["actual_title"], res["is_redirect"], res["timestamp"], wiki)
    if conn: conn.cursor().execute(sql, vals)
    else:
        with db as conn: conn.cursor().execute(sql, vals)
    # smart_log(f"[DB] Saved: {title} ({res['words']} words)") # Too verbose for large syncs

async def count_words_async(session, api_url, title, site_url, code=None):
    is_bn = site_url.startswith('bn.')
    params = {
        "action": "query",
        "prop": "extracts|revisions" if is_bn else "extracts",
        "explaintext": "1",
        "titles": title,
        "format": "json",
        "redirects": "1",
        "origin": "*"
    }
    if is_bn:
        params["rvprop"] = "content"
        params["rvslots"] = "main"
    
    # Use a loop-bound semaphore to prevent "different event loop" errors in multi-loop environments
    loop = asyncio.get_running_loop()
    if not hasattr(loop, "_api_semaphore"):
        loop._api_semaphore = asyncio.Semaphore(5)
        
    async with loop._api_semaphore:
        for attempt in range(5):
            try:
                # Small jittered delay to prevent simultaneous burst, but avoid blocking first attempt
                if attempt > 0:
                    await asyncio.sleep(attempt * 2.0 + random.uniform(0.1, 0.5))
                else:
                    await asyncio.sleep(random.uniform(0.05, 0.2)) 
                
                async with session.get(api_url, params=params) as res:
                    if res.status in [429, 503]:
                        smart_log(f"[API] Rate limited (HTTP {res.status}) for {title}. Retry {attempt+1} in {2**(attempt+1)}s...", component="live")
                        await asyncio.sleep(2 ** (attempt + 1))
                        continue
                        
                    if res.status != 200:
                        smart_log(f"[API] HTTP {res.status} for {title}. Retrying...", "ERROR")
                        continue
                    
                    data = await res.json()
                    if "error" in data:
                        if data["error"].get("code") == "missingtitle": return 0, title, False, "MISSING"
                        continue
                    
                    pages = data.get("query", {}).get("pages", {})
                    if not pages:
                        continue
                        
                    page_id = list(pages.keys())[0]
                    if page_id == "-1":
                        return 0, title, False, "MISSING"
                        
                    page_data = pages[page_id]
                    actual_title = page_data.get("title", title)
                    is_redirect = "redirects" in data.get("query", {})
                    
                    if is_bn:
                        revisions = page_data.get("revisions", [])
                        if revisions:
                            content = revisions[0].get("slots", {}).get("main", {}).get("*", "")
                            
                            # 1. Strip comments
                            content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
                            # 2. Strip math tags and content
                            content = re.sub(r'<math>.*?</math>', ' ', content, flags=re.DOTALL | re.IGNORECASE)
                            # 3. Strip ref tags and content
                            content = re.sub(r'<ref.*?>.*?</ref>', ' ', content, flags=re.DOTALL | re.IGNORECASE)
                            content = re.sub(r'<ref.*?>', ' ', content, flags=re.IGNORECASE)
                            # 4. Strip images/categories/files
                            content = re.sub(r'\[\[(File|Image|Category|চিত্র|ছবি|বিষয়শ্রেণী):.*?\]\]', '', content, flags=re.IGNORECASE | re.DOTALL)
                            # 5. Strip templates (rough removal of markers)
                            content = re.sub(r'\{\{[^|}]+\|', ' ', content)
                            content = content.replace('}}', ' ').replace('{{', ' ')
                            # 6. Strip template parameters like 1=
                            content = re.sub(r'\|\s*\d+\s*=', ' ', content)
                            content = re.sub(r'^\s*\d+\s*=', ' ', content, flags=re.MULTILINE)
                            # 7. Strip HTML tags
                            content = re.sub(r'<[^>]+>', ' ', content)
                            # 8. Strip wikitext formatting
                            content = content.replace("'''", "").replace("''", "")
                            content = re.sub(r'^==+.*==+$', '', content, flags=re.MULTILINE)
                            content = re.sub(r'^[;:*#]+', '', content, flags=re.MULTILINE)
                            # 9. Replace punctuation with spaces
                            content = re.sub(r'[।\.,\?\!\(\)\[\]\{\}:;=\-_\|]', ' ', content)
                            
                            # Save cleaned text for auditing (as requested by user)
                            log_cleaned_article(actual_title, content)
                            
                            # Count Bengali words (tokens containing at least one Bengali char and no Latin)
                            tokens = content.split()
                            bengali_words = [t for t in tokens if re.search(r'[\u0980-\u09FF]', t) and not re.search(r'[a-zA-Z]', t)]
                            words = len(bengali_words)
                        else:
                            content = page_data.get("extract", "")
                            words = len(re.findall(r'[\u0980-\u09FF]+', content))
                    else:
                        content = page_data.get("extract", "")
                        words = len([w for w in content.split() if len(w) > 0])
                    
                    return words, actual_title, is_redirect, "LIVE"
                    
            except Exception as e:
                smart_log(f"API Exception for {title}: {str(e)}", "ERROR")
                await asyncio.sleep(3)
    
    # Resiliency: Fallback to STALE data if all retries fail
    if code:
        try:
            t_hash = get_title_hash(title)
            with db as conn:
                row = conn.execute("SELECT words, actual_title, is_redirect FROM wordcount_cache WHERE editathon_code = ? AND title_hash = ?", (code, t_hash)).fetchone()
                if row:
                    smart_log(f"[Resiliency] API failed for {title}, serving STALE data", "INFO")
                    return row[0], row[1], bool(row[2]), "STALE"
        except: pass
        
    return None, title, False, "ERROR"

def get_all_cached_for_editathon(code):
    with db as conn:
        rows = conn.cursor().execute('''
            SELECT title_hash, words, actual_title, is_redirect, last_updated, article_title 
            FROM wordcount_cache INDEXED BY idx_editathon_code WHERE editathon_code = ?
        ''', (code,)).fetchall()
    return {r[0]: {"words": r[1], "actual_title": r[2], "is_redirect": bool(r[3]), "last_updated": r[4], "article_title": r[5]} for r in rows}

def get_banned_users(code):
    try:
        with db as conn:
            rows = conn.execute("SELECT username FROM banned_users WHERE editathon_code = ?", (code,)).fetchall()
            return [r[0] for r in rows]
    except:
        return []

def calculate_leaderboard(data, current_cache, banned_users=None):
    if not data: return None, None
    editathon_code = data.get("code")
    if not banned_users and editathon_code:
        banned_users = get_banned_users(editathon_code)
    
    banned_users = set(banned_users or [])
    wiki_code = data.get("wiki", "wiki:bn")
    site_url = get_wiki_url(wiki_code)
    totals = defaultdict(lambda: {"accepted": 0, "unreviewed": 0, "rejected": 0, "total": 0, "count": 0, "articles": [], "isBanned": False})
    
    for art in data.get("articles", []):
        user = art.get("user")
        if not user: continue
        name = normalize_title(art.get("name", ""))
        t_hash = get_title_hash(name)
        marks = art.get("marks", [])
        status = get_article_status(marks)
        
        # Extract reviewer names
        jurors = ", ".join([m.get("user") or m.get("userName") or "N/A" for m in marks])
        
        c = current_cache.get(t_hash, {"words": 0, "actual_title": name, "is_redirect": False})
        w = c["words"]
        u_s = totals[user]
        u_s["total"] += w
        u_s["count"] += 1
        u_s["isBanned"] = user in banned_users
        
        if status == "গৃহীত হয়েছে": u_s["accepted"] += w
        elif status == "গৃহীত হয়নি": u_s["rejected"] += w
        else: u_s["unreviewed"] += w
        u_s["articles"].append({
            "title": name, 
            "actualTitle": c["actual_title"] if c["actual_title"] != name else "", 
            "status": status, 
            "words": w, 
            "isRedirect": c.get("is_redirect", False),
            "jurors": jurors,
            "multiJuror": len(marks) > 1
        })
    return totals, site_url

def get_jury_stats_core(data):
    from datetime import datetime, timedelta
    stats = defaultdict(lambda: {"total": 0, "accepted": 0, "rejected": 0})
    conflicts = []
    stale_threshold = datetime.now() - timedelta(hours=48)
    
    for art in data.get("articles", []):
        name = art.get("name")
        marks = art.get("marks", [])
        is_stale = False
        if not marks:
            try:
                added_date = datetime.strptime(art.get("dateAdded"), "%Y-%m-%dT%H:%M:%SZ")
                if added_date < stale_threshold: is_stale = True
            except: pass

        decisions = [m.get("marks", {}).get("0") for m in marks if "0" in m.get("marks", {})]
        has_conflict = len(set(decisions)) > 1 and 0 in decisions and (1 in decisions or 2 in decisions)
        
        # Only include articles with actual multiple reviews or a clear conflict
        if len(marks) > 1:
            juror_marks = []
            for i, m in enumerate(marks):
                u = m.get("user") or m.get("userName") or "N/A"
                d_val = m.get("marks", {}).get("0")
                d_str = "গৃহীত" if d_val == 0 else "বাতিল" if d_val in [1, 2] else "অনির্ধারিত"
                juror_marks.append({"user": u, "decision": d_str, "status": "accepted" if d_val == 0 else "rejected" if d_val in [1, 2] else "unknown", "isFirst": i == 0})
            
            conflicts.append({"title": name, "jurors": juror_marks, "hasConflict": has_conflict, "isStale": is_stale})

        for i, rev in enumerate(marks):
            u = rev.get("user")
            if u:
                if i == 0:
                    stats[u]["total"] += 1
                    m = rev.get("marks", {}).get("0")
                    if m == 0: stats[u]["accepted"] += 1
                    elif m in [1, 2]: stats[u]["rejected"] += 1
                else:
                    # Secondary judgments (subtract from "actual" stats by tracking separately)
                    stats[u]["secondary"] = stats[u].get("secondary", 0) + 1
                
    sorted_j = sorted(stats.items(), key=lambda x: x[1]["total"], reverse=True)
    return sorted_j, conflicts

def get_daily_stats_core(data, current_cache):
    if not data: return []
    
    daily_data = defaultdict(lambda: {"count": 0, "words": 0})
    
    for art in data.get("articles", []):
        name = normalize_title(art.get("name", ""))
        t_hash = get_title_hash(name)
        
        # Get date added (YYYY-MM-DD)
        date_str = art.get("dateAdded")
        if not date_str: continue
        
        try:
            day = date_str.split('T')[0]
            c = current_cache.get(t_hash, {"words": 0})
            w = c["words"]
            
            daily_data[day]["count"] += 1
            daily_data[day]["words"] += w
        except: continue
        
    sorted_days = sorted(daily_data.keys())
    result = []
    cumulative_count = 0
    cumulative_words = 0
    
    for day in sorted_days:
        stats = daily_data[day]
        cumulative_count += stats["count"]
        cumulative_words += stats["words"]
        result.append({
            "date": day,
            "daily_count": stats["count"],
            "daily_words": stats["words"],
            "total_count": cumulative_count,
            "total_words": cumulative_words
        })
        
    return result

async def refresh_editathon_data(code, queue=None, target_article=None, component=None):
    # Deduplication: If already refreshing, wait for it instead of starting a new one
    pending = get_pending_refreshes()
    if code in pending and not target_article:
        smart_log(f"[{code}] Refresh already in progress, joining wait pool", component=component)
        await pending[code].wait()
        return None

    refresh_event = asyncio.Event()
    if not target_article: pending[code] = refresh_event
    
    try:
        data = await fetch_fountain_data_async(code, force_fresh=True)
        wiki_code = data.get("wiki", "wiki:bn")
        wiki_dbname = get_wiki_dbname(wiki_code)
        site_url = get_wiki_url(wiki_code)
        api_url = f"https://{site_url}/w/api.php"
        cached_wordcounts = get_all_cached_for_editathon(code)
        
        tasks = []
        target_hash = get_title_hash(target_article) if target_article else None
        
        # Professional throttling: Use a smaller semaphore for API calls to avoid 429s
        sem = asyncio.Semaphore(3) 

        # Article Synchronization: Remove entries from DB that are no longer in Fountain
        current_fountain_hashes = set()
        for article in data.get("articles", []):
            name, t_hash = normalize_title(article.get("name", "")), get_title_hash(article.get("name", ""))
            if name:
                current_fountain_hashes.add(t_hash)
                tracked_hashes.add(f"{wiki_dbname}:{t_hash}")
                should_update = False
                if target_hash and t_hash == target_hash:
                    should_update = True
                    smart_log(f"[{code}] Targeted update for: {name} on {wiki_dbname}", component=component)
                elif t_hash not in cached_wordcounts or cached_wordcounts[t_hash]["words"] == 0:
                    should_update = True

                if should_update:
                    tasks.append({"user": article.get("user"), "title": name, "marks": article.get("marks", [])})

        # Perform deletion of stale records (articles removed from Fountain)
        stale_hashes = set(cached_wordcounts.keys()) - current_fountain_hashes
        if stale_hashes and not target_article:
            smart_log(f"[{code}] Found {len(stale_hashes)} stale articles. Removing from local DB.", component=component)
            with db as conn:
                for s_hash in stale_hashes:
                    art_title = cached_wordcounts[s_hash].get("article_title", "Unknown")
                    conn.execute("DELETE FROM wordcount_cache WHERE editathon_code = ? AND title_hash = ?", (code, s_hash))
                    smart_log(f"[{code}] Removed: {art_title} ({s_hash})", component=component)
                    # Note: We don't remove from tracked_hashes as it might be in other editathons

        if tasks:
            smart_log(f"[{code}] Refreshing {len(tasks)} articles", component=component)
            session = await get_session()
            
            # Batch updates to the queue to prevent flooding the frontend/network
            batch_size = 5
            current_batch = []
            
            async def run_task(t):
                async with sem:
                    try:
                        words, actual, redir, status_ts = await count_words_async(session, api_url, t["title"], site_url, code=code)
                        if words is not None:
                            # Write to DB individually to avoid long-held transactions
                            save_article_to_cache(code, {"title": t["title"], "actual_title": actual, "words": words, "is_redirect": redir, "timestamp": status_ts}, wiki=wiki_dbname)
                            
                            update_msg = {
                                "user": t["user"], 
                                "title": t["title"], 
                                "actual_title": actual, 
                                "words": words, 
                                "status": get_article_status(t["marks"]), 
                                "is_redirect": redir,
                                "jurors": ", ".join([m.get("user") or m.get("userName") or "N/A" for m in t["marks"]]),
                                "multiJuror": len(t["marks"]) > 1
                            }
                            
                            if queue:
                                current_batch.append(update_msg)
                                if len(current_batch) >= batch_size:
                                    await queue.put({"type": "update", "articles": list(current_batch)})
                                    current_batch.clear()
                    except Exception as inner_e:
                        smart_log(f"Task error for {t['title']}: {inner_e}", "ERROR")
            
            # Process in parallel with controlled concurrency
            await asyncio.gather(*[run_task(t) for t in tasks])
            
            # Flush final batch
            if queue and current_batch:
                await queue.put({"type": "update", "articles": current_batch})
        else:
            smart_log(f"[{code}] No articles need refreshing", component=component)
            
        if queue:
            updated_totals, site_url = calculate_leaderboard(data, get_all_cached_for_editathon(code))
            await queue.put({"type": "complete", "data": (updated_totals, site_url)})
        
        return data
    except Exception as e:
        smart_log(f"Refresh Error for {code}: {e}", "ERROR")
        return None
    finally:
        refresh_event.set()
        if not target_article: pending.pop(code, None)

async def process_word_counts_async(code, queue=None, source="UI", target_article=None):
    try:
        smart_log(f"[{source}] Starting for {code}" + (f" (target: {target_article})" if target_article else ""))
        
        # Immediate ping to start the stream
        if queue: await queue.put({"type": "ping", "ts": time.time()})
        
        with db as conn:
            f_row = conn.execute("SELECT data FROM fountain_cache WHERE code = ?", (code,)).fetchone()
        cached_wordcounts = get_all_cached_for_editathon(code)
        if f_row:
            totals, site_url = calculate_leaderboard(json.loads(f_row[0]), cached_wordcounts)
            if queue and totals:
                await queue.put({"type": "info", "site_url": site_url})
                await queue.put({"type": "cache", "data": (totals, site_url)})
                smart_log(f"[{source}] Sent instant DB state (cache) for {code}")
        
        # Periodic heartbeat in background while refresh runs
        async def heartbeat():
            while True:
                await asyncio.sleep(10)
                if queue: await queue.put({"type": "ping", "ts": time.time()})
        
        hb_task = asyncio.create_task(heartbeat())
        try:
            await refresh_editathon_data(code, queue, target_article=target_article, component=("sync" if source == "Monitor" else "live" if "Realtime" in source else None))
        finally:
            hb_task.cancel()
            
    except Exception as e:
        smart_log(f"[{source}] Error: {str(e)}", "ERROR")
        if queue: await queue.put({"type": "error", "message": str(e)})
    finally:
        if queue: 
            await queue.put("DONE")
            smart_log(f"[{source}] Sent DONE to queue")
