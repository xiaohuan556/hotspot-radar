#!/usr/bin/env python3
"""热点雷达 Web 版 — Flask 后端"""
import os, json, hashlib
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode, quote
import xml.etree.ElementTree as ET
import threading

from flask import Flask, jsonify, render_template, request

# ── .env ──
PROJECT = Path(__file__).parent
ENV_FILE = PROJECT / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("\"'")
            if k and k not in os.environ: os.environ[k] = v

DEEPSEEK_KEY = os.getenv("OPENAI_API_KEY", "")
DEEPSEEK_BASE = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
YOUTUBE_KEY = os.getenv("YOUTUBE_API_KEY", "")
TMDB_KEY = os.getenv("TMDB_API_KEY", "")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
TRENDMCP_KEY = os.getenv("TRENDMCP_KEY", "")

CAT_COLORS = {
    "🔥 热门Meme": "#E0646E",
    "🌟 娱乐新闻": "#CB9842",
    "🎬 电影资讯": "#787CE6",
    "🏈 体育热点": "#44A87A",
    "📹 视频热点": "#D0659E",
    "🌍 全球热帖": "#5B8FDF",
    "🔍 搜索趋势": "#8B7CF6",
}
CAT_KEYS = list(CAT_COLORS.keys())

app = Flask(__name__)

# ═══════════════ 数据获取（和 main.py 完全一致） ═══════════════

def fetch_reddit(subreddits=None, limit=15):
    if subreddits is None:
        subreddits = {
            "memes": "memes+dankmemes+me_irl+funny",
            "entertainment": "entertainment+television+movies",
            "sports": "sports+nba+soccer+nfl",
            "worldnews": "worldnews+news",
        }
    results = []
    headers = {"User-Agent": "HotRadar/5.0"}
    for category, subs in subreddits.items():
        try:
            url = f"https://www.reddit.com/r/{subs}/hot.json?limit={limit}"
            req = Request(url, headers=headers)
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            for post in data.get("data", {}).get("children", []):
                p = post["data"]
                if p.get("stickied"): continue
                selftext = p.get("selftext", "")[:200]
                results.append(dict(
                    id=f"reddit_{p['id']}", title=p["title"],
                    source=f"r/{p['subreddit']}", category=category,
                    url=f"https://reddit.com{p['permalink']}",
                    score=p.get("score", 0), comments=p.get("num_comments", 0),
                    desc=(selftext or p["title"])[:200],
                ))
        except Exception as e:
            print(f"[Reddit] {category}: {e}")
    return results

def fetch_youtube(max_results=12):
    if not YOUTUBE_KEY: return []
    try:
        params = dict(part="snippet", chart="mostPopular", regionCode="US",
                      maxResults=max_results, key=YOUTUBE_KEY)
        url = f"https://www.googleapis.com/youtube/v3/videos?{urlencode(params)}"
        with urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        results = []
        for item in data.get("items", []):
            s = item.get("snippet", {})
            results.append(dict(
                id=f"yt_{item['id']}", title=s.get("title", ""),
                source=s.get("channelTitle", "YouTube"), category="video",
                url=f"https://youtube.com/watch?v={item['id']}",
                desc=s.get("description", "")[:200],
            ))
        return results
    except Exception as e:
        print(f"[YouTube]: {e}"); return []

def fetch_tmdb():
    if not TMDB_KEY: return []
    results = []
    try:
        for ep in ["/movie/upcoming", "/trending/movie/week"]:
            url = f"https://api.themoviedb.org/3{ep}?api_key={TMDB_KEY}&language=zh-CN&region=US"
            with urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
            for item in data.get("results", [])[:10]:
                results.append(dict(
                    id=f"tmdb_{item['id']}", title=item.get("title", ""),
                    source="TMDB", category="movie",
                    url=f"https://www.themoviedb.org/movie/{item['id']}",
                    desc=(item.get("overview") or "")[:200],
                    score=int(item.get("vote_average", 0) * 100),
                ))
        return results
    except Exception as e:
        print(f"[TMDB]: {e}"); return []

def fetch_newsapi(max_results=10):
    if not NEWSAPI_KEY: return []
    results = []
    queries = {
        "entertainment": "entertainment OR celebrity OR Hollywood",
        "sports": "sports OR NFL OR NBA OR soccer",
    }
    for cat, q in queries.items():
        try:
            url = (f"https://newsapi.org/v2/everything?"
                   f"q={quote(q)}&language=en&sortBy=popularity&pageSize={max_results}&apiKey={NEWSAPI_KEY}")
            with urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
            for a in data.get("articles", []):
                results.append(dict(
                    id=f"news_{hashlib.md5(a['url'].encode()).hexdigest()[:12]}",
                    title=a.get("title", ""),
                    source=a.get("source", {}).get("name", "News"), category=cat,
                    url=a.get("url", ""), desc=(a.get("description") or "")[:200],
                ))
        except Exception as e:
            print(f"[NewsAPI] {cat}: {e}")
    return results

RSS_FEEDS = {
    "entertainment": [
        ("Variety", "https://variety.com/feed/"),
        ("Deadline", "https://deadline.com/feed/"),
        ("Hollywood Reporter", "https://feeds.feedburner.com/thr/news"),
        ("Billboard", "https://www.billboard.com/feed/"),
    ],
    "sports": [
        ("ESPN", "https://www.espn.com/espn/rss/news"),
        ("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml"),
        ("Yahoo Sports", "https://sports.yahoo.com/rss/"),
    ],
    "world": [("BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml")],
}

def fetch_rss(categories=None):
    """categories: 要获取的分类列表，None=全部。如 ['entertainment', 'sports']"""
    results = []
    for category, feeds in RSS_FEEDS.items():
        if categories and category not in categories:
            continue
        for name, url in feeds:
            try:
                req = Request(url, headers={"User-Agent": "HotRadar/5.0"})
                with urlopen(req, timeout=10) as resp:
                    content = resp.read().decode("utf-8", errors="replace")
                root = ET.fromstring(content)
                for item in root.iter("item"):
                    title = item.find("title")
                    link = item.find("link")
                    desc = item.find("description")
                    if title is None or not title.text: continue
                    import re
                    desc_text = ""
                    if desc is not None and desc.text:
                        desc_text = re.sub(r'<[^>]+>', '', desc.text)[:200]
                    results.append(dict(
                        id=f"rss_{hashlib.md5((title.text or '').encode()).hexdigest()[:12]}",
                        title=title.text.strip(), source=name, category=category,
                        url=link.text.strip() if link is not None else "",
                        desc=desc_text,
                    ))
            except Exception as e:
                print(f"[RSS] {name}: {e}")
    return results

def fetch_trendmcp(source, limit=20):
    if not TRENDMCP_KEY: return []
    try:
        body = json.dumps({"mode": "top_trends", "type": source, "limit": limit}).encode()
        req = Request("https://api.trendsmcp.ai/api", data=body, headers={
            "Authorization": f"Bearer {TRENDMCP_KEY}",
            "Content-Type": "application/json"
        })
        with urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read())
        if isinstance(raw, dict) and "body" in raw:
            data = json.loads(raw["body"])
        else:
            data = raw
        results = []
        for rk, name in data.get("data", []):
            results.append(dict(
                id=f"trend_{hashlib.md5(name.encode()).hexdigest()[:12]}",
                title=name, source=source, category="trend",
                url=f"https://trends.google.com/trends/explore?q={quote(name)}",
                score=rk, desc="",
            ))
        return results
    except Exception as e:
        print(f"[TrendMCP] {source}: {e}")
        return []

def fetch_x_trends(limit=25):
    if not TRENDMCP_KEY: return []
    try:
        body = json.dumps({"mode": "top_trends", "type": "X (Twitter)", "limit": limit}).encode()
        req = Request("https://api.trendsmcp.ai/api", data=body, headers={
            "Authorization": f"Bearer {TRENDMCP_KEY}",
            "Content-Type": "application/json"
        })
        with urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read())
        if isinstance(raw, dict) and "body" in raw:
            data = json.loads(raw["body"])
        else:
            data = raw
        results = []
        for rk, name in data.get("data", []):
            results.append(dict(
                id=f"xt_{hashlib.md5(name.encode()).hexdigest()[:12]}",
                title=name, source="X (Twitter)", category="x_trend",
                url=f"https://x.com/search?q={quote(name)}",
                score=rk, desc="",
            ))
        if results: return results
    except Exception as e:
        print(f"[X Trends]: {e}")
    # fallback to Google News
    try:
        body = json.dumps({"mode": "top_trends", "source": "google news", "limit": limit}).encode()
        req = Request("https://api.trendsmcp.ai/api", data=body, headers={
            "Authorization": f"Bearer {TRENDMCP_KEY}",
            "Content-Type": "application/json"
        })
        with urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read())
        if isinstance(raw, dict) and "body" in raw:
            data = json.loads(raw["body"])
        else:
            data = raw
        results = []
        for rk, name in data.get("data", []):
            results.append(dict(
                id=f"soc_{hashlib.md5(name.encode()).hexdigest()[:12]}",
                title=name, source="Google News", category="social",
                url=f"https://news.google.com/search?q={quote(name)}",
                score=rk, desc="",
            ))
        return results
    except Exception as e:
        print(f"[SocialTrends]: {e}")
        return []

def translate_text(text):
    if not DEEPSEEK_KEY or not text: return text
    try:
        from openai import OpenAI
        client = OpenAI(api_key=DEEPSEEK_KEY, base_url=DEEPSEEK_BASE, timeout=20.0)
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "system", "content": "翻译为中文，只输出译文，不要解释。"},
                      {"role": "user", "content": text}],
            temperature=0.3, max_tokens=100,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ {e}"


# ═══════════════ 路由 ═══════════════

@app.route("/")
def index():
    return render_template("index.html",
        cat_keys_json=json.dumps(CAT_KEYS, ensure_ascii=False),
        cat_colors_json=json.dumps(CAT_COLORS, ensure_ascii=False))

@app.route("/api/refresh")
def api_refresh():
    """获取所有分类的热点数据"""
    results = {}
    sections = [
        ("🔥 热门Meme", lambda: fetch_reddit({"memes": "memes+dankmemes+funny"})),
        ("🌟 娱乐新闻", lambda: fetch_newsapi() + fetch_rss(categories=["entertainment"])),
        ("🎬 电影资讯", fetch_tmdb),
        ("🏈 体育热点", lambda: fetch_rss(categories=["sports"])),
        ("📹 视频热点", fetch_youtube),
        ("🌍 全球热帖", lambda: fetch_reddit({"worldnews": "worldnews+news+all"}, 10)),
        ("🔍 搜索趋势", lambda: fetch_trendmcp("Google Trends", 20)),
    ]
    for name, func in sections:
        try:
            items = func()
        except Exception as e:
            items = []
            print(f"[API] {name}: {e}")
        results[name] = items[:20]
    return jsonify(results)

@app.route("/api/translate", methods=["POST"])
def api_translate():
    """翻译单条标题"""
    data = request.get_json()
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "empty text"}), 400
    result = translate_text(text)
    return jsonify({"translated": result})

@app.route("/api/translate-batch", methods=["POST"])
def api_translate_batch():
    """批量翻译"""
    data = request.get_json()
    texts = data.get("texts", [])
    results = {}
    for text in texts:
        results[text] = translate_text(text)
    return jsonify(results)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
