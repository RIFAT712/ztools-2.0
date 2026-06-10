import json
import requests
import aiohttp
import asyncio
from datetime import datetime, timedelta
from core.db import db
from core.utils import get_wiki_url
from core.config import USER_AGENT

async def get_session():
    loop = asyncio.get_running_loop()
    if not hasattr(loop, "_shared_session") or loop._shared_session.closed:
        loop._shared_session = aiohttp.ClientSession(
            headers={"User-Agent": USER_AGENT},
            connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
        )
    return loop._shared_session

async def close_session():
    try:
        loop = asyncio.get_running_loop()
        if hasattr(loop, "_shared_session"):
            session = loop._shared_session
            if not session.closed:
                await session.close()
            del loop._shared_session
    except RuntimeError:
        pass # No loop running

async def fetch_fountain_data_async(code, force_fresh=False):
    if not force_fresh:
        with db as conn:
            row = conn.execute("SELECT data FROM fountain_cache WHERE code = ?", (code,)).fetchone()
            if row: return json.loads(row[0])
    try:
        session = await get_session()
        async with session.get(f"https://fountain.toolforge.org/api/editathons/{code}", timeout=15) as resp:
            resp.raise_for_status()
            data = await resp.json()
            with db as conn:
                conn.execute("INSERT OR REPLACE INTO fountain_cache (code, data, last_updated) VALUES (?, ?, ?)", 
                             (code, json.dumps(data), datetime.now().isoformat()))
            return data
    except Exception as e:
        with db as conn:
            row = conn.execute("SELECT data FROM fountain_cache WHERE code = ?", (code,)).fetchone()
            if row: return json.loads(row[0])
        raise e

def fetch_fountain_data(code, force_fresh=False):
    # Synchronous wrapper for legacy compatibility
    if not force_fresh:
        with db as conn:
            row = conn.execute("SELECT data FROM fountain_cache WHERE code = ?", (code,)).fetchone()
            if row: return json.loads(row[0])
    try:
        resp = requests.get(f"https://fountain.toolforge.org/api/editathons/{code}", timeout=10, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        data = resp.json()
        with db as conn:
            conn.execute("INSERT OR REPLACE INTO fountain_cache (code, data, last_updated) VALUES (?, ?, ?)", 
                         (code, json.dumps(data), datetime.now().isoformat()))
        return data
    except Exception as e:
        with db as conn:
            row = conn.execute("SELECT data FROM fountain_cache WHERE code = ?", (code,)).fetchone()
            if row: return json.loads(row[0])
        raise e

def get_bn_editathons():
    try:
        data = requests.get("https://fountain.toolforge.org/api/editathons", timeout=10).json()
        cutoff = datetime.now() - timedelta(days=365)
        result = []
        for e in data:
            wiki = e.get("wiki", "bn")
            if (wiki.split(':')[1] if ':' in wiki else wiki) != "bn": continue
            try:
                if datetime.strptime(e.get("finish"), "%Y-%m-%dT%H:%M:%SZ") < cutoff: continue
            except: pass
            result.append({"code": e.get("code"), "name": e.get("name"), "wiki": wiki, "finish": e.get("finish"), "site_url": get_wiki_url(wiki)})
        return result
    except: return []
