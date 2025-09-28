from flask import Flask, render_template, request, jsonify
import requests
from collections import defaultdict

app = Flask(__name__)

WIKI_PREFIXES = {
    "wiki": "wikipedia",
    "wikt": "wiktionary",
    "b": "wikibooks",
    "voy": "wikivoyage",
    "q": "wikiquote",
    "s": "wikisource",
    "n": "wikinews"
}

def get_wiki_url(fountain_wiki_code):
    if ':' in fountain_wiki_code:
        prefix, lang = fountain_wiki_code.split(':', 1)
    else:
        prefix, lang = "wikipedia", fountain_wiki_code
    site_suffix = WIKI_PREFIXES.get(prefix, "wikipedia")
    return f"{lang}.{site_suffix}.org"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/fetch_articles", methods=["POST"])
def fetch_articles():
    data = request.json
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"error": "No code provided"}), 400

    try:
        resp = requests.get(f"https://fountain.toolforge.org/api/editathons/{code}")
        resp.raise_for_status()
        fountain_data = resp.json()

        wiki_code = fountain_data.get("wiki", "wiki:bn")
        site_url = get_wiki_url(wiki_code)

        user_articles = defaultdict(list)
        for article in fountain_data.get("articles", []):
            user = article.get("user")
            name = article.get("name")
            status = "অপর্যালোচিত"  # Default status

            # Correct acceptance/rejection logic
            marks = article.get("marks", [])
            if marks:
                rejected = any(review.get("marks", {}).get("0") in [1, 2] for review in marks)
                if rejected:
                    status = "গৃহীত হয়নি"
                else:
                    status = "গৃহীত হয়েছে"

            if user and name:
                user_articles[user].append({
                    "name": name,
                    "status": status,
                    "reviews": len(marks)
                })

        return jsonify({"articles": user_articles, "site_url": site_url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/jury_stats", methods=["POST"])
def jury_stats():
    data = request.json
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"error": "No code provided"}), 400

    try:
        resp = requests.get(f"https://fountain.toolforge.org/api/editathons/{code}")
        resp.raise_for_status()
        fountain_data = resp.json()

        jury_stats = {}
        for article in fountain_data.get("articles", []):
            for review in article.get("marks", []):
                jury = review.get("user")
                if not jury:
                    continue
                if jury not in jury_stats:
                    jury_stats[jury] = {"total": 0, "accepted": 0, "rejected": 0}
                jury_stats[jury]["total"] += 1
                decision = review.get("marks", {}).get("0")
                if decision == 0:
                    jury_stats[jury]["accepted"] += 1
                elif decision in [1, 2]:
                    jury_stats[jury]["rejected"] += 1

        sorted_juries = sorted(jury_stats.items(), key=lambda x: x[1]["total"], reverse=True)
        return jsonify({"raw": sorted_juries})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0")
    # app.run(debug=True)