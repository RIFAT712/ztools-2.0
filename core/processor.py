import re
import asyncio
import random
import time
from collections import defaultdict
from datetime import datetime, timezone
from core.config import tracked_hashes
from core.logger import smart_log
from core.db import db
from core.utils import normalize_title, get_title_hash, get_wiki_url, get_article_status, get_wiki_dbname
from core.api import fetch_fountain_data, get_session, _cached_fountain

# Task Deduplication Registry Helper
def get_pending_refreshes():
    loop = asyncio.get_running_loop()
    if not hasattr(loop, "_pending_refreshes"):
        loop._pending_refreshes = {}
    return loop._pending_refreshes

RULES_VERSION = 2  # bump whenever count_bn_words changes: stored counts from older rules get recounted once

def save_article_to_cache(code, res, wiki):
    title, t_hash = normalize_title(res["title"]), get_title_hash(res["title"])
    tracked_hashes.add(f"{wiki}:{t_hash}")
    sql = '''INSERT OR REPLACE INTO wordcount_cache (editathon_code, title_hash, article_title, words, actual_title, is_redirect, last_updated, wiki, revid, rules_v)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
    vals = (code, t_hash, title, res["words"], res["actual_title"], res["is_redirect"], res["timestamp"], wiki, res.get("revid"), RULES_VERSION)
    with db as conn: conn.execute(sql, vals)

BATCH_SIZE = 50  # MediaWiki's per-request title limit for non-bot clients

def count_bn_words(content):
    # 1. Strip comments
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    # 2. Strip math tags and content
    content = re.sub(r'<math>.*?</math>', ' ', content, flags=re.DOTALL | re.IGNORECASE)
    # 3. Strip ref tags and content
    content = re.sub(r'<ref.*?>.*?</ref>', ' ', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<ref.*?>', ' ', content, flags=re.IGNORECASE)
    # 4. Strip images/categories/files (\u09af\u09bc: MediaWiki stores NFC text, where precomposed U+09DF never appears)
    content = re.sub(r'\[\[(File|Image|Category|চিত্র|ছবি|বিষ\u09af\u09bcশ্রেণী):.*?\]\]', '', content, flags=re.IGNORECASE | re.DOTALL)
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
    # Count Bengali words (tokens containing at least one Bengali char and no Latin)
    return sum(1 for t in content.split() if re.search(r'[\u0980-\u09FF]', t) and not re.search(r'[a-zA-Z]', t))

def _api_semaphore():
    # Loop-bound semaphore (one per event loop) caps concurrent API calls at 3 to avoid 429s
    loop = asyncio.get_running_loop()
    if not hasattr(loop, "_api_semaphore"):
        loop._api_semaphore = asyncio.Semaphore(3)
    return loop._api_semaphore

async def _api_query(session, api_url, params, label):
    """POST an Action API query with retries. Returns the `query` dict, or None if every attempt failed."""
    async with _api_semaphore():
        for attempt in range(5):
            try:
                if attempt > 0:
                    await asyncio.sleep(attempt * 2.0 + random.uniform(0.1, 0.5))
                # POST: 50 percent-encoded Bengali titles overflow GET URL limits
                async with session.post(api_url, data=params) as res:
                    if res.status in [429, 503]:
                        smart_log(f"[API] Rate limited (HTTP {res.status}) for {label}. Retry {attempt+1} in {2**(attempt+1)}s...", component="live")
                        await asyncio.sleep(2 ** (attempt + 1))
                        continue
                    if res.status != 200:
                        smart_log(f"[API] HTTP {res.status} for {label}. Retrying...", "ERROR")
                        continue
                    data = await res.json()
                if "error" not in data and data.get("query"):
                    return data["query"]
            except Exception as e:
                smart_log(f"API Exception for {label}: {str(e)}", "ERROR")
                await asyncio.sleep(3)
    return None

def _resolve_pages(query, titles):
    """Map each requested title to (page, was_redirect), following the API's normalization and redirects."""
    normalized = {n["from"]: n["to"] for n in query.get("normalized", [])}
    redirects = {r["from"]: r["to"] for r in query.get("redirects", [])}
    pages = {p["title"]: p for p in query.get("pages", [])}
    out = {}
    for t in titles:
        n = normalized.get(t, t)
        page = pages.get(redirects.get(n, n))
        if page: out[t] = (page, n in redirects)
    return out

async def count_words_batch(session, api_url, titles, code=None, at=None):
    """Count words for up to BATCH_SIZE titles in one API call.
    With `at` (an ISO timestamp, single title only) counts the revision live at that moment and marks it FINAL.
    Returns {title: (words, actual_title, is_redirect, status, revid)}; words is None when nothing could be fetched."""
    params = {"action": "query", "prop": "revisions", "rvprop": "content|ids", "rvslots": "main",
              "titles": "|".join(titles), "redirects": "1", "format": "json", "formatversion": "2"}
    if at:
        assert len(titles) == 1, "rvstart only works for a single page"
        params.update({"rvstart": at, "rvdir": "older", "rvlimit": "1"})
    live = "FINAL" if at else "LIVE"
    results = {}
    query = await _api_query(session, api_url, params, f"{len(titles)} titles")
    if query:
        for t, (page, redir) in _resolve_pages(query, titles).items():
            if page.get("missing") or page.get("invalid"):
                results[t] = (0, t, False, "FINAL" if at else "MISSING", None)
            elif page.get("revisions"):
                rev = page["revisions"][0]
                results[t] = (count_bn_words(rev["slots"]["main"].get("content", "")), page["title"], redir, live, rev.get("revid"))
            elif at:
                results[t] = (0, page["title"], redir, live, None)  # page did not exist yet at the deadline
            # else: content cut by the API's result-size limit; retried below

    left = [t for t in titles if t not in results]
    if query and left and len(titles) > 1:
        # Response was truncated (too much content in one reply): retry the rest in halves
        half = (len(left) + 1) // 2
        for part in (left[:half], left[half:]):
            if part: results.update(await count_words_batch(session, api_url, part, code))
        left = [t for t in titles if t not in results]

    # Resiliency: Fallback to STALE data for anything the API couldn't give us
    for t in left:
        row = None
        if code:
            try:
                with db as conn:
                    row = conn.execute("SELECT words, actual_title, is_redirect, revid FROM wordcount_cache WHERE editathon_code = ? AND title_hash = ?", (code, get_title_hash(t))).fetchone()
            except Exception: pass
        if row:
            smart_log(f"[Resiliency] API failed for {t}, serving STALE data", "INFO")
            results[t] = (row[0], row[1], bool(row[2]), "STALE", row[3])
        else:
            results[t] = (None, t, False, "ERROR", None)
    return results

async def fetch_lastrevids(session, api_url, titles):
    """Current revision id for up to BATCH_SIZE titles (no content, so cheap). Missing pages map to None;
    titles the API couldn't answer are left out."""
    query = await _api_query(session, api_url, {"action": "query", "prop": "info", "titles": "|".join(titles),
                                                "redirects": "1", "format": "json", "formatversion": "2"}, f"revids of {len(titles)} titles")
    if not query: return {}
    return {t: page.get("lastrevid") for t, (page, _) in _resolve_pages(query, titles).items()}

def get_all_cached_for_editathon(code):
    with db as conn:
        rows = conn.cursor().execute('''
            SELECT title_hash, words, actual_title, is_redirect, last_updated, article_title, revid, rules_v
            FROM wordcount_cache INDEXED BY idx_editathon_code WHERE editathon_code = ?
        ''', (code,)).fetchall()
    return {r[0]: {"words": r[1], "actual_title": r[2], "is_redirect": bool(r[3]), "last_updated": r[4], "article_title": r[5], "revid": r[6], "rules_v": r[7]} for r in rows}

def get_finish(code):
    """Contest deadline as an ISO string (UTC) if it has passed, else None."""
    with db as conn:
        row = conn.execute("SELECT finish FROM enabled_editathons WHERE code = ?", (code,)).fetchone()
    try:
        finish = datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    return row[0] if datetime.now(timezone.utc) > finish else None

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
    stats = defaultdict(lambda: {"total": 0, "accepted": 0, "rejected": 0})
    conflicts = []
    
    for art in data.get("articles", []):
        name = art.get("name")
        marks = art.get("marks", [])

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
            
            conflicts.append({"title": name, "jurors": juror_marks, "hasConflict": has_conflict})

        # Only the first reviewer's judgment counts
        if marks and (u := marks[0].get("user")):
            stats[u]["total"] += 1
            m = marks[0].get("marks", {}).get("0")
            if m == 0: stats[u]["accepted"] += 1
            elif m in [1, 2]: stats[u]["rejected"] += 1
                
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

async def refresh_editathon_data(code, queue=None, target_article=None, component=None, check_revisions=False):
    # Deduplication: If already refreshing, wait for it instead of starting a new one
    pending = get_pending_refreshes()
    if code in pending and not target_article:
        smart_log(f"[{code}] Refresh already in progress, joining wait pool", component=component)
        await pending[code].wait()
        # A viewer who joined still needs the finished leaderboard, or its progress bar never ends
        if queue and (cached := _cached_fountain(code)):
            totals, site_url = calculate_leaderboard(cached, get_all_cached_for_editathon(code))
            await queue.put({"type": "complete", "data": (totals, site_url)})
        return None

    refresh_event = asyncio.Event()
    if not target_article: pending[code] = refresh_event

    try:
        # A live edit to one article doesn't need a fresh copy of the whole contest from Fountain
        data = await asyncio.to_thread(fetch_fountain_data, code, not target_article)
        wiki_code = data.get("wiki", "wiki:bn")
        wiki_dbname = get_wiki_dbname(wiki_code)
        site_url = get_wiki_url(wiki_code)
        api_url = f"https://{site_url}/w/api.php"
        cached_wordcounts = get_all_cached_for_editathon(code)
        # Finished contests are counted exactly as they stood at the deadline, once, then frozen (FINAL)
        finish = get_finish(code)

        tasks = []
        unchanged = []  # counted already; candidates for the revision-id check
        target_hash = get_title_hash(target_article) if target_article else None

        # Article Synchronization: Remove entries from DB that are no longer in Fountain
        current_fountain_hashes = set()
        for article in data.get("articles", []):
            name, t_hash = normalize_title(article.get("name", "")), get_title_hash(article.get("name", ""))
            if not name: continue
            current_fountain_hashes.add(t_hash)
            tracked_hashes.add(f"{wiki_dbname}:{t_hash}")
            c = cached_wordcounts.get(t_hash)
            task = {"user": article.get("user"), "title": name, "marks": article.get("marks", [])}
            if finish:
                should_update = not c or c["last_updated"] != "FINAL" or c["rules_v"] != RULES_VERSION
            else:
                should_update = not c or c["words"] == 0 or c["rules_v"] != RULES_VERSION or t_hash == target_hash
            if should_update:
                if t_hash == target_hash: smart_log(f"[{code}] Targeted update for: {name} on {wiki_dbname}", component=component)
                tasks.append(task)
            elif not target_article:
                unchanged.append((task, c))

        # Perform deletion of stale records (articles removed from Fountain)
        stale_hashes = set(cached_wordcounts.keys()) - current_fountain_hashes
        if stale_hashes and not current_fountain_hashes:
            # Fountain listing zero articles for a contest we hold counts for is far likelier a glitch than reality
            smart_log(f"[{code}] Fountain lists no articles; keeping {len(stale_hashes)} cached counts", "ERROR")
        elif stale_hashes and not target_article:
            smart_log(f"[{code}] Found {len(stale_hashes)} stale articles. Removing from local DB.", component=component)
            with db as conn:
                for s_hash in stale_hashes:
                    art_title = cached_wordcounts[s_hash].get("article_title", "Unknown")
                    conn.execute("DELETE FROM wordcount_cache WHERE editathon_code = ? AND title_hash = ?", (code, s_hash))
                    smart_log(f"[{code}] Removed: {art_title} ({s_hash})", component=component)
                    # Note: We don't remove from tracked_hashes as it might be in other editathons

        session = await get_session()

        # Catch edits the live stream missed (it drops every few minutes): recount anything whose revision moved
        if check_revisions and not finish and unchanged:
            groups = [unchanged[i:i + BATCH_SIZE] for i in range(0, len(unchanged), BATCH_SIZE)]
            revids = {}
            for r in await asyncio.gather(*[fetch_lastrevids(session, api_url, [t["title"] for t, _ in g]) for g in groups]):
                revids.update(r)
            changed = [t for t, c in unchanged if t["title"] in revids and revids[t["title"]] != c["revid"]]
            if changed:
                smart_log(f"[{code}] {len(changed)} articles changed since last count", component=component)
                tasks += changed

        if tasks:
            smart_log(f"[{code}] Refreshing {len(tasks)} articles" + (" (as of deadline)" if finish else ""), component=component)

            async def run_batch(batch):
                try:
                    counts = await count_words_batch(session, api_url, [t["title"] for t in batch], code=code, at=finish)
                    updates = []
                    for t in batch:
                        words, actual, redir, status_ts, revid = counts[t["title"]]
                        if words is None: continue
                        save_article_to_cache(code, {"title": t["title"], "actual_title": actual, "words": words, "is_redirect": redir, "timestamp": status_ts, "revid": revid}, wiki=wiki_dbname)
                        updates.append({
                            "user": t["user"],
                            "title": t["title"],
                            "actual_title": actual,
                            "words": words,
                            "status": get_article_status(t["marks"]),
                            "is_redirect": redir,
                            "jurors": ", ".join([m.get("user") or m.get("userName") or "N/A" for m in t["marks"]]),
                            "multiJuror": len(t["marks"]) > 1
                        })
                    # Small chunks keep the UI progress bar moving
                    if queue:
                        for i in range(0, len(updates), 5):
                            await queue.put({"type": "update", "articles": updates[i:i + 5]})
                except Exception as inner_e:
                    smart_log(f"Batch error for {code}: {inner_e}", "ERROR")

            # One API call per BATCH_SIZE articles (per article for deadline revisions); _api_semaphore caps concurrency
            size = 1 if finish else BATCH_SIZE
            await asyncio.gather(*[run_batch(tasks[i:i + size]) for i in range(0, len(tasks), size)])
        else:
            smart_log(f"[{code}] No articles need refreshing", component=component)

        if queue:
            updated_totals, site_url = calculate_leaderboard(data, get_all_cached_for_editathon(code))
            await queue.put({"type": "complete", "data": (updated_totals, site_url)})

        return data
    except Exception as e:
        smart_log(f"Refresh Error for {code}: {e}", "ERROR")
        if queue: await queue.put({"type": "error", "message": "তথ্য হালনাগাদ করা যায়নি; সংরক্ষিত তথ্য দেখানো হচ্ছে।"})
        return None
    finally:
        refresh_event.set()
        if not target_article: pending.pop(code, None)

async def process_word_counts_async(code, queue=None, source="UI", target_article=None):
    try:
        smart_log(f"[{source}] Starting for {code}" + (f" (target: {target_article})" if target_article else ""))
        
        # Immediate ping to start the stream
        if queue: await queue.put({"type": "ping", "ts": time.time()})
        
        cached_fountain = _cached_fountain(code)
        if cached_fountain:
            totals, site_url = calculate_leaderboard(cached_fountain, get_all_cached_for_editathon(code))
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
            await refresh_editathon_data(code, queue, target_article=target_article, component=("sync" if source == "Monitor" else "live" if "Realtime" in source else None), check_revisions=(source == "Monitor"))
        finally:
            hb_task.cancel()
            
    except Exception as e:
        smart_log(f"[{source}] Error: {str(e)}", "ERROR")
        if queue: await queue.put({"type": "error", "message": str(e)})
    finally:
        if queue: 
            await queue.put("DONE")
            smart_log(f"[{source}] Sent DONE to queue")
