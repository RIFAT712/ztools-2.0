# ZTools 2.0 - Wikipedia Editathon Management System

ZTools 2.0 is a robust, high-performance management system designed specifically for Wikipedia editathons. It provides organizers with real-time tracking, participant management, and comprehensive data visualization tools.

## 🚀 Key Features

### 🛡️ Advanced Security
- **Robust Authentication**: JWT-based admin authentication with mandatory database verification for every request.
- **CSRF Protection**: High-security cookie policies (`SameSite=Strict`, `HttpOnly`, `Secure`) to prevent Cross-Site Request Forgery.
- **Access Control**: Public API endpoints are strictly restricted to only process data for editathons explicitly enabled by an administrator.

### 📊 Admin Dashboard
- **Editathon Management**: One-click toggle to enable or disable tracking for specific Wikimedia Fountain editathons.
- **Participant Management**: 
  - Modern, responsive interface for monitoring contributors.
  - Real-time Ban/Unban functionality with optimistic UI updates.
  - Advanced search with quick clearing and visual status indicators (Active/Banned).
  - User avatars and detailed contributing status.
- **Navigation**: Integrated "Home" shortcut and secure logout.

### 💾 Smart Data Management
- **Selective Storage**: To keep the system lean and efficient, disabling an editathon automatically purges all associated word counts, metadata caches, and banned user records.
- **Real-time Monitoring**: Background services track Wikipedia edits in real-time, matching them against active editathons using a high-performance hash-based lookup.
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
- **Environment**: Set up your `.env` in the home directory or project root.
- **Static Files**: The FastAPI server serves the pre-built React frontend from the `static/` directory.
- **Database**: Uses a persistent SQLite database (`ztools.db`).

---
*Developed for the Wikimedia Community to streamline editathon management and data transparency.*
