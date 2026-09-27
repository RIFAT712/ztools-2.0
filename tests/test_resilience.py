"""Failure-injection checks for the resilience fixes. Scratch DB, all network faked. Run: python tests/test_resilience.py"""
import os, sys, io, json, time, asyncio, sqlite3, tempfile
TMP = tempfile.mkdtemp()
os.environ["TOOL_DATA_DIR"] = TMP  # production-like: NFS path -> rollback journal
os.environ.update(ADMIN_USER="admin", ADMIN_PASS="pw")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core.config as cfg
cfg.LOG_DIR = os.path.join(TMP, "logs")
import services.monitor as mon
mon.start_background_services = lambda: None
import httpx
import main, core.api as capi, core.processor as pr, core.db as cdb, core.logger as lg
from fastapi.testclient import TestClient

c = TestClient(main.app, raise_server_exceptions=False)
H = {"Authorization": "Bearer " + c.post("/api/admin/login", data={"username": "admin", "password": "pw"}).json()["access_token"]}
db = main.db

class FakeResp:
    def __init__(self, body): self.body = body
    def raise_for_status(self): pass
    def json(self): return self.body

def fake_fountain(body):
    calls = []
    capi.requests.get = lambda url, **k: (calls.append(url), FakeResp(body))[1]
    return calls

def rows(sql, *a):
    with db as conn: return conn.execute(sql, a).fetchall()

def test_commit_failure_is_not_success():                  # C1
    orig = cdb.DatabaseManager.connect
    cdb.DatabaseManager.connect = lambda self: sqlite3.connect(self.db_path, timeout=1, check_same_thread=False)
    reader = sqlite3.connect(db.db_path); reader.execute("BEGIN"); reader.execute("SELECT * FROM banned_users").fetchall()
    try:
        r = c.post("/api/admin/ban", json={"code": "e", "username": "Mallory"}, headers=H)
    finally:
        reader.rollback(); reader.close(); cdb.DatabaseManager.connect = orig
    assert r.status_code == 500, r.text                       # was: 200 "success"
    assert rows("SELECT * FROM banned_users WHERE username = 'Mallory'") == []
    r = c.post("/api/admin/ban", json={"code": "e", "username": "Mallory"}, headers=H)   # retry once the lock clears
    assert r.status_code == 200 and len(rows("SELECT * FROM banned_users WHERE username = 'Mallory'")) == 1

def test_malformed_fountain_reply():                        # C2
    good = {"code": "m", "wiki": "wiki:bn", "articles": [{"name": "A", "user": "U", "marks": []}]}
    with db as conn:
        conn.execute("INSERT OR REPLACE INTO enabled_editathons (code) VALUES ('m')")
        conn.execute("INSERT OR REPLACE INTO fountain_cache VALUES ('m', ?, 'x')", (json.dumps(good),))
    for bad in ({"detail": "upstream error"}, ["not", "a", "contest"], "oops"):
        fake_fountain(bad)
        assert capi.fetch_fountain_data("m", force_fresh=True) == good      # falls back to last good copy
        assert json.loads(rows("SELECT data FROM fountain_cache WHERE code = 'm'")[0][0]) == good  # never overwritten
    fake_fountain({"detail": "x"})
    try: capi.fetch_fountain_data("nocache", force_fresh=True); assert False, "should raise without a cache"
    except ValueError: pass
    with db as conn: conn.execute("UPDATE fountain_cache SET data = '[1, 2]' WHERE code = 'm'")   # already-poisoned row
    fake_fountain(good)
    assert c.post("/api/jury_stats", json={"code": "m"}).status_code == 200   # was: 500 until the next good fetch

def test_empty_fountain_list_keeps_counts():                # C2
    with db as conn:
        for i in range(5):
            conn.execute("INSERT INTO wordcount_cache (editathon_code, title_hash, article_title, words, wiki, rules_v) VALUES ('w', ?, ?, 100, 'bnwiki', ?)", (f"h{i}", f"A{i}", pr.RULES_VERSION))
    orig = pr.fetch_fountain_data
    pr.fetch_fountain_data = lambda code, force_fresh=False: {"code": "w", "articles": []}
    try: asyncio.run(pr.refresh_editathon_data("w"))
    finally: pr.fetch_fountain_data = orig
    assert len(rows("SELECT * FROM wordcount_cache WHERE editathon_code = 'w'")) == 5   # was: 0

def test_untracked_codes_rejected():                        # C3
    calls = fake_fountain({"code": "x", "articles": []})
    for ep in ("/api/jury_stats", "/api/rejected_articles", "/api/daily_stats"):
        assert c.post(ep, json={"code": "untracked"}).status_code == 403
    assert calls == [] and rows("SELECT * FROM fountain_cache WHERE code = 'untracked'") == []
    with db as conn: conn.execute("INSERT OR REPLACE INTO enabled_editathons (code) VALUES ('t')")
    for ep in ("/api/jury_stats", "/api/rejected_articles", "/api/daily_stats"):
        assert c.post(ep, json={"code": "t"}).status_code == 200

def test_login_does_not_block_server():                     # C4
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as ac:
            t0 = time.perf_counter()
            async def health():
                await asyncio.sleep(0.05); sent = time.perf_counter() - t0
                await ac.get("/health"); return sent, time.perf_counter() - t0
            res = await asyncio.gather(*[ac.post("/api/admin/login", data={"username": "admin", "password": "bad"}) for _ in range(20)], health())
            assert all(r.status_code == 401 for r in res[:-1])
            return res[-1]
    sent, answered = asyncio.run(run())
    assert sent < 0.2 and answered - sent < 0.2, (sent, answered)   # was: sent at ~1.2 s, loop blocked by scrypt

def test_stream_always_ends_with_outcome():                 # C5
    fountain = {"code": "s", "wiki": "wiki:bn", "articles": [{"name": "A", "user": "U", "marks": []}]}
    with db as conn:
        conn.execute("INSERT OR REPLACE INTO fountain_cache VALUES ('s', ?, 'x')", (json.dumps(fountain),))
    async def slow_batch(session, api_url, titles, code=None, at=None):
        await asyncio.sleep(0.2); return {t: (7, t, False, "LIVE", 1) for t in titles}
    async def no_session(): return None
    saved = pr.fetch_fountain_data, pr.count_words_batch, pr.get_session
    pr.fetch_fountain_data, pr.count_words_batch, pr.get_session = (lambda code, force_fresh=False: fountain), slow_batch, no_session
    kinds = lambda q: [i if isinstance(i, str) else i["type"] for i in [q.get_nowait() for _ in range(q.qsize())]]
    async def two_viewers():
        q1, q2 = asyncio.Queue(), asyncio.Queue()
        await asyncio.gather(pr.process_word_counts_async("s", q1), pr.process_word_counts_async("s", q2))
        return kinds(q1), kinds(q2)
    async def fountain_down():
        q = asyncio.Queue(); await pr.process_word_counts_async("s", q); return kinds(q)
    try:
        k1, k2 = asyncio.run(two_viewers())
        assert "complete" in k1 and "complete" in k2, (k1, k2)          # was: second viewer had no 'complete'
        def boom(code, force_fresh=False): raise ConnectionError("Fountain down")
        pr.fetch_fountain_data = boom
        k = asyncio.run(fountain_down())
        assert "error" in k and "cache" in k, k                          # was: silent end, no error
    finally:
        pr.fetch_fountain_data, pr.count_words_batch, pr.get_session = saved

def test_http_timeout_bounded():                            # C6
    async def run():
        s = await capi.get_session(); t = s.timeout.total; await capi.close_session(); return t
    assert asyncio.run(run()) == 60                           # was: 300

def test_errors_reach_stderr():                             # C7
    buf = io.StringIO(); old = lg.stderr_handler.setStream(buf)
    try: lg.smart_log("probe-error-line", "ERROR"); lg.smart_log("probe-info-line")
    finally: lg.stderr_handler.setStream(old)
    out = buf.getvalue()
    assert "probe-error-line" in out and "probe-info-line" in out and out.count("probe-error-line") == 1

for name, fn in list(globals().items()):
    if name.startswith("test_"):
        fn(); print("ok", name)
print("resilience OK")
