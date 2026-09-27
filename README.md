# ZTools 2.0 - Wikipedia Editathon Management System

ZTools 2.0 is a robust, high-performance management system designed specifically for Wikipedia editathons. It provides organizers with real-time tracking, participant management, and comprehensive data visualization tools.

## 🚀 Key Features

### 🛡️ Advanced Security
- **Robust Authentication**: JWT-based admin authentication with mandatory database verification for every request.
- **CSRF Protection**: High-security cookie policies (`SameSite=Strict`, `HttpOnly`, `Secure`) to prevent Cross-Site Request Forgery.
- **Access Control**: Public API endpoints only process Bengali Fountain editathons that the tool is tracking.

### 📊 Admin Dashboard
- **Participant Management**: 
  - Modern, responsive interface for monitoring contributors.
  - Real-time Ban/Unban functionality with optimistic UI updates.
  - Advanced search with quick clearing and visual status indicators (Active/Banned).
  - User avatars and detailed contributing status.
- **Navigation**: Integrated "Home" shortcut and secure logout.

### 💾 Smart Data Management
- **Automatic Tracking**: Every Bengali Fountain editathon that finished within the last 365 days is tracked with no manual setup; the list refreshes every sync cycle (15 min). Active contests, plus those finished within the last 30 days (jury still reviewing), sync every cycle; older ones sync once a day. When a contest ages out, its caches are dropped but bans are kept.
- **Real-time Monitoring**: Background services track Wikipedia edits in real-time, matching them against active editathons using a high-performance hash-based lookup.
- **Change Detection**: Each sync cycle checks the current revision ID of every counted article (50 per request, no content) and recounts only the ones that changed. Edits missed while the live stream is reconnecting still get counted.
- **Deadline Counts**: Once a contest's finish date passes, every article is counted once from the revision live at the deadline, then frozen. Edits made after the deadline don't change results.
- **Fountain Integration**: Seamlessly pulls data from the Wikimedia Fountain tool for official participant lists and jury marks.

### ⚡ Performance Optimizations
- **Data Preloading**: Editathon lists are pre-fetched during the login process to ensure the dashboard is ready the moment you log in.
- **Parallel Processing**: Backend uses asynchronous programming (FastAPI + AsyncIO) to handle multiple requests and background tasks concurrently.
- **Optimized UI**: Dashboard uses parallel API calls and optimistic updates to provide a snappy, zero-lag experience.

## 🛠️ Tech Stack

- **Backend**: Python 3.x, FastAPI, SQLite, Uvicorn.
- **Frontend**: React, TypeScript, Vite, Tailwind CSS (or custom CSS variables), Lucide Icons.
- **Monitoring**: SSE (Server-Sent Events) for real-time Wikipedia edit tracking.
- **Visualization**: Matplotlib (for daily progress graphs).

## 📝 Word Counting Procedure

The system includes a specialized procedure for calculating word counts from WikiBooks and Wikipedia content, specifically designed to handle Wikitext and Bengali characters accurately.

### 1. Data Extraction
The procedure retrieves page content with the MediaWiki Action API (`prop=revisions`, `rvprop=content`, `rvslots=main`, `formatversion=2`), fetching up to **50 articles per request** (POST). Normalized titles and redirects are mapped back to the original article names. If a reply is cut short by the API's result-size limit, the missing pages are retried in smaller batches; if a request fails outright, the last cached count is kept (marked `STALE`). Content is read from `query.pages[].revisions[0].slots.main.content`.

### 2. Wikitext Cleaning
To ensure an accurate word count that reflects only readable text, a multi-stage cleaning process is applied using regular expressions:
- **Comments**: Removes `<!-- ... -->` blocks.
- **Math Expressions**: Completely removes `<math> ... </math>` tags and their LaTeX content, as math symbols do not count as words.
- **HTML Tags**: Removes all other HTML-like tags (e.g., `<div>`, `<span>`, `<li>`).
- **Templates**: Removes Wikitext template markers (e.g., `{{TextBox|1=...}}`) while preserving the content inside when applicable.
- **Links**: Simplifies internal links `[[Target|Text]]` or `[[Target]]` to just the displayed text.
- **Formatting**: Removes bold (`'''`) and italic (`''`) markers.
- **Structural Markers**: Removes Wikitext structural symbols like headings (`==`), list bullets (`*`, `#`), and indentation (`:`, `;`).

### 3. Word Counting Logic
- **Punctuation**: Replaces common punctuation marks (including Bengali 'DARI' `।`) with spaces to prevent words from being joined incorrectly.
- **Tokenization**: Splits the cleaned text by whitespace characters.
- **Count**: The final word count is the total number of tokens generated after this cleaning process.

This approach provides a "Cleaned Word Count" that aligns more closely with human reading expectations than a raw character or byte count.

## ⚙️ Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/RIFAT712/ztools-2.0.git
   cd ztools-2.0
   ```

2. **Backend Setup**:
   ```bash
   pip install -r requirements.txt
   cp .env.example .env  # Configure your JWT_SECRET and ADMIN credentials
   python main.py
   ```

3. **Frontend Setup**:
   ```bash
   cd frontend
   npm install
   npm run build  # Builds the frontend into the root /static folder
   ```

## 🌐 Deployment (Toolforge)

ZTools 2.0 is optimized for **Wikimedia Toolforge**.
- **Environment**: Set these in `~/.env` (the tool's home) or with `toolforge envvars create NAME value`:
  - `ADMIN_USER` / `ADMIN_PASS`: create the first admin account on an empty database. There is no built-in default.
  - `JWT_SECRET`: a long random string. Without it, a random key is generated at startup and admin logins reset on every restart.
  - `USER_AGENT` (optional): identifies the tool to Wikimedia APIs.
- **Static Files**: The FastAPI server serves the pre-built React frontend from the `static/` directory.
- **Database**: SQLite `ztools.db` is stored in `$TOOL_DATA_DIR` (the tool's persistent NFS home) when set, otherwise in the project root. The container filesystem is wiped on restart, so the DB must not live there.

---
*Developed for the Wikimedia Community to streamline editathon management and data transparency.*
