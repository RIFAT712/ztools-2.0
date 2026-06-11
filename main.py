import os
import json
import asyncio
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import StreamingResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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

# For Toolforge: explicitly look for .env in the home directory if not found locally
env_path = os.path.join(os.path.expanduser("~"), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

# Matplotlib configuration for headless environments
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

# Set a writable config directory for matplotlib on Toolforge
os.environ['MPLCONFIGDIR'] = os.path.join(BASE_DIR, ".matplotlib_cache")
if not os.path.exists(os.environ['MPLCONFIGDIR']):
    os.makedirs(os.environ['MPLCONFIGDIR'], exist_ok=True)

# Global font cache for performance
BN_PROP = None
BN_PROP_BOLD = None

def init_fonts():
    global BN_PROP, BN_PROP_BOLD
    try:
        font_candidates = ['Kalpurush', 'Nirmala UI', 'Nikosh', 'Siyam Rupali', 'Lohit Bengali', 'FreeSans', 'Arial Unicode MS']
        available_fonts = {f.name: f.fname for f in fm.fontManager.ttflist}
        chosen_font = next((f for f in font_candidates if f in available_fonts), 'sans-serif')
        font_path = available_fonts.get(chosen_font)
        
        if font_path:
            try: fm.fontManager.addfont(font_path)
            except: pass
            BN_PROP = fm.FontProperties(fname=font_path)
            BN_PROP_BOLD = fm.FontProperties(fname=font_path, weight='bold')
        else:
            BN_PROP = fm.FontProperties(family='sans-serif')
            BN_PROP_BOLD = fm.FontProperties(family='sans-serif', weight='bold')
    except Exception as e:
        BN_PROP = fm.FontProperties(family='sans-serif')
        BN_PROP_BOLD = fm.FontProperties(family='sans-serif', weight='bold')

# Initialize Fonts
init_fonts()

# Initialize DB and cache
db.init_db(tracked_hashes)

app = FastAPI()

# Start background services
start_background_services()

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # More permissive for Toolforge proxy environment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

@app.get("/api/editathons")
async def get_editathons():
    try:
        from core.api import get_bn_editathons
        result = await asyncio.get_event_loop().run_in_executor(None, get_bn_editathons)
        return {"editathons": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fetch_articles")
async def fetch_articles(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
    try:
        def get_data_sync(c):
            f_data = fetch_fountain_data(c)
            cached = get_all_cached_for_editathon(c)
            return calculate_leaderboard(f_data, cached)
            
        user_articles, site_url = await asyncio.get_event_loop().run_in_executor(None, get_data_sync, code)
        return {"articles": user_articles, "site_url": site_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/jury_stats")
async def jury_stats(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
    try:
        def get_jury_sync(c):
            f_data = fetch_fountain_data(c)
            return get_jury_stats_core(f_data)
            
        sorted_juries, conflicts = await asyncio.get_event_loop().run_in_executor(None, get_jury_sync, code)
        return {"raw": {"stats": sorted_juries, "conflicts": conflicts}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rejected_articles")
async def rejected_articles(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/daily_stats")
async def daily_stats(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
    try:
        def get_daily_sync(c):
            f_data = fetch_fountain_data(c)
            cached = get_all_cached_for_editathon(c)
            return get_daily_stats_core(f_data, cached)
            
        result = await asyncio.get_event_loop().run_in_executor(None, get_daily_sync, code)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/daily_graph/{code}")
async def daily_graph(code: str, metric: str = None, format: str = "png"):
    from core.logger import smart_log
    
    def generate_graph_sync(code, metric):
        try:
            import io
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
            from core.processor import get_daily_stats_core, get_all_cached_for_editathon
            from core.api import fetch_fountain_data
            from core.utils import to_bn, format_bn_num, format_bn_commas

            # Get data
            data = fetch_fountain_data(code)
            cached = get_all_cached_for_editathon(code)
            stats = get_daily_stats_core(data, cached)
            
            if not stats:
                return None, "No data available for this editathon"
                
            e_name = data.get("name", code)
                
            def bn_date(d_str):
                try:
                    d = datetime.strptime(d_str, "%Y-%m-%d")
                    months = ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর"]
                    return f"{to_bn(d.day)} {months[d.month-1]}"
                except: return to_bn(d_str)

            dates = [s["date"] for s in stats]
            bn_dates = [bn_date(d) for d in dates]
            
            metrics_cfg = {
                "total_words": {"data": [s["total_words"] for s in stats], "label": "মোট শব্দসংখ্যা বৃদ্ধি", "title_suffix": "শব্দসংখ্যা লেখচিত্র", "color": "#2563eb", "type": "area"},
                "total_count": {"data": [s["total_count"] for s in stats], "label": "মোট নিবন্ধ সংখ্যা", "title_suffix": "নিবন্ধ সংখ্যা লেখচিত্র", "color": "#10b981", "type": "area"},
                "daily_count": {"data": [s["daily_count"] for s in stats], "label": "প্রতিদিনের নিবন্ধ জমা", "title_suffix": "প্রতিদিনের নিবন্ধ জমা লেখচিত্র", "color": "#f59e0b", "type": "bar"},
                "daily_words": {"data": [s["daily_words"] for s in stats], "label": "প্রতিদিনের শব্দসংখ্যা", "title_suffix": "প্রতিদিনের শব্দসংখ্যা লেখচিত্র", "color": "#8b5cf6", "type": "bar"}
            }

            # Font discovery
            font_candidates = ['Kalpurush', 'Nirmala UI', 'Nikosh', 'Siyam Rupali', 'Lohit Bengali', 'FreeSans', 'Arial Unicode MS']
            available_fonts = {f.name: f.fname for f in fm.fontManager.ttflist}
            chosen_font = next((f for f in font_candidates if f in available_fonts), 'sans-serif')
            font_path = available_fonts.get(chosen_font)
            
            if font_path:
                try: fm.fontManager.addfont(font_path)
                except: pass
            
            bn_prop = fm.FontProperties(fname=font_path) if font_path else fm.FontProperties(family='sans-serif')
            bn_prop_bold = fm.FontProperties(fname=font_path, weight='bold') if font_path else fm.FontProperties(family='sans-serif', weight='bold')

            # Create Figure (Object-Oriented API for thread safety)
            fig = Figure(figsize=(11, 6.5))
            ax = fig.add_subplot(111)
            
            if metric and metric in metrics_cfg:
                cfg = metrics_cfg[metric]
                vals = cfg["data"]
                if cfg["type"] == "area":
                    ax.fill_between(bn_dates, vals, color=cfg["color"], alpha=0.1)
                    ax.plot(bn_dates, vals, color=cfg["color"], linewidth=3)
                    for i in range(len(bn_dates)):
                        ax.plot(bn_dates[i], vals[i], color=cfg["color"], marker='o', markersize=7, gid=f"marker_{metric}_{i}")
                else:
                    bars = ax.bar(bn_dates, vals, color=cfg["color"], alpha=0.7)
                    for i, bar in enumerate(bars): bar.set_gid(f"marker_{metric}_{i}")
                
                ax.set_ylabel(cfg["label"], fontproperties=bn_prop_bold, fontsize=13, color=cfg["color"])
                ax.set_title(f'{e_name}: {cfg["title_suffix"]}', fontproperties=bn_prop_bold, fontsize=15, pad=15)
            else:
                # Default dual-axis
                counts = metrics_cfg["total_count"]["data"]
                words = metrics_cfg["total_words"]["data"]
                color_articles = '#10b981'
                ax.set_ylabel('মোট নিবন্ধ সংখ্যা', fontproperties=bn_prop_bold, color=color_articles, fontsize=13)
                ax.bar(bn_dates, counts, color=color_articles, alpha=0.2)
                ax.plot(bn_dates, counts, color=color_articles, marker='o', linewidth=2)
                for i in range(len(bn_dates)):
                    ax.plot(bn_dates[i], counts[i], color=color_articles, marker='o', markersize=5, gid=f"marker_total_count_{i}")
                ax.tick_params(axis='y', labelcolor=color_articles)
                
                ax2 = ax.twinx()
                color_words = '#2563eb'
                ax2.set_ylabel('মোট শব্দসংখ্যা বৃদ্ধি', fontproperties=bn_prop_bold, color=color_words, fontsize=13)
                ax2.plot(bn_dates, words, color=color_words, marker='s', linewidth=3)
                for i in range(len(bn_dates)):
                    ax2.plot(bn_dates[i], words[i], color=color_words, marker='s', markersize=6, gid=f"marker_total_words_{i}")
                ax2.tick_params(axis='y', labelcolor=color_words)
                ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format_bn_num(x)))
                for label in ax2.get_yticklabels(): label.set_fontproperties(bn_prop)
                ax.set_title(f'{e_name}: অগ্রগতি লেখচিত্র', fontproperties=bn_prop_bold, fontsize=17, pad=20)

            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format_bn_num(x)))
            for label in ax.get_xticklabels(): label.set_fontproperties(bn_prop)
            for label in ax.get_yticklabels(): label.set_fontproperties(bn_prop)
            ax.set_xlabel('তারিখ', fontproperties=bn_prop, fontsize=12)
            ax.tick_params(axis='x', rotation=45)
            ax.grid(axis='y', linestyle='--', alpha=0.4)
            fig.tight_layout()
            
            svg_buf = io.BytesIO()
            fig.savefig(svg_buf, format='svg', bbox_inches='tight')
            return svg_buf.getvalue(), None, stats, metrics_cfg, e_name
        except Exception as e:
            import traceback
            smart_log(f"Graph Generation Error: {str(e)}\n{traceback.format_exc()}", "ERROR")
            return None, str(e), None, None, None

    # Run in executor
    loop = asyncio.get_event_loop()
    svg_data, error, stats, metrics_cfg, e_name = await loop.run_in_executor(None, generate_graph_sync, code, metric)
    
    if error:
        if "No data" in error: raise HTTPException(status_code=404, detail=error)
        raise HTTPException(status_code=500, detail=f"Graph generation failed: {error}")

    # POST-PROCESS SVG FOR INTERACTIVITY
    try:
        import xml.etree.ElementTree as ET
        from core.utils import to_bn, format_bn_num, format_bn_commas
        
        def bn_date_local(d_str):
            try:
                d = datetime.strptime(d_str, "%Y-%m-%d")
                months = ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর"]
                return f"{to_bn(d.day)} {months[d.month-1]}"
            except: return to_bn(d_str)

        svg_ns = "http://www.w3.org/2000/svg"
        ET.register_namespace('', svg_ns)
        ET.register_namespace('xlink', "http://www.w3.org/1999/xlink")
        
        svg_tree = ET.fromstring(svg_data)
        
        # 1. Add CSS for hover effects
        style = ET.Element(f'{{{svg_ns}}}style')
        style.text = """
            [id^='marker_'] { transition: all 0.2s; cursor: pointer; pointer-events: all; }
            [id^='marker_']:hover { filter: brightness(0.8); stroke: #000; stroke-width: 2px; }
            circle[id^='marker_']:hover { r: 9px; }
            rect[id^='marker_']:hover { opacity: 1; }
        """
        svg_tree.insert(0, style)
        
        # 2. Add Script for Infobox
        script = ET.Element(f'{{{svg_ns}}}script')
        script.set('type', 'text/javascript')
        script.text = """
            function showTooltip(evt, title, date, val, exactVal, color) {
                var tooltip = document.getElementById('svg-infobox');
                var t_title = document.getElementById('infobox-title');
                var t_date = document.getElementById('infobox-date');
                var t_val = document.getElementById('infobox-val');
                var t_exact = document.getElementById('infobox-exact');
                
                t_title.textContent = title;
                t_title.setAttribute('fill', color);
                t_date.textContent = 'তারিখ: ' + date;
                t_val.textContent = 'মান: ' + val;
                t_exact.textContent = 'সঠিক মান: ' + exactVal;
                
                tooltip.setAttribute('visibility', 'visible');
                var svg = evt.target.ownerSVGElement;
                var pt = svg.createSVGPoint();
                pt.x = evt.clientX; pt.y = evt.clientY;
                var cursorpt = pt.matrixTransform(svg.getScreenCTM().inverse());
                
                var x = cursorpt.x + 15; var y = cursorpt.y + 15;
                if (x > svg.viewBox.baseVal.width - 210) x = cursorpt.x - 215;
                if (y > svg.viewBox.baseVal.height - 110) y = cursorpt.y - 115;
                tooltip.setAttribute('transform', 'translate(' + x + ',' + y + ')');
            }
            function hideTooltip() { document.getElementById('svg-infobox').setAttribute('visibility', 'hidden'); }
        """
        svg_tree.append(script)
        
        # 3. Add Tooltip Attributes
        for el in svg_tree.iter():
            gid = el.get('id')
            if gid and gid.startswith('marker_'):
                parts = gid.split('_')
                if len(parts) >= 3:
                    m_key = "_".join(parts[1:-1])
                    idx = int(parts[-1])
                    if m_key in metrics_cfg and idx < len(stats):
                        m_info = metrics_cfg[m_key]
                        date_str = bn_date_local(stats[idx]["date"])
                        val_str = format_bn_num(stats[idx][m_key])
                        exact_val_str = format_bn_commas(stats[idx][m_key])
                        safe_title = m_info['label'].replace("'", "\\'")
                        el.set('onmousemove', f"showTooltip(evt, '{safe_title}', '{date_str}', '{val_str}', '{exact_val_str}', '{m_info['color']}')")
                        el.set('onmouseout', "hideTooltip()")
        
        # 4. Create Infobox
        infobox = ET.SubElement(svg_tree, f'{{{svg_ns}}}g', id='svg-infobox', visibility='hidden', style='pointer-events: none;')
        ET.SubElement(infobox, f'{{{svg_ns}}}rect', id='infobox-bg', width='210', height='105', fill='white', stroke='#2563eb', stroke_width='2', rx='8', ry='8', style='opacity: 0.95;')
        ET.SubElement(infobox, f'{{{svg_ns}}}text', id='infobox-title', x='12', y='22', style='font-family: sans-serif; font-weight: bold; font-size: 14px;')
        ET.SubElement(infobox, f'{{{svg_ns}}}text', id='infobox-date', x='12', y='44', fill='#475569', style='font-family: sans-serif; font-size: 12px;')
        ET.SubElement(infobox, f'{{{svg_ns}}}text', id='infobox-val', x='12', y='66', fill='#1e293b', style='font-family: sans-serif; font-weight: bold; font-size: 14px;')
        ET.SubElement(infobox, f'{{{svg_ns}}}text', id='infobox-exact', x='12', y='88', fill='#64748b', style='font-family: sans-serif; font-size: 12px;')
        
        final_svg = ET.tostring(svg_tree, encoding='utf-8', method='xml')
        return Response(content=final_svg, media_type="image/svg+xml", headers={"Content-Disposition": f"attachment; filename=progress_{code}.svg"})
    except Exception as e:
        smart_log(f"SVG Post-processing Error: {e}", "ERROR")
        return Response(content=svg_data, media_type="image/svg+xml", headers={"Content-Disposition": f"attachment; filename=progress_{code}.svg"})

@app.post("/api/count_words")
async def count_words(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")

    q = asyncio.Queue()
    # Start processing in the background within the same event loop
    from core.processor import process_word_counts_async
    asyncio.create_task(process_word_counts_async(code, q, source="UI"))

    async def generate():
        try:
            while True:
                item = await q.get()
                if item == "DONE":
                    break
                yield json.dumps(item) + "\n"
        except Exception as e:
            yield json.dumps({"error": str(e)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")

# Serve static files for the React frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.exception_handler(404)
async def not_found(request: Request, exc: HTTPException):
    # SPA fallback: return index.html for all non-API 404s
    if not request.url.path.startswith("/api"):
        return FileResponse("static/index.html")
    return JSONResponse(status_code=404, content={"detail": "Not Found"})

if __name__ == "__main__":
    import uvicorn
    # Toolforge Build Service expects port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
