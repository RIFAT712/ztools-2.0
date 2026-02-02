from datetime import datetime, timedelta
import requests
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

# Constants and Configuration
WIKI_PREFIXES = {
    "wiki": "wikipedia",
    "wikt": "wiktionary",
    "b": "wikibooks",
    "voy": "wikivoyage",
    "q": "wikiquote",
    "s": "wikisource",
    "n": "wikinews"
}

# Simple In-Memory Cache
cache = {
    "editathons": {"data": None, "expiry": 0},
    "details": {}  # code: {"data": None, "expiry": 0}
}

# Persistent Session for requests
session = requests.Session()


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


def get_jury_stats_data(code):
    """Processes jury statistics for a given editathon code."""
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
    return sorted_juries


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
