import re
import unicodedata
import hashlib
from datetime import datetime

WIKI_PREFIXES = {
    "wiki": "wikipedia", "wikipedia": "wikipedia",
    "wikt": "wiktionary", "wiktionary": "wiktionary",
    "b": "wikibooks", "wikibooks": "wikibooks",
    "voy": "wikivoyage", "wikivoyage": "wikivoyage",
    "q": "wikiquote", "wikiquote": "wikiquote",
    "s": "wikisource", "wikisource": "wikisource",
    "n": "wikinews", "wikinews": "wikinews"
}

def to_bn(n):
    return "".join("০১২৩৪৫৬৭৮৯"[int(d)] if d.isdigit() else d for d in str(n))

def format_bn_commas(n):
    try:
        s = str(int(float(n)))
        if len(s) <= 3:
            return to_bn(s)
        
        # South Asian formatting: last 3 digits, then groups of 2
        last_three = s[-3:]
        other_parts = s[:-3]
        
        # Reverse other_parts to group by 2 from the right
        rev_others = other_parts[::-1]
        groups = [rev_others[i:i+2] for i in range(0, len(rev_others), 2)]
        
        # Join groups with commas, reverse back, and add the last three
        formatted = ",".join(groups)[::-1] + "," + last_three
        return to_bn(formatted)
    except:
        return to_bn(n)

def format_bn_num(n):
    try:
        n = float(n)
        if n >= 10000000:
            val = round(n / 10000000, 1)
            return to_bn(int(val) if val == int(val) else val) + " কোটি"
        if n >= 100000:
            val = round(n / 100000, 1)
            return to_bn(int(val) if val == int(val) else val) + " লক্ষ"
        if n >= 1000:
            val = round(n / 1000, 1)
            return to_bn(int(val) if val == int(val) else val) + " হাজার"
        return to_bn(int(n) if n == int(n) else n)
    except:
        return to_bn(n)

def normalize_title(title):
    if not title: return ""
    return unicodedata.normalize('NFC', str(title)).replace('_', ' ').strip()

def get_title_hash(title):
    if not title: return ""
    return hashlib.sha256(normalize_title(title).encode('utf-8')).hexdigest()

def get_wiki_url(code):
    prefix, lang = code.split(':', 1) if ':' in code else ("wikipedia", code)
    return f"{lang}.{WIKI_PREFIXES.get(prefix.lower(), 'wikipedia')}.org"

def get_wiki_dbname(fountain_wiki_code):
    prefix, lang = fountain_wiki_code.split(':', 1) if ':' in fountain_wiki_code else ("wikipedia", fountain_wiki_code)
    project = WIKI_PREFIXES.get(prefix.lower(), "wikipedia")
    if project == "wikipedia": return f"{lang}wiki"
    return f"{lang}{project}"

def get_article_status(marks):
    if not marks: return "অপর্যালোচিত"
    decisions = [m.get("marks", {}).get("0") for m in marks if "0" in m.get("marks", {})]
    if any(d in [1, 2] for d in decisions): return "গৃহীত হয়নি"
    return "গৃহীত হয়েছে"
