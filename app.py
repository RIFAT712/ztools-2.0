from flask import Flask, render_template, request, jsonify
import requests
import fountain

app = Flask(__name__)


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
        user_articles, site_url = fountain.get_articles_data(code)
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
        sorted_juries = fountain.get_jury_stats_data(code)
        return jsonify({"raw": sorted_juries})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/editathons", methods=["GET"])
def editathons():
    try:
        result = fountain.get_bn_editathons()
        print(result)
        return jsonify({"editathons": result})
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
