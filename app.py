from werkzeug.middleware.proxy_fix import ProxyFix
import fountain
import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from auth import auth, oauth
from dotenv import load_dotenv
import os
from datetime import timedelta
load_dotenv()


app = Flask(__name__)
# Enable ProxyFix to correctly handle HTTPS behind Toolforge proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1,
                        x_host=1, x_port=1, x_prefix=1)

# Ensure a stable secret key for session persistence
app.secret_key = os.getenv("SECRET_KEY", "ztools_permanent_secret_123")
app.config.update(
    SESSION_COOKIE_NAME='ztools_session',
    PERMANENT_SESSION_LIFETIME=timedelta(days=1),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,  # Set to True in production with HTTPS
)

oauth.init_app(app)
app.register_blueprint(auth)


@app.context_processor
def inject_user():
    return dict(username=session.get('username'))


@app.route("/comment")
def comment():
    return render_template("comment.html")


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


@app.route("/user_reviews", methods=["GET", "POST"])
def user_reviews():
    if request.method == "GET":
        return redirect(url_for('comment'))

    if not session.get('username'):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"error": "No code provided"}), 400

    try:
        reviews, site_url = fountain.get_user_reviews(
            code, session.get('username'))
        return jsonify({"reviews": reviews, "site_url": site_url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/editathons", methods=["GET"])
def editathons():
    try:
        result = fountain.get_bn_editathons()
        return jsonify({"editathons": result})
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/jury_editathons", methods=["GET"])
def jury_editathons():
    username = session.get('username')
    if not username:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        result = fountain.get_user_jury_editathons(username)
        return jsonify({"editathons": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
