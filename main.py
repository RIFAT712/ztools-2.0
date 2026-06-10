import os
import json
import asyncio
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import StreamingResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import fountain
from services.monitor import start_background_services
from core.db import db
from core.config import tracked_hashes

# For Toolforge: explicitly look for .env in the home directory if not found locally
env_path = os.path.join(os.path.expanduser("~"), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

# Initialize DB and cache
db.init_db(tracked_hashes)

app = FastAPI()

# Start background services
start_background_services()

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://ztools.toolforge.org"
    ], # Vite default + Production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/editathons")
async def get_editathons():
    try:
        # Run blocking sync function in executor
        result = await asyncio.get_event_loop().run_in_executor(None, fountain.get_bn_editathons)
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
        user_articles, site_url = await asyncio.get_event_loop().run_in_executor(None, fountain.get_articles_data, code)
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
        sorted_juries, wikitable = await asyncio.get_event_loop().run_in_executor(None, fountain.get_jury_stats_data, code)
        return {"raw": sorted_juries, "wikitable": wikitable}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rejected_articles")
async def rejected_articles(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
    try:
        rejected_articles, wikitable = await asyncio.get_event_loop().run_in_executor(None, fountain.get_rejected_articles_data, code)
        return {"rejected_articles": rejected_articles, "wikitable": wikitable}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/daily_stats")
async def daily_stats(request: Request):
    data = await request.json()
    code = data.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
    try:
        result = await asyncio.get_event_loop().run_in_executor(None, fountain.get_daily_stats_data, code)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/daily_graph/{code}")
async def daily_graph(code: str, metric: str = None, format: str = "png"):
    try:
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
        import io
        from core.processor import get_daily_stats_core, get_all_cached_for_editathon
        from core.api import fetch_fountain_data
        from core.utils import to_bn
        
        # Get data
        data = fetch_fountain_data(code)
        cached = get_all_cached_for_editathon(code)
        stats = get_daily_stats_core(data, cached)
        
        if not stats:
            raise HTTPException(status_code=404, detail="No data available for this editathon")
            
        # Get descriptive title
        e_name = data.get("name", code)
            
        # Localization helper for dates
        from core.utils import to_bn, format_bn_num, format_bn_commas
        def bn_date(d_str):
            try:
                d = datetime.strptime(d_str, "%Y-%m-%d")
                months = ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর"]
                return f"{to_bn(d.day)} {months[d.month-1]}"
            except: return to_bn(d_str)

        dates = [s["date"] for s in stats]
        bn_dates = [bn_date(d) for d in dates]
        
        # Define metrics mapping
        metrics_cfg = {
            "total_words": {"data": [s["total_words"] for s in stats], "label": "মোট শব্দসংখ্যা বৃদ্ধি", "title_suffix": "শব্দসংখ্যা লেখচিত্র", "color": "#2563eb", "type": "area"},
            "total_count": {"data": [s["total_count"] for s in stats], "label": "মোট নিবন্ধ সংখ্যা", "title_suffix": "নিবন্ধ সংখ্যা লেখচিত্র", "color": "#10b981", "type": "area"},
            "daily_count": {"data": [s["daily_count"] for s in stats], "label": "প্রতিদিনের নিবন্ধ জমা", "title_suffix": "প্রতিদিনের নিবন্ধ জমা লেখচিত্র", "color": "#f59e0b", "type": "bar"},
            "daily_words": {"data": [s["daily_words"] for s in stats], "label": "প্রতিদিনের শব্দসংখ্যা", "title_suffix": "প্রতিদিনের শব্দসংখ্যা লেখচিত্র", "color": "#8b5cf6", "type": "bar"}
        }

        # DEFINITIVE FONT FIX:
        import matplotlib.font_manager as fm
        font_candidates = ['Kalpurush', 'Nirmala UI', 'Nikosh', 'Siyam Rupali', 'Arial Unicode MS']
        available_fonts = {f.name: f.fname for f in fm.fontManager.ttflist}
        
        chosen_font = next((f for f in font_candidates if f in available_fonts), 'sans-serif')
        font_path = available_fonts.get(chosen_font)
        
        if font_path:
            fm.fontManager.addfont(font_path) # Force register
        
        # Configure global parameters BEFORE creating the figure
        plt.rcParams['font.family'] = chosen_font
        plt.rcParams['svg.fonttype'] = 'none'  # ALWAYS keep text as text in SVG for browser shaping
        plt.rcParams['pdf.fonttype'] = 42
        plt.rcParams['axes.unicode_minus'] = False
        
        # Use FontProperties for explicit control in text calls
        bn_prop = fm.FontProperties(fname=font_path) if font_path else fm.FontProperties(family='sans-serif')
        bn_prop_bold = fm.FontProperties(fname=font_path, weight='bold') if font_path else fm.FontProperties(family='sans-serif', weight='bold')

        # Setup plot
        fig, ax = plt.subplots(figsize=(11, 6.5))
        
        if metric and metric in metrics_cfg:
            cfg = metrics_cfg[metric]
            vals = cfg["data"]
            
            if cfg["type"] == "area":
                ax.fill_between(bn_dates, vals, color=cfg["color"], alpha=0.1)
                ax.plot(bn_dates, vals, color=cfg["color"], linewidth=3)
                # Add interactive markers
                for i in range(len(bn_dates)):
                    ax.plot(bn_dates[i], vals[i], color=cfg["color"], marker='o', markersize=7, 
                            gid=f"marker_{metric}_{i}")
            else:
                bars = ax.bar(bn_dates, vals, color=cfg["color"], alpha=0.7)
                for i, bar in enumerate(bars):
                    bar.set_gid(f"marker_{metric}_{i}")
            
            ax.set_ylabel(cfg["label"], fontproperties=bn_prop_bold, fontsize=13, color=cfg["color"])
            plt.title(f'{e_name}: {cfg["title_suffix"]}', fontproperties=bn_prop_bold, fontsize=15, pad=15)
        else:
            # Dual-axis default
            counts = metrics_cfg["total_count"]["data"]
            words = metrics_cfg["total_words"]["data"]
            
            color_articles = '#10b981'
            ax.set_ylabel('মোট নিবন্ধ সংখ্যা', fontproperties=bn_prop_bold, color=color_articles, fontsize=13)
            ax.bar(bn_dates, counts, color=color_articles, alpha=0.2)
            ax.plot(bn_dates, counts, color=color_articles, marker='o', linewidth=2)
            
            # GIDs for default view articles
            for i in range(len(bn_dates)):
                ax.plot(bn_dates[i], counts[i], color=color_articles, marker='o', markersize=5, gid=f"marker_total_count_{i}")
            
            ax.tick_params(axis='y', labelcolor=color_articles)
            
            ax2 = ax.twinx()
            color_words = '#2563eb'
            ax2.set_ylabel('মোট শব্দসংখ্যা বৃদ্ধি', fontproperties=bn_prop_bold, color=color_words, fontsize=13)
            ax2.plot(bn_dates, words, color=color_words, marker='s', linewidth=3)
            
            # GIDs for default view words
            for i in range(len(bn_dates)):
                ax2.plot(bn_dates[i], words[i], color=color_words, marker='s', markersize=6, gid=f"marker_total_words_{i}")
                
            ax2.tick_params(axis='y', labelcolor=color_words)
            
            # Apply Bengali font to ax2 ticks
            ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format_bn_num(x)))
            for label in ax2.get_yticklabels():
                label.set_fontproperties(bn_prop)
                
            plt.title(f'{e_name}: অগ্রগতি লেখচিত্র', fontproperties=bn_prop_bold, fontsize=17, pad=20)

        # Apply font to ALL primary ticks
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format_bn_num(x)))
        for label in ax.get_xticklabels():
            label.set_fontproperties(bn_prop)
        for label in ax.get_yticklabels():
            label.set_fontproperties(bn_prop)
            
        ax.set_xlabel('তারিখ', fontproperties=bn_prop, fontsize=12)
        plt.xticks(rotation=45, ha='right')
        ax.grid(axis='y', linestyle='--', alpha=0.4)
        fig.tight_layout()
        
        # Save to SVG
        svg_buf = io.BytesIO()
        plt.savefig(svg_buf, format='svg', bbox_inches='tight')
        plt.close(fig)
        
        # POST-PROCESS SVG FOR INTERACTIVITY
        try:
            import xml.etree.ElementTree as ET
            # Fix namespaces
            svg_ns = "http://www.w3.org/2000/svg"
            xhtml_ns = "http://www.w3.org/1999/xhtml"
            ET.register_namespace('', svg_ns)
            ET.register_namespace('xlink', "http://www.w3.org/1999/xlink")
            
            svg_tree = ET.fromstring(svg_buf.getvalue())
            
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
                    var bg = document.getElementById('infobox-bg');
                    
                    t_title.textContent = title;
                    t_title.setAttribute('fill', color);
                    t_date.textContent = 'তারিখ: ' + date;
                    t_val.textContent = 'মান: ' + val;
                    t_exact.textContent = 'সঠিক মান: ' + exactVal;
                    
                    tooltip.setAttribute('visibility', 'visible');
                    
                    var svg = evt.target.ownerSVGElement;
                    var pt = svg.createSVGPoint();
                    pt.x = evt.clientX;
                    pt.y = evt.clientY;
                    var cursorpt = pt.matrixTransform(svg.getScreenCTM().inverse());
                    
                    // Position adjustment
                    var x = cursorpt.x + 15;
                    var y = cursorpt.y + 15;
                    if (x > svg.viewBox.baseVal.width - 210) x = cursorpt.x - 215;
                    if (y > svg.viewBox.baseVal.height - 110) y = cursorpt.y - 115;
                    
                    tooltip.setAttribute('transform', 'translate(' + x + ',' + y + ')');
                }
                function hideTooltip() {
                    document.getElementById('svg-infobox').setAttribute('visibility', 'hidden');
                }
            """
            svg_tree.append(script)
            
            # 3. Add Tooltip Attributes to Markers
            for el in svg_tree.iter():
                gid = el.get('id')
                if gid and gid.startswith('marker_'):
                    parts = gid.split('_')
                    if len(parts) >= 3:
                        m_key = "_".join(parts[1:-1])
                        idx = int(parts[-1])
                        
                        if m_key in metrics_cfg and idx < len(stats):
                            m_info = metrics_cfg[m_key]
                            date_str = bn_date(stats[idx]["date"])
                            val_str = format_bn_num(stats[idx][m_key])
                            exact_val_str = format_bn_commas(stats[idx][m_key])
                            color = m_info["color"]
                            
                            # Escape single quotes in titles if any
                            safe_title = m_info['label'].replace("'", "\\'")
                            el.set('onmousemove', f"showTooltip(evt, '{safe_title}', '{date_str}', '{val_str}', '{exact_val_str}', '{color}')")
                            el.set('onmouseout', "hideTooltip()")
            
            # 4. Create the Infobox Element (Hidden by default)
            infobox = ET.SubElement(svg_tree, f'{{{svg_ns}}}g')
            infobox.set('id', 'svg-infobox')
            infobox.set('visibility', 'hidden')
            infobox.set('pointer-events', 'none')
            
            # Background rect (Native SVG)
            bg = ET.SubElement(infobox, f'{{{svg_ns}}}rect')
            bg.set('id', 'infobox-bg')
            bg.set('width', '210')
            bg.set('height', '105')
            bg.set('fill', 'white')
            bg.set('stroke', '#2563eb')
            bg.set('stroke-width', '2')
            bg.set('rx', '8')
            bg.set('ry', '8')
            bg.set('style', 'opacity: 0.95;')
            
            # Title text
            t1 = ET.SubElement(infobox, f'{{{svg_ns}}}text')
            t1.set('id', 'infobox-title')
            t1.set('x', '12')
            t1.set('y', '22')
            t1.set('font-family', 'sans-serif')
            t1.set('font-weight', 'bold')
            t1.set('font-size', '14px')
            
            # Date text
            t2 = ET.SubElement(infobox, f'{{{svg_ns}}}text')
            t2.set('id', 'infobox-date')
            t2.set('x', '12')
            t2.set('y', '44')
            t2.set('font-family', 'sans-serif')
            t2.set('font-size', '12px')
            t2.set('fill', '#475569')
            
            # Value text
            t3 = ET.SubElement(infobox, f'{{{svg_ns}}}text')
            t3.set('id', 'infobox-val')
            t3.set('x', '12')
            t3.set('y', '66')
            t3.set('font-family', 'sans-serif')
            t3.set('font-weight', 'bold')
            t3.set('font-size', '14px')
            t3.set('fill', '#1e293b')

            # Exact value text
            t4 = ET.SubElement(infobox, f'{{{svg_ns}}}text')
            t4.set('id', 'infobox-exact')
            t4.set('x', '12')
            t4.set('y', '88')
            t4.set('font-family', 'sans-serif')
            t4.set('font-size', '12px')
            t4.set('fill', '#64748b')
            
            final_svg = ET.tostring(svg_tree, encoding='utf-8', method='xml')
            return Response(
                content=final_svg, 
                media_type="image/svg+xml",
                headers={"Content-Disposition": f"attachment; filename=progress_{code}.svg"}
            )
        except Exception as e:
            return Response(
                content=svg_buf.getvalue(), 
                media_type="image/svg+xml",
                headers={"Content-Disposition": f"attachment; filename=progress_{code}.svg"}
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
