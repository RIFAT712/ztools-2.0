import asyncio
import threading
import json
from queue import Queue
from core.config import tracked_hashes, DB_FILE
from core.db import db
from core.api import get_bn_editathons, fetch_fountain_data
from core.processor import (
    process_word_counts_async, 
    get_all_cached_for_editathon, 
    calculate_leaderboard,
    save_article_to_cache,
    get_jury_stats_core,
    get_daily_stats_core
)
from core.utils import to_bn, get_wiki_url
# from services.monitor import start_background_services # Moved to main.py or explicit call

# Facade for Compatibility - Bridge for legacy sync components

def get_articles_data(code):
    data = fetch_fountain_data(code)
    cached = get_all_cached_for_editathon(code)
    return calculate_leaderboard(data, cached)

# get_word_counts removed as main.py now calls process_word_counts_async directly

def get_jury_stats_data(code):
    data = fetch_fountain_data(code)
    sorted_j, conflicts = get_jury_stats_core(data)
    
    # Generate Wikitable for legacy compatibility
    wt = '{| class="wikitable sortable"\n! # !! পর্যালোচক !! মোট !! গৃহীত !! বাতিল\n'
    t_t, t_a, t_r = 0, 0, 0
    for i, (j, s) in enumerate(sorted_j, 1):
        wt += f"|-\n| {i} || {j} || {s['total']} || {s['accepted']} || {s['rejected']}\n"
        t_t += s['total']; t_a += s['accepted']; t_r += s['rejected']
    wt += f"|-\n! মোট ||  || {t_t} || {t_a} || {t_r}\n|}}"
    
    return {"stats": sorted_j, "conflicts": conflicts}, wt

def get_rejected_articles_data(code):
    data = fetch_fountain_data(code)
    rej = []
    for art in data.get("articles", []):
        if any(r.get("marks", {}).get("0") in [1, 2] for r in art.get("marks", [])): rej.append(art.get("name"))
    wt = '{| class="wikitable sortable"\n! ক্রমিক !! নিবন্ধের নাম\n'
    for i, n in enumerate(rej, 1): wt += f"|-\n| {i} || {n}\n"
    return rej, wt + "|}"

def get_daily_stats_data(code):
    data = fetch_fountain_data(code)
    cached = get_all_cached_for_editathon(code)
    return get_daily_stats_core(data, cached)
