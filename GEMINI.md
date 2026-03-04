# ZTools - Wikipedia Editathon Management & Analytics

ZTools is a Flask-based web application designed to support Wikipedia editathons, specifically focused on the Bengali Wikipedia. It integrates with the [Fountain](https://fountain.toolforge.org/) tool to provide advanced analytics, word counting, and a streamlined interface for jury members to communicate with participants.

## Project Overview

- **Core Functionality:**
  - **Analytics:** Fetch and display article data from Fountain editathons.
  - **Word Counting:** Automatically count words in Wikipedia articles, with specialized support for Bengali script.
  - **Jury Statistics:** Generate detailed statistics and Wikitables for jury activity.
  - **Communication:** Allow jury members (via Wikimedia OAuth) to send feedback messages directly to participants' talk pages.
  - **Caching:** Uses SQLite to cache word counts and metadata to minimize API calls and improve performance.

- **Technology Stack:**
  - **Backend:** Python 3.10+, Flask 3.0.3
  - **Database/Caching:** SQLite (`ztools.db`)
  - **Authentication:** Authlib (OAuth 2.0 with Wikimedia)
  - **Web Scraping/Parsing:** BeautifulSoup4 (for word counting)
  - **Frontend:** Vanilla JavaScript, HTML5, CSS3
  - **API Integration:** Fountain API, Wikimedia Action API

## Directory Structure

- `app.py`: Main Flask application entry point and route definitions.
- `auth.py`: Authentication blueprint, Wikimedia OAuth logic, and talk page message posting.
- `fountain.py`: Core business logic, including Fountain/MediaWiki API clients and word counting.
- `ztools.db`: SQLite database for caching word counts and article metadata.
- `static/`: Frontend assets (CSS and modularized JavaScript).
- `templates/`: Jinja2 HTML templates.
- `requirements.txt`: Python dependencies.

## Building and Running

### Prerequisites
- Python 3.10 or higher.
- A registered OAuth 2.0 consumer on Wikimedia (Meta-Wiki).

### Setup
1. **Clone the repository.**
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure environment variables:**
   Create a `.env` file in the root directory with the following:
   ```env
   SECRET_KEY=your_flask_secret_key
   CONSUMER_KEY=your_wikimedia_oauth_client_id
   CONSUMER_SECRET=your_wikimedia_oauth_client_secret
   USER_AGENT=ZTools/1.0 (contact_email_or_username)
   ```
4. **Run the application:**
   ```bash
   python app.py
   ```
   The application will be available at `http://localhost:3000`.

## Development Conventions

- **Surgical Updates:** When modifying `fountain.py`, ensure that changes to the word counting logic are tested against both English and Bengali scripts.
- **Database Migrations:** The application automatically migrates from `wordcount.json` to SQLite on startup if the JSON file is present.
- **Frontend Modules:** JavaScript is organized into modules in `static/js/`. Prefer adding new functionality to specific modules rather than bloating `main.js`.
- **Error Handling:** The backend uses `stream_with_context` for long-running word count tasks; ensure frontend handlers (`wordCount.js`) can process NDJSON streams.
- **Security:** Never commit the `.env` file or `ztools.db`. Ensure `SESSION_COOKIE_SECURE` is set to `True` when deploying to production with HTTPS.

## Deployment Note
The project is configured to run in a Toolforge-like environment. The `LOG_FILE` path in `auth.py` and absolute path handling in `fountain.py` reflect this environment.
