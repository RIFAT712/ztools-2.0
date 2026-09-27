import unicodedata
import hashlib

WIKI_PREFIXES = {
    "wiki": "wikipedia", "wikipedia": "wikipedia",
    "wikt": "wiktionary", "wiktionary": "wiktionary",
    "b": "wikibooks", "wikibooks": "wikibooks",
    "voy": "wikivoyage", "wikivoyage": "wikivoyage",
    "q": "wikiquote", "wikiquote": "wikiquote",
    "s": "wikisource", "wikisource": "wikisource",
    "n": "wikinews", "wikinews": "wikinews"
}

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
