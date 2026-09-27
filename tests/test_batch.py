"""Self-check for word counting against a fake MediaWiki API. Run: python tests/test_batch.py"""
import os, sys, asyncio, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core.config as cfg
tmp = tempfile.mkdtemp()
cfg.DB_FILE, cfg.LOG_DIR = os.path.join(tmp, "t.db"), os.path.join(tmp, "logs")
from core.db import db
import core.processor as pr

CATEGORY = "[[বিষয়শ্রেণী:খাবার]]"  # NFC form, exactly as MediaWiki stores it
TEXT = "আমি ভাত খাই " + CATEGORY

class FakeResp:
    def __init__(self, status, body): self.status, self.body = status, body
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass
    async def json(self): return self.body

class FakeSession:
    """Serves at most `cap` page contents per reply (mimics the API result-size limit). `revs` = current revid per title."""
    def __init__(self, cap=50, fail=False, revs=None): self.cap, self.fail, self.revs, self.calls = cap, fail, revs or {}, []
    def post(self, url, data):
        self.calls.append(data)
        if self.fail: return FakeResp(500, {})
        titles, pages, served = data["titles"].split("|"), [], 0
        q = {"normalized": [], "redirects": [], "pages": pages}
        for t in titles:
            n = t[0].upper() + t[1:]
            if n != t: q["normalized"].append({"from": t, "to": n})
            if n == "Old": q["redirects"].append({"from": n, "to": "New"}); n = "New"
            if n.startswith("Missing"): pages.append({"title": n, "missing": True}); continue
            page = {"title": n, "lastrevid": self.revs.get(n, 1)}
            if data["prop"] == "revisions" and served < self.cap:
                page["revisions"] = [{"revid": self.revs.get(n, 1), "slots": {"main": {"content": TEXT}}}]
                served += 1
            pages.append(page)
        return FakeResp(200, {"query": q})

async def test_batch():
    assert pr.count_bn_words(TEXT) == 3                       # category link is stripped
    s = FakeSession()
    r = await pr.count_words_batch(s, "api", ["ক", "Old", "MissingX", "x"])
    assert len(s.calls) == 1
    assert r["ক"] == (3, "ক", False, "LIVE", 1)
    assert r["Old"] == (3, "New", True, "LIVE", 1)            # redirect followed
    assert r["MissingX"] == (0, "MissingX", False, "MISSING", None)
    assert r["x"] == (3, "X", False, "LIVE", 1)               # normalized title mapped back

    s = FakeSession(cap=2)                                    # truncated replies -> split and retry
    titles = [f"t{i}" for i in range(7)]
    r = await pr.count_words_batch(s, "api", titles)
    assert all(r[t][3] == "LIVE" for t in titles) and len(s.calls) > 1

    s = FakeSession()                                         # deadline revision
    r = await pr.count_words_batch(s, "api", ["ক"], at="2026-01-01T00:00:00Z")
    assert r["ক"][3] == "FINAL" and s.calls[0]["rvstart"] == "2026-01-01T00:00:00Z"

    with db as conn:                                          # total failure -> STALE, else ERROR
        conn.execute("INSERT INTO wordcount_cache (editathon_code, title_hash, words, actual_title, is_redirect, revid) VALUES ('c', ?, 42, 'A', 0, 7)", (pr.get_title_hash("A"),))
    orig_sleep = pr.asyncio.sleep
    pr.asyncio.sleep = lambda *_: orig_sleep(0)
    r = await pr.count_words_batch(FakeSession(fail=True), "api", ["A", "B"], code="c")
    pr.asyncio.sleep = orig_sleep
    assert r["A"] == (42, "A", False, "STALE", 7) and r["B"] == (None, "B", False, "ERROR", None)

async def test_refresh():
    fountain = {"code": "e", "wiki": "wiki:bn", "articles": [{"name": n, "user": "U", "marks": []} for n in ("A", "B", "C")]}
    pr.fetch_fountain_data = lambda code, force_fresh=False: fountain
    s = FakeSession(revs={"A": 1, "B": 1, "C": 1})
    async def fake_session(): return s
    pr.get_session = fake_session
    def set_finish(f):
        with db as conn: conn.execute("INSERT OR REPLACE INTO enabled_editathons (code, finish) VALUES ('e', ?)", (f,))
    def rows():
        with db as conn:
            return {r[0]: r[1:] for r in conn.execute("SELECT article_title, last_updated, revid, rules_v FROM wordcount_cache WHERE editathon_code = 'e'")}

    set_finish("2999-01-01T00:00:00Z")                        # active contest
    await pr.refresh_editathon_data("e", check_revisions=True)
    assert len(s.calls) == 1 and rows()["B"] == ("LIVE", 1, pr.RULES_VERSION)   # all 3 in one batch

    s.calls.clear(); s.revs["B"] = 2                          # B edited while the live stream was down
    await pr.refresh_editathon_data("e", check_revisions=True)
    assert [c["prop"] for c in s.calls] == ["info", "revisions"] and s.calls[1]["titles"] == "B"
    assert rows()["B"][1] == 2

    s.calls.clear()                                           # nothing changed -> only the cheap revid check
    await pr.refresh_editathon_data("e", check_revisions=True)
    assert [c["prop"] for c in s.calls] == ["info"]

    with db as conn: conn.execute("UPDATE wordcount_cache SET rules_v = 1 WHERE article_title = 'A'")
    s.calls.clear()                                           # counted under old rules -> recounted
    await pr.refresh_editathon_data("e")
    assert [c["titles"] for c in s.calls] == ["A"]

    set_finish("2000-01-01T00:00:00Z")                        # contest over: each article counted at deadline, once
    s.calls.clear()
    await pr.refresh_editathon_data("e", check_revisions=True)
    assert len(s.calls) == 3 and all(c.get("rvstart") == "2000-01-01T00:00:00Z" for c in s.calls)
    assert all(v[0] == "FINAL" for v in rows().values())
    s.calls.clear(); s.revs["C"] = 9
    await pr.refresh_editathon_data("e", check_revisions=True)
    await pr.refresh_editathon_data("e", target_article="C")  # live edit after the deadline
    assert s.calls == []                                      # frozen

db.init_db(set())
asyncio.run(test_batch())
asyncio.run(test_refresh())
print("batch OK")
