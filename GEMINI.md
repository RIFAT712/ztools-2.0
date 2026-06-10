# ztools - Wikipedia Editathon Manager

`ztools` is a management and monitoring tool for Wikipedia editathons, specifically tailored for the Bengali Wikipedia (`bnwiki`). It provides advanced tracking, word counting, jury statistics, and automated notifications for editathon participants and organizers.

## Project Overview

- **Purpose:** Enhances the capabilities of the standard "Fountain" tool for Wikipedia editathons by providing accurate Bengali word counts, monitoring article changes in real-time, and generating detailed jury statistics.
- **Main Technologies:**
    - **Backend:** Python, FastAPI, SQLite, Aiohttp.
    - **Frontend:** React, TypeScript, Vite, Lucide React, Axios, React Router.
    - **Infrastructure:** Designed for deployment on Wikimedia Toolforge.

## Architecture

The project follows a modular, decoupled architecture:
- **FastAPI Backend:** Orchestrates the API and serves the frontend.
- **Core Modules (`/core`):** 
    - `db.py`: Thread-safe SQLite management using a context manager.
    - `api.py`: Wrappers for Fountain and Wikipedia API interactions.
    - `processor.py`: Core business logic for word counting and leaderboard generation.
    - `logger.py`: Granular multi-channel logging (`success`, `error`, `sync`, `live`).
- **Services (`/services`):** Concurrent background tasks for full-sync and real-time monitoring.
- **React Frontend:** A modern SPA built with TypeScript and Vite.

## Key Components

### Backend
- `fountain.py`: The main facade that provides a high-level API for the rest of the application.
- `main.py`: Entry point for the FastAPI server and route definitions.

### Intelligence & Resiliency
- **Stale-While-Revalidate:** The tool automatically falls back to cached data if the Wikipedia API is unavailable.
- **Intelligent Jury Flagging:** Automatically detects juror conflicts and stale reviews (>48h).
- **Worker Pool:** Uses a `ThreadPoolExecutor` to safely scale real-time updates without overloading resources.


### Frontend (`/frontend`)
- `src/App.tsx`: The main React component managing state and routing.
- `src/components/`: Modular UI components like `EditathonSelector`, `Header`, and `ProgressBar`.
- `src/utils.ts`: Utility functions for Bengali localization and data formatting.
- `static/`: The directory where built frontend assets are stored and served from by the backend.

## Development

### Backend Setup
1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
2.  Configure environment variables in a `.env` file (see `.env.example` if available, otherwise refer to `core/config.py` for required variables like `USER_AGENT`).
3.  Initialize the database:
    ```bash
    python reset_db.py
    ```
4.  Run the development server:
    ```bash
    python main.py
    ```

### Frontend Setup
1.  Navigate to the frontend directory:
    ```bash
    cd frontend
    ```
2.  Install dependencies:
    ```bash
    npm install
    ```
3.  Run the development server (Vite):
    ```bash
    npm run dev
    ```
4.  Build for production:
    ```bash
    npm run build
    ```
    *Note: The build process outputs to the root `static/` directory.*

## Conventions

- **Database:** SQLite is used with WAL mode for better concurrency. The schema includes indices for both competition-level (`editathon_code`) and article-level (`title_hash`) queries to ensure scalability.
- **Performance:** A hybrid caching strategy is used. Long-term data is in SQLite, while high-frequency lookups for the real-time monitor use an in-memory `set` to avoid disk I/O.
- **Async Logic:** The backend heavily utilizes `asyncio` and `aiohttp` for efficient, non-blocking API calls to Wikipedia.
- **Word Counting:** Specifically designed for Bengali script using regex (`[\u0980-\u09FF]+`). It excludes common boilerplate like navboxes, references, and metadata.
- **Toolforge Specifics:** 
    - Deployment uses a `Procfile`.
    - Logs are handled by a `LimitedFileHandler` to prevent excessive file growth on Toolforge disks.
    - Environment variables are optionally loaded from the user's home directory (`~/.env`).

## Deployment on Toolforge

The tool is configured for the Toolforge Build Service and Grid Engine/Kubernetes.
- The `Procfile` defines the web process: `web: uvicorn main:app --host 0.0.0.0 --port 8000`.
- Static files must be built (`npm run build` in `frontend/`) before deploying to ensure the backend can serve the latest UI.
