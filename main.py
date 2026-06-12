import os
import json
import asyncio
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Response, Depends
from fastapi.responses import StreamingResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from dotenv import load_dotenv
from services.monitor import start_background_services
from core.db import db
from core.config import tracked_hashes, BASE_DIR
from core.api import get_bn_editathons, fetch_fountain_data
from core.processor import (
    calculate_leaderboard, 
    get_all_cached_for_editathon, 
    get_jury_stats_core, 
    get_daily_stats_core,
    process_word_counts_async
)
from core.auth import get_password_hash, verify_password, create_access_token, get_current_user

# For Toolforge: explicitly look for .env in the home directory if not found locally
env_path = os.path.join(os.path.expanduser("~"), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

# Matplotlib configuration for headless environments
import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['svg.fonttype'] = 'none'
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

os.environ['MPLCONFIGDIR'] = os.path.join(BASE_DIR, ".matplotlib_cache")
if not os.path.exists(os.environ['MPLCONFIGDIR']):
    os.makedirs(os.environ['MPLCONFIGDIR'], exist_ok=True)

BN_PROP = None
BN_PROP_BOLD = None

def init_fonts():
    global BN_PROP, BN_PROP_BOLD
    try:
        from core.logger import smart_log
        import glob
        local_fonts_dir = os.path.join(BASE_DIR, "assets", "fonts")
        local_font_files = glob.glob(os.path.join(local_fonts_dir, "*.ttf"))
        font_path = None
        chosen_font = None
        if local_font_files:
            preferred_local = ['Kalpurush', 'Nikosh', 'NotoSansBengali', 'SiyamRupali', 'Lohit']
            for pref in preferred_local:
                match = next((f for f in local_font_files if pref.lower() in os.path.basename(f).lower() and 'bold' not in os.path.basename(f).lower()), None)
                if match:
                    font_path = match
                    chosen_font = os.path.basename(match)
                    break
            if not font_path:
                font_path = local_font_files[0]
                chosen_font = os.path.basename(font_path)
            smart_log(f"[Fonts] Found local font: {chosen_font} at {font_path}")
            bold_match = next((f for f in local_font_files if chosen_font.split('-')[0].lower() in os.path.basename(f).lower() and 'bold' in os.path.basename(f).lower()), None)
            bold_font_path = bold_match if bold_match else font_path
        if not font_path:
            font_candidates = ['Kalpurush', 'Nirmala UI', 'Nikosh', 'Siyam Rupali', 'Lohit Bengali', 'FreeSans', 'Arial Unicode MS', 'DejaVu Sans', 'Liberation Sans']
            available_fonts = {f.name: f.fname for f in fm.fontManager.ttflist}
            chosen_font = next((f for f in font_candidates if f in available_fonts), None)
            font_path = available_fonts.get(chosen_font) if chosen_font else None
            bold_font_path = font_path
        if font_path:
            try: fm.fontManager.addfont(font_path)
            except: pass
            if bold_font_path and bold_font_path != font_path:
                try: fm.fontManager.addfont(bold_font_path)
                except: pass
            BN_PROP = fm.FontProperties(fname=font_path)
            BN_PROP_BOLD = fm.FontProperties(fname=bold_font_path, weight='bold') if bold_font_path else fm.FontProperties(fname=font_path, weight='bold')
    except Exception as e:
        from core.logger import smart_log
        smart_log(f"[Fonts] Initialization error: {str(e)}", "ERROR")
        BN_PROP = fm.FontProperties()
        BN_PROP_BOLD = fm.FontProperties(weight='bold')

init_fonts()
db.init_db(tracked_hashes)

def ensure_admin():
    try:
        with db as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM admins")
            if cursor.fetchone()[0] == 0:
                default_user = os.getenv("ADMIN_USER", "R1F4T")
                default_pass = os.getenv("ADMIN_PASS", "0895")
                hashed = get_password_hash(default_pass)
                cursor.execute("INSERT INTO admins (username, password_hash) VALUES (?, ?)", (default_user, hashed))
                from core.logger import smart_log
                smart_log(f"[Auth] Created default admin user: {default_user}")
    except Exception as e:
        print(f"Error ensuring admin: {e}")

ensure_admin()

app = FastAPI()
start_background_services()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

# Admin APIs
@app.post("/api/admin/login")
async def admin_login(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    try:
        with db as conn:
            row = conn.execute("SELECT password_hash FROM admins WHERE username = ?", (form_data.username,)).fetchone()
            if not row or not verify_password(form_data.password, row[0]):
                raise HTTPException(status_code=401, detail="Invalid username or password")
            token = create_access_token({"sub": form_data.username})
            response.set_cookie(
                key="admin_token",
                value=token,
                httponly=True,
                max_age=60 * 60 * 24 * 7,
                samesite="lax",
                secure=False
            )
            return {"access_token": token, "token_type": "bearer"}
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/check-auth")
async def check_auth(user: str = Depends(get_current_user)):
    return {"status": "authenticated", "user": user}

@app.post("/api/admin/logout")
async def logout(response: Response):
    response.delete_cookie("admin_token")
    return {"status": "ok"}

@app.get("/api/admin/participants/{code}")
async def get_participants(code: str, user: str = Depends(get_current_user)):
    try:
        f_data = fetch_fountain_data(code)
        participants = list(set([art.get("user") for art in f_data.get("articles", []) if art.get("user")]))
        banned = []
        try:
            with db as conn:
                rows = conn.execute("SELECT username FROM banned_users WHERE editathon_code = ?", (code,)).fetchall()
                banned = [r[0] for r in rows]
        except: pass
        return {"participants": sorted([{"username": u, "isBanned": u in banned} for u in participants], key=lambda x: x["username"].lower())}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/ban")
async def ban_user(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    code, target_user = data.get("code"), data.get("username")
    if not code or not target_user: raise HTTPException(status_code=400, detail="Missing code or username")
    try:
        with db as conn:
            conn.execute("INSERT OR IGNORE INTO banned_users (editathon_code, username) VALUES (?, ?)", (code, target_user))
        return {"status": "success", "message": f"User {target_user} banned from {code}"}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/unban")
async def unban_user(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    code, target_user = data.get("code"), data.get("username")
    if not code or not target_user: raise HTTPException(status_code=400, detail="Missing code or username")
    try:
        with db as conn:
            conn.execute("DELETE FROM banned_users WHERE editathon_code = ? AND username = ?", (code, target_user))
        return {"status": "success", "message": f"User {target_user} unbanned from {code}"}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/editathons")
async def get_editathons():
    try:
        result = await asyncio.get_event_loop().run_in_executor(None, get_bn_editathons)
        return {"editathons": result}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fetch_articles")
async def fetch_articles(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code: raise HTTPException(status_code=400, detail="No code provided")
    try:
        def get_data_sync(c):
            f_data = fetch_fountain_data(c)
            cached = get_all_cached_for_editathon(c)
            return calculate_leaderboard(f_data, cached)
        user_articles, site_url = await asyncio.get_event_loop().run_in_executor(None, get_data_sync, code)
        return {"articles": user_articles, "site_url": site_url}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/jury_stats")
async def jury_stats(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code: raise HTTPException(status_code=400, detail="No code provided")
    try:
        def get_jury_sync(c):
            f_data = fetch_fountain_data(c)
            return get_jury_stats_core(f_data)
        sorted_juries, conflicts = await asyncio.get_event_loop().run_in_executor(None, get_jury_sync, code)
        return {"raw": {"stats": sorted_juries, "conflicts": conflicts}}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rejected_articles")
async def rejected_articles(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code: raise HTTPException(status_code=400, detail="No code provided")
    try:
        def get_rejected_sync(c):
            f_data = fetch_fountain_data(c)
            rej = []
            for art in f_data.get("articles", []):
                if any(r.get("marks", {}).get("0") in [1, 2] for r in art.get("marks", [])):
                    rej.append(art.get("name"))
            return rej
        rejected_articles = await asyncio.get_event_loop().run_in_executor(None, get_rejected_sync, code)
        return {"rejected_articles": rejected_articles}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/daily_stats")
async def daily_stats(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code: raise HTTPException(status_code=400, detail="No code provided")
    try:
        def get_daily_sync(c):
            f_data = fetch_fountain_data(c)
            cached = get_all_cached_for_editathon(c)
            return get_daily_stats_core(f_data, cached)
        result = await asyncio.get_event_loop().run_in_executor(None, get_daily_sync, code)
        return result
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/daily_graph/{code}")
async def daily_graph(code: str, metric: str = None, format: str = "png"):
    from core.logger import smart_log
    smart_log(f"[API] Graph request for {code} (metric: {metric})")
    def generate_graph_sync(code, metric):
        try:
            import io
            from core.utils import to_bn, format_bn_num, format_bn_commas
            data = fetch_fountain_data(code)
            cached = get_all_cached_for_editathon(code)
            stats = get_daily_stats_core(data, cached)
            if not stats: return None, "No data available for this editathon", None, None, None
            e_name = data.get("name", code)
            def bn_date(d_str):
                try:
                    d = datetime.strptime(d_str, "%Y-%m-%d")
                    months = ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর"]
                    return f"{to_bn(d.day)} {months[d.month-1]} {to_bn(d.year)}"
                except: return to_bn(d_str)
            dates = [s["date"] for s in stats]
            bn_dates = [bn_date(d) for d in dates]
            metrics_cfg = {
                "total_words": {"data": [s["total_words"] for s in stats], "label": "মোট শব্দসংখ্যা বৃদ্ধি", "title_suffix": "শব্দসংখ্যা লেখচিত্র", "color": "#2563eb", "type": "area"},
                "total_count": {"data": [s["total_count"] for s in stats], "label": "মোট নিবন্ধ সংখ্যা", "title_suffix": "নিবন্ধ সংখ্যা লেখচিত্র", "color": "#10b981", "type": "area"},
                "daily_count": {"data": [s["daily_count"] for s in stats], "label": "প্রতিদিনের নিবন্ধ জমা", "title_suffix": "প্রতিদিনের নিবন্ধ জমা লেখচিত্র", "color": "#f59e0b", "type": "bar"},
                "daily_words": {"data": [s["daily_words"] for s in stats], "label": "প্রতিদিনের শব্দসংখ্যা", "title_suffix": "প্রতিদিনের শব্দসংখ্যা লেখচিত্র", "color": "#8b5cf6", "type": "bar"}
            }
            bn_prop, bn_prop_bold = BN_PROP, BN_PROP_BOLD
            fig = Figure(figsize=(11, 6.5))
            ax = fig.add_subplot(111)
            if metric and metric in metrics_cfg:
                cfg = metrics_cfg[metric]
                vals = cfg["data"]
                if cfg["type"] == "area":
                    ax.fill_between(bn_dates, vals, color=cfg["color"], alpha=0.1); ax.plot(bn_dates, vals, color=cfg["color"], linewidth=3)
                    for i in range(len(bn_dates)): ax.plot(bn_dates[i], vals[i], color=cfg["color"], marker='o', markersize=7, gid=f"marker_{metric}_{i}")
                else:
                    bars = ax.bar(bn_dates, vals, color=cfg["color"], alpha=0.7)
                    for i, bar in enumerate(bars): bar.set_gid(f"marker_{metric}_{i}")
                ax.set_ylabel(cfg["label"], fontproperties=bn_prop_bold, fontsize=13, color=cfg["color"])
                ax.set_title(f'{e_name}: {cfg["title_suffix"]}', fontproperties=bn_prop_bold, fontsize=15, pad=15)
            else:
                counts, words = metrics_cfg["total_count"]["data"], metrics_cfg["total_words"]["data"]
                color_articles = '#10b981'
                ax.set_ylabel('মোট নিবন্ধ সংখ্যা', fontproperties=bn_prop_bold, color=color_articles, fontsize=13)
                ax.bar(bn_dates, counts, color=color_articles, alpha=0.2); ax.plot(bn_dates, counts, color=color_articles, marker='o', linewidth=2)
                for i in range(len(bn_dates)): ax.plot(bn_dates[i], counts[i], color=color_articles, marker='o', markersize=5, gid=f"marker_total_count_{i}")
                ax.tick_params(axis='y', labelcolor=color_articles)
                ax2 = ax.twinx(); color_words = '#2563eb'
                ax2.set_ylabel('মোট শব্দসংখ্যা বৃদ্ধি', fontproperties=bn_prop_bold, color=color_words, fontsize=13)
                ax2.plot(bn_dates, words, color=color_words, marker='s', linewidth=3)
                for i in range(len(bn_dates)): ax2.plot(bn_dates[i], words[i], color=color_words, marker='s', markersize=6, gid=f"marker_total_words_{i}")
                ax2.tick_params(axis='y', labelcolor=color_words); ax2.yaxis.set_major_formatter(FuncFormatter(lambda x, p: format_bn_num(x)))
                for label in ax2.get_yticklabels(): label.set_fontproperties(bn_prop)
                ax.set_title(f'{e_name}: অগ্রগতি লেখচিত্র', fontproperties=bn_prop_bold, fontsize=17, pad=20)
            ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: format_bn_num(x)))
            for label in ax.get_xticklabels(): label.set_fontproperties(bn_prop); label.set_horizontalalignment('right')
            for label in ax.get_yticklabels(): label.set_fontproperties(bn_prop)
            ax.set_xlabel('তারিখ', fontproperties=bn_prop, fontsize=12); ax.tick_params(axis='x', rotation=30); ax.grid(axis='y', linestyle='--', alpha=0.4); fig.tight_layout()
            svg_buf = io.BytesIO(); fig.savefig(svg_buf, format='svg', bbox_inches='tight')
            return svg_buf.getvalue(), None, stats, metrics_cfg, e_name
        except Exception as e: return None, str(e), None, None, None

    loop = asyncio.get_event_loop()
    svg_data, error, stats, metrics_cfg, e_name = await loop.run_in_executor(None, generate_graph_sync, code, metric)
    if error: raise HTTPException(status_code=500, detail=error)

    try:
        import xml.etree.ElementTree as ET
        from core.utils import to_bn, format_bn_num, format_bn_commas
        def bn_date_local(d_str):
            try:
                d = datetime.strptime(d_str, "%Y-%m-%d")
                months = ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর"]
                return f"{to_bn(d.day)} {months[d.month-1]} {to_bn(d.year)}"
            except: return to_bn(d_str)
        svg_ns = "http://www.w3.org/2000/svg"
        ET.register_namespace('', svg_ns); ET.register_namespace('xlink', "http://www.w3.org/1999/xlink")
        svg_tree = ET.fromstring(svg_data)
        style = ET.Element(f'{{{svg_ns}}}style')
        style.text = "text { font-family: 'Hind Siliguri', 'Noto Sans Bengali', sans-serif !important; } [id^='marker_'] { transition: all 0.2s; cursor: pointer; pointer-events: all; } [id^='marker_']:hover { filter: brightness(0.8); stroke: #000; stroke-width: 2px; } circle[id^='marker_']:hover { r: 9px; } rect[id^='marker_']:hover { opacity: 1; }"
        svg_tree.insert(0, style)
        script = ET.Element(f'{{{svg_ns}}}script'); script.set('type', 'text/javascript')
        script.text = "function showTooltip(evt, title, date, val, exactVal, color) { var tooltip = document.getElementById('svg-infobox'); if (!tooltip) return; var t_title = document.getElementById('infobox-title'); var t_date = document.getElementById('infobox-date'); var t_val = document.getElementById('infobox-val'); var t_exact = document.getElementById('infobox-exact'); t_title.textContent = title; t_title.setAttribute('fill', color); t_date.textContent = 'তারিখ: ' + date; t_val.textContent = 'মান: ' + val; t_exact.textContent = 'সঠিক মান: ' + exactVal; tooltip.setAttribute('visibility', 'visible'); var svg = evt.target.ownerSVGElement; var pt = svg.createSVGPoint(); pt.x = evt.clientX; pt.y = evt.clientY; var cursorpt = pt.matrixTransform(svg.getScreenCTM().inverse()); var x = cursorpt.x + 15; var y = cursorpt.y + 15; if (x > svg.viewBox.baseVal.width - 210) x = cursorpt.x - 215; if (y > svg.viewBox.baseVal.height - 110) y = cursorpt.y - 115; tooltip.setAttribute('transform', 'translate(' + x + ',' + y + ')'); } function hideTooltip() { var tooltip = document.getElementById('svg-infobox'); if (tooltip) tooltip.setAttribute('visibility', 'hidden'); }"
        svg_tree.append(script)
        for el in svg_tree.iter():
            gid = el.get('id')
            if gid and 'marker_' in gid:
                parts = gid.split('_'); m_key = next((k for k in metrics_cfg.keys() if f"_{k}_" in gid or gid.startswith(f"marker_{k}_")), None)
                idx_str = parts[-1]
                if idx_str.isdigit() and m_key in metrics_cfg:
                    idx = int(idx_str)
                    if idx < len(stats):
                        m_info, date_str, val_str, exact_val_str = metrics_cfg[m_key], bn_date_local(stats[idx]["date"]), format_bn_num(stats[idx][m_key]), format_bn_commas(stats[idx][m_key])
                        safe_label = m_info['label'].replace("'", "\\'")
                        el.set('onmousemove', f"showTooltip(evt, '{safe_label}', '{date_str}', '{val_str}', '{exact_val_str}', '{m_info['color']}')")
                        el.set('onmouseout', "hideTooltip()")
        infobox = ET.SubElement(svg_tree, f'{{{svg_ns}}}g', id='svg-infobox', visibility='hidden', style='pointer-events: none;')
        ET.SubElement(infobox, f'{{{svg_ns}}}rect', id='infobox-bg', width='210', height='105', fill='white', stroke='#2563eb', stroke_width='2', rx='8', ry='8', style='opacity: 0.95;')
        ET.SubElement(infobox, f'{{{svg_ns}}}text', id='infobox-title', x='12', y='22', style='font-weight: bold; font-size: 14px;')
        ET.SubElement(infobox, f'{{{svg_ns}}}text', id='infobox-date', x='12', y='44', fill='#475569', style='font-size: 12px;')
        ET.SubElement(infobox, f'{{{svg_ns}}}text', id='infobox-val', x='12', y='66', fill='#1e293b', style='font-weight: bold; font-size: 14px;')
        ET.SubElement(infobox, f'{{{svg_ns}}}text', id='infobox-exact', x='12', y='88', fill='#64748b', style='font-size: 12px;')
        return Response(content=ET.tostring(svg_tree, encoding='utf-8', method='xml'), media_type="image/svg+xml", headers={"Content-Disposition": f"attachment; filename=progress_{code}.svg"})
    except: return Response(content=svg_data, media_type="image/svg+xml", headers={"Content-Disposition": f"attachment; filename=progress_{code}.svg"})

@app.post("/api/count_words")
async def count_words(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code: raise HTTPException(status_code=400, detail="No code provided")
    q = asyncio.Queue()
    asyncio.create_task(process_word_counts_async(code, q, source="UI"))
    async def generate():
        try:
            while True:
                item = await q.get()
                if item == "DONE": break
                yield json.dumps(item) + "\n"
        except Exception as e: yield json.dumps({"error": str(e)}) + "\n"
    return StreamingResponse(generate(), media_type="application/x-ndjson")

app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.exception_handler(404)
async def not_found(request: Request, exc: HTTPException):
    if not request.url.path.startswith("/api"): return FileResponse("static/index.html")
    return JSONResponse(status_code=404, content={"detail": "Not Found"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
