import requests
import time
from collections import defaultdict

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


def get_bn_editathons():
    """Fetches and filters Bengali editathons."""
    now = time.time()
    if cache["editathons"]["data"] and cache["editathons"]["expiry"] > now:
        return cache["editathons"]["data"]

    resp = session.get(
        "https://fountain.toolforge.org/api/editathons", timeout=10)
    resp.raise_for_status()
    data = resp.json()

    result = []
    for e in data:
        wiki_code = e.get("wiki", "wiki:en")
        lang = wiki_code.split(':', 1)[1] if ':' in wiki_code else wiki_code

        if lang != "bn":
            continue

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
