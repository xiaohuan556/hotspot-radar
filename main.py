#!/usr/bin/env python3
"""
热点雷达 v4 - 海外热点聚合器
浅色主题 · 顶部Tab切换 · 双击跳转 · 流畅体验
"""
import sys, os, json, hashlib
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode, quote
import xml.etree.ElementTree as ET
import webbrowser
import threading

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

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QScrollArea, QFrame,
    QStackedWidget, QSizePolicy, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor, QMouseEvent

# ═══════════════ 主题色 ═══════════════
CAT_COLORS = {
    "🔥 热门Meme":    "#E0646E",
    "🌟 娱乐新闻":    "#CB9842",
    "🎬 电影资讯":    "#787CE6",
    "🏈 体育热点":    "#44A87A",
    "📹 视频热点":    "#D0659E",
    "🔍 搜索趋势":    "#8B7CF6",
}

CAT_KEYS = list(CAT_COLORS.keys())

# ═══════════════ 数据获取 ═══════════════
def fetch_reddit(subreddits=None, limit=15):
    if subreddits is None:
        subreddits = {
            "memes": "memes+dankmemes+me_irl+funny",
            "entertainment": "entertainment+television+movies",
            "sports": "sports+nba+soccer+nfl",
            "worldnews": "worldnews+news",
        }
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }
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

def fetch_meme_fallback(limit=15):
    """Reddit 被拦截时的 Meme 备用源：抓取 Know Your Meme /memes 最新条目"""
    results = []
    try:
        req = Request("https://knowyourmeme.com/memes", headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        import re
        # 匹配 entry grid 中的 <a> 块
        pattern = re.compile(
            r'<a[^>]+href="(/memes/[^"]+)"[^>]*>(.*?)</a>',
            re.S
        )
        seen = set()
        for match in pattern.finditer(html):
            href, block = match.group(1), match.group(2)
            # 跳过分页链接
            if "page/" in href:
                continue
            # 找图片
            img_match = re.search(r'<img[^>]+src="([^"]+)"', block)
            img = img_match.group(1) if img_match else ""
            # 优先从 h3.title 提取标题，回退到 span
            h3_match = re.search(r'<h3[^>]+class="title"[^>]*>([^<]+)</h3>', block)
            if h3_match:
                title = h3_match.group(1).strip()
            else:
                span_match = re.search(r'<span[^>]*>([^<]+)</span>', block)
                title = span_match.group(1).strip() if span_match else ""
            if not title or title in seen or len(title) < 3:
                continue
            # 过滤分类标签
            if title.lower() in ("meme", "subculture", "event", "entry", "photo", "video", "image"):
                continue
            seen.add(title)
            url = f"https://knowyourmeme.com{href}"
            img_url = img if img.startswith("http") else f"https:{img}" if img.startswith("//") else img
            results.append(dict(
                id=f"kym_{hashlib.md5(title.encode()).hexdigest()[:12]}",
                title=title,
                source="Know Your Meme", category="memes",
                url=url,
                score=0, comments=0,
                desc=title[:200],
                image=img_url,
            ))
            if len(results) >= limit:
                break
        if results:
            return results
    except Exception as e:
        print(f"[MemeFallback KYM]: {e}")

    # 降级到 Google News
    try:
        rss_url = "https://news.google.com/rss/search?q=viral+meme+funny+trending&hl=en-US&gl=US&ceid=US:en"
        req = Request(rss_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="replace")
        root = ET.fromstring(content)
        for i, item in enumerate(root.iter("item")):
            if i >= limit: break
            title = item.find("title")
            link = item.find("link")
            if title is None or not title.text: continue
            title_text = title.text.strip()
            if not any(k in title_text.lower() for k in ["meme", "viral", "tiktok", "funny", "trend", "internet"]):
                continue
            results.append(dict(
                id=f"meme_{hashlib.md5(title_text.encode()).hexdigest()[:12]}",
                title=title_text,
                source="Google News", category="memes",
                url=link.text.strip() if link is not None else "",
                score=0, comments=0,
                desc=title_text[:200],
            ))
        if results:
            return results
    except Exception as e:
        print(f"[MemeFallback GoogleNews]: {e}")

    return [dict(
        id="meme_notice", title="⚠️ Meme 数据源暂时不可用",
        source="系统提示", category="memes",
        url="", score=0, comments=0,
        desc="Reddit 和 Know Your Meme 均无法访问，请稍后再试。",
    )]

def fetch_google_trends(limit=20):
    """抓取 Google Trends RSS (Daily Search Trends)"""
    results = []
    ns = {"ht": "https://trends.google.com/trending/rss"}
    try:
        req = Request("https://trends.google.com/trending/rss?geo=US", headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="replace")
        root = ET.fromstring(content)
        for i, item in enumerate(root.findall(".//item")):
            if i >= limit:
                break
            title_el = item.find("title")
            traffic_el = item.find("ht:approx_traffic", ns)
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            traffic = traffic_el.text.strip() if traffic_el is not None and traffic_el.text else ""
            news_el = item.find("ht:news_item", ns)
            news_title = ""
            news_url = ""
            if news_el is not None:
                nt = news_el.find("ht:news_item_title", ns)
                nu = news_el.find("ht:news_item_url", ns)
                news_title = nt.text.strip() if nt is not None and nt.text else ""
                news_url = nu.text.strip() if nu is not None and nu.text else ""
            search_url = f"https://trends.google.com/trends/explore?q={quote(title)}"
            results.append(dict(
                id=f"trend_{hashlib.md5(title.encode()).hexdigest()[:12]}",
                title=title,
                source="Google Trends",
                category="trend",
                url=news_url or search_url,
                score=0,
                comments=0,
                desc=news_title or f"搜索量: {traffic}",
            ))
        return results
    except Exception as e:
        print(f"[GoogleTrends]: {e}")
        return []

    return [dict(
        id="meme_notice", title="⚠️ Meme 数据源暂时不可用",
        source="系统提示", category="memes",
        url="", score=0, comments=0,
        desc="Reddit 和 Know Your Meme 均无法访问，请稍后再试。",
    )]

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
    if not TMDB_KEY:
        return []  # 无Key时返回空，面板显示配置提示
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

def fetch_trendmcp(source, limit=20):
    """TrendMCP: 获取多平台趋势（Google Trends、新闻等）"""
    if not TRENDMCP_KEY:
        return []
    try:
        body = json.dumps({"mode": "top_trends", "type": source, "limit": limit}).encode()
        req = Request("https://api.trendsmcp.ai/api", data=body, headers={
            "Authorization": f"Bearer {TRENDMCP_KEY}",
            "Content-Type": "application/json"
        })
        with urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read())
        # 解析可能嵌套的响应
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
    """X热点：TrendMCP X (Twitter) 趋势（需付费套餐，无数据时用 Google News 兜底）"""
    if not TRENDMCP_KEY:
        return []
    # 先尝试 X
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
        if results:
            return results
    except Exception as e:
        print(f"[X Trends]: {e}")

    # X 无数据，降级到 Google News
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
                req = Request(url, headers={"User-Agent": "HotRadar/4.0"})
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

def translate_text(text):
    if not DEEPSEEK_KEY or not text:
        return text
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
        return f"⚠️ 翻译失败: {e}"

def llm_summary(items, category_name):
    if not DEEPSEEK_KEY or not items: return ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=DEEPSEEK_KEY, base_url=DEEPSEEK_BASE, timeout=30.0)
        titles = "\n".join(f"- {it['title']}" for it in items[:12])
        prompt = (f"以下是今日海外「{category_name}」热点标题，用中文写一句40字以内日报摘要，"
                  f"像新闻快报一样：\n\n{titles}")
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5, max_tokens=100,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return ""


# ═══════════════ 热点条目卡 ═══════════════
class HotItemWidget(QFrame):
    """单条热点：序号 + 标题 + 来源标签 + 热度 + 翻译 + 双击打开"""
    _trans_done_signal = pyqtSignal(str)

    CARD_NORMAL = (
        "HotItemWidget{background:#FFFFFF;border:1px solid #E8ECF1;border-radius:10px;}"
        "HotItemWidget:hover{background:#F0F6FF;border-color:#BFDBFE;}"
    )

    def __init__(self, item, color, rank, parent=None):
        super().__init__(parent)
        self._item = item
        self._color = color
        self._rank = rank
        self._translated = False
        self.setStyleSheet(self.CARD_NORMAL)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(52)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        # 序号
        lbl_rank = QLabel(f"{rank:02d}")
        lbl_rank.setFixedWidth(24)
        lbl_rank.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_rank.setStyleSheet(f"color:{color};font-size:11px;font-weight:700;")
        layout.addWidget(lbl_rank)

        # 翻译按钮 — 放在左侧固定位置，永不隐藏
        self.btn_trans = QPushButton("译")
        self.btn_trans.setFixedSize(26, 26)
        self.btn_trans.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_trans.setStyleSheet(
            f"QPushButton{{background:transparent;color:{color};border:1px solid {color}30;"
            f"border-radius:5px;font-size:10px;font-weight:600;}}"
            f"QPushButton:hover{{background:{color}12;border-color:{color}60;}}")
        self.btn_trans.clicked.connect(self._do_translate)
        layout.addWidget(self.btn_trans)

        # 分类色标竖线
        bar = QFrame()
        bar.setFixedWidth(4)
        bar.setFixedHeight(26)
        bar.setStyleSheet(f"background:{color};border-radius:2px;")
        layout.addWidget(bar)

        # 标题
        self.lbl_title = QLabel(item["title"])
        self.lbl_title.setWordWrap(False)
        self.lbl_title.setTextFormat(Qt.TextFormat.PlainText)
        self.lbl_title.setStyleSheet("color:#1E293B;font-size:13px;")
        layout.addWidget(self.lbl_title, 1)

        # 来源标签 — 中性配色
        src = item.get("source", "")
        if src:
            lbl_src = QLabel(src)
            lbl_src.setStyleSheet(
                "color:#475569;font-size:10px;background:#F1F5F9;"
                "border:1px solid #E2E8F0;border-radius:3px;padding:1px 6px;")
            lbl_src.setMaximumWidth(120)
            layout.addWidget(lbl_src)

        # 热度
        if item.get("score"):
            heat = item["score"]
            heat_str = f"{heat/1000:.1f}k" if heat >= 1000 else str(heat)
            lbl_heat = QLabel(f"⬆ {heat_str}")
            lbl_heat.setStyleSheet("color:#94A3B8;font-size:10px;")
            lbl_heat.setFixedWidth(46)
            lbl_heat.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(lbl_heat)

        # 信号连接
        self._trans_done_signal.connect(self._on_trans_done)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """双击打开对应链接"""
        url = self._item.get("url", "")
        if url:
            webbrowser.open(url)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        """单击也有视觉反馈"""
        super().mousePressEvent(event)

    def _do_translate(self):
        if self._translated:
            self.lbl_title.setText(self._item["title"])
            self.lbl_title.setStyleSheet("color:#1E293B;font-size:13px;")
            self.btn_trans.setText("译")
            self.btn_trans.setStyleSheet(
                f"QPushButton{{background:transparent;color:{self._color};"
                f"border:1px solid {self._color}30;border-radius:6px;font-size:11px;font-weight:600;}}"
                f"QPushButton:hover{{background:{self._color}12;border-color:{self._color}50;}}")
            self._translated = False
            return

        self.lbl_title.setText("⏳ 翻译中…")
        self.lbl_title.setStyleSheet("color:#94A3B8;font-size:13px;font-style:italic;")
        self.btn_trans.setEnabled(False)

        def _run():
            result = translate_text(self._item["title"])
            self._trans_done_signal.emit(result)
        threading.Thread(target=_run, daemon=True).start()

    def _on_trans_done(self, result):
        self.lbl_title.setText(result)
        self.lbl_title.setStyleSheet(f"color:{self._color};font-size:13px;font-weight:500;")
        self.btn_trans.setEnabled(True)
        self.btn_trans.setText("↩")
        self.btn_trans.setStyleSheet(
            f"QPushButton{{background:{self._color}15;color:{self._color};"
            f"border:1px solid {self._color}40;border-radius:6px;font-size:11px;font-weight:600;}}"
            f"QPushButton:hover{{background:{self._color}25;}}")
        self._translated = True


# ═══════════════ 分类内容面板 ═══════════════
class CategoryPanel(QWidget):
    trans_progress = pyqtSignal(int, int)  # done, total

    def __init__(self, category, color, parent=None):
        super().__init__(parent)
        self._category = category
        self._color = color
        self._items = []  # store HotItemWidget refs
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(12)

        # AI 摘要卡片
        self.summary_card = QFrame()
        self.summary_card.setStyleSheet(
            f"QFrame{{background:#F8FAFC;border:1px solid #E8ECF1;"
            f"border-radius:12px;border-left:4px solid {color};}}")
        sum_layout = QHBoxLayout(self.summary_card)
        sum_layout.setContentsMargins(16, 12, 16, 12)
        icon = QLabel("📊")
        icon.setStyleSheet("font-size:16px;")
        sum_layout.addWidget(icon)
        self.lbl_summary = QLabel("")
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setStyleSheet("color:#475569;font-size:12px;line-height:1.5;")
        sum_layout.addWidget(self.lbl_summary, 1)
        self.summary_card.hide()
        layout.addWidget(self.summary_card)

        # 列表头
        header = QHBoxLayout()
        header.setSpacing(8)
        lbl_rank_h = QLabel("#")
        lbl_rank_h.setFixedWidth(24)
        lbl_rank_h.setStyleSheet("color:#94A3B8;font-size:10px;font-weight:600;")
        lbl_rank_h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(lbl_rank_h)
        header.addSpacing(26)   # 译按钮宽度
        header.addSpacing(4)    # 色条宽度
        lbl_title_h = QLabel("标题 / 来源")
        lbl_title_h.setStyleSheet("color:#94A3B8;font-size:10px;font-weight:600;")
        header.addWidget(lbl_title_h, 1)

        # 全部翻译按钮
        self.btn_trans_all = QPushButton("全部翻译")
        self.btn_trans_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_trans_all.setFixedSize(72, 24)
        self.btn_trans_all.setStyleSheet(
            f"QPushButton{{background:transparent;color:{color};"
            f"border:1px solid {color}40;border-radius:6px;font-size:10px;}}"
            f"QPushButton:hover{{background:{color}10;border-color:{color};}}"
            f"QPushButton:disabled{{color:#C0C8D4;border-color:#E2E8F0;}}")
        self.btn_trans_all.clicked.connect(self._translate_all)
        header.addWidget(self.btn_trans_all)
        header.addSpacing(8)

        self.lbl_count = QLabel("加载中…")
        self.lbl_count.setStyleSheet("color:#94A3B8;font-size:10px;")
        header.addWidget(self.lbl_count)
        layout.addLayout(header)

        # 分隔线
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:#E8ECF1;")
        layout.addWidget(sep)

        # 列表区
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 4, 0, 0)
        self._list_layout.setSpacing(6)
        layout.addWidget(self._list_widget)
        layout.addStretch()

        # 进度信号
        self.trans_progress.connect(self._on_trans_progress)

    def set_items(self, items, summary=""):
        while self._list_layout.count():
            child = self._list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._items = []
        self.btn_trans_all.setEnabled(True)
        self.btn_trans_all.setText("全部翻译")

        if summary:
            self.lbl_summary.setText(summary)
            self.summary_card.show()
        else:
            self.summary_card.hide()

        shown = min(len(items), 20)
        for i, item in enumerate(items[:20], 1):
            w = HotItemWidget(item, self._color, i)
            self._list_layout.addWidget(w)
            self._items.append(w)

        if shown == 0:
            self.lbl_count.setText("暂无数据")
            self.btn_trans_all.setEnabled(False)
            hint_map = {
                "🎬 电影资讯": "⚠️ 未配置 TMDB_API_KEY → https://www.themoviedb.org/settings/api",
                "📹 视频热点": "⚠️ 未配置 YOUTUBE_API_KEY → https://console.cloud.google.com/apis",
            }
            if self._category in hint_map:
                hint = QLabel(hint_map[self._category])
                hint.setWordWrap(True)
                hint.setStyleSheet(
                    "color:#94A3B8;font-size:12px;background:#FFFBEB;"
                    "border:1px solid #FDE68A;border-radius:8px;padding:10px 14px;")
                self._list_layout.addWidget(hint)
        elif len(items) > 20:
            self.lbl_count.setText(f"20/{len(items)}")
        else:
            self.lbl_count.setText(f"{shown}条")

    def _translate_all(self):
        self.btn_trans_all.setEnabled(False)
        self.btn_trans_all.setText("翻译中…")
        untranslated = [w for w in self._items if not w._translated]
        total = len(untranslated)
        if total == 0:
            self.btn_trans_all.setEnabled(True)
            self.btn_trans_all.setText("全部翻译")
            return

        def _run():
            for idx, w in enumerate(untranslated):
                if w._translated:
                    continue
                result = translate_text(w._item["title"])
                w._trans_done_signal.emit(result)
                self.trans_progress.emit(idx + 1, total)

        threading.Thread(target=_run, daemon=True).start()

    def _on_trans_progress(self, done, total):
        self.btn_trans_all.setText(f"{done}/{total}")
        if done >= total:
            self.btn_trans_all.setEnabled(True)
            self.btn_trans_all.setText("✓ 已翻译")


# ═══════════════ Tab 按钮 ═══════════════
class TabButton(QPushButton):
    ACTIVE_STYLE = (
        "QPushButton{{background:transparent;color:{color};border:none;"
        "border-bottom:3px solid {color};border-radius:0px;"
        "font-size:13px;font-weight:600;padding:8px 20px 5px 20px;}}"
    )
    INACTIVE_STYLE = (
        "QPushButton{{background:transparent;color:#64748B;border:none;"
        "border-bottom:3px solid transparent;border-radius:0px;"
        "font-size:13px;padding:8px 20px 5px 20px;}}"
        "QPushButton:hover{{color:{color};background:{color}06;}}"
    )

    def __init__(self, text, color, parent=None):
        super().__init__(text, parent)
        self._color = color
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self._update_style()

    def set_active(self, active):
        self._active = active
        self.setChecked(active)
        self._update_style()

    def _update_style(self):
        if self._active:
            self.setStyleSheet(self.ACTIVE_STYLE.format(color=self._color))
        else:
            self.setStyleSheet(self.INACTIVE_STYLE.format(color=self._color))


# ═══════════════ Worker ═══════════════
def load_meme_cache():
    """加载本地缓存的 meme 数据（保底）"""
    cache_file = PROJECT / "meme_cache.json"
    if cache_file.exists():
        try:
            with open(cache_file, encoding="utf-8") as f:
                cache = json.load(f)
            return cache.get("memes", [])
        except Exception as e:
            print(f"[MemeCache] load error: {e}")
    return []


def fetch_memes():
    """实时抓取 KYM 最新 meme，失败时降级"""
    items = fetch_meme_fallback()
    if items:
        cache_file = PROJECT / "meme_cache.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"memes": items, "source": "Know Your Meme"}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return items
    reddit = fetch_reddit({"memes": "memes+dankmemes+funny"})
    if reddit:
        return reddit
    return load_meme_cache()


class FetchWorker(QThread):
    progress = pyqtSignal(int, str)
    done_section = pyqtSignal(str, list, str)
    all_done = pyqtSignal()

    def run(self):
        sections = [
            ("🔥 热门Meme", fetch_memes),
            ("🌟 娱乐新闻", lambda: fetch_newsapi() + fetch_rss(categories=["entertainment"])),
            ("🎬 电影资讯", fetch_tmdb),
            ("🏈 体育热点", lambda: fetch_rss(categories=["sports"])),
            ("📹 视频热点", fetch_youtube),
            ("🔍 搜索趋势", lambda: fetch_google_trends(20)),
        ]
        for i, (name, func) in enumerate(sections):
            self.progress.emit(int(i / len(sections) * 100), name)
            try:
                items = func()
            except Exception as e:
                items = []
                print(f"[Worker] {name}: {e}")
            summary = llm_summary(items, name)
            self.done_section.emit(name, items, summary)
        self.all_done.emit()


# ═══════════════ 主窗口 ═══════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("热点雷达")
        self.setMinimumSize(960, 720)
        self.resize(1100, 820)
        self._panels = {}
        self._tabs = {}
        self._tab_order = []
        self._build_ui()
        QTimer.singleShot(500, self.refresh)

    def _build_ui(self):
        # 整体白色背景
        self.setStyleSheet("QMainWindow{background:#FFFFFF;}")
        central = QWidget()
        central.setStyleSheet("background:#FFFFFF;")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(32, 20, 32, 20)
        root.setSpacing(0)

        # ═══ 顶栏 ═══
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 12)

        # Logo + 标题
        logo_area = QHBoxLayout()
        logo_area.setSpacing(10)
        logo_icon = QLabel("📡")
        logo_icon.setStyleSheet("font-size:30px;")
        logo_area.addWidget(logo_icon)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        lbl_title = QLabel("热点雷达")
        lbl_title.setStyleSheet(
            "font-size:22px;font-weight:800;color:#0F172A;letter-spacing:-0.5px;")
        title_col.addWidget(lbl_title)
        lbl_sub = QLabel("海外热点聚合 · 双击标题即可跳转原文")
        lbl_sub.setStyleSheet("color:#94A3B8;font-size:11px;")
        title_col.addWidget(lbl_sub)
        logo_area.addLayout(title_col)
        top.addLayout(logo_area)
        top.addStretch()

        self.btn_refresh = QPushButton("🔄  刷新热点")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet(
            "QPushButton{background:#3B82F6;color:#fff;border:none;border-radius:10px;"
            "font-size:13px;padding:10px 22px;font-weight:600;}"
            "QPushButton:hover{background:#2563EB;}"
            "QPushButton:disabled{background:#CBD5E1;color:#94A3B8;}")
        self.btn_refresh.clicked.connect(self.refresh)
        top.addWidget(self.btn_refresh)
        root.addLayout(top)

        # ═══ 进度条 ═══
        self.progress = QProgressBar()
        self.progress.setFixedHeight(3)
        self.progress.setStyleSheet(
            "QProgressBar{background:#F1F5F9;border:none;border-radius:2px;}"
            "QProgressBar::chunk{background:#3B82F6;border-radius:2px;}")
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)

        # ═══ 状态行 ═══
        bar_row = QHBoxLayout()
        bar_row.setContentsMargins(0, 6, 0, 0)
        self.status = QLabel("就绪")
        self.status.setStyleSheet("color:#94A3B8;font-size:11px;")
        bar_row.addWidget(self.status)
        bar_row.addStretch()
        self.lbl_tip = QLabel("💡 双击任意热点即可打开原文链接")
        self.lbl_tip.setStyleSheet("color:#CBD5E1;font-size:11px;")
        bar_row.addWidget(self.lbl_tip)
        root.addLayout(bar_row)

        # ═══ Tab 导航栏 ═══
        tab_bar = QHBoxLayout()
        tab_bar.setContentsMargins(0, 12, 0, 10)
        tab_bar.setSpacing(10)

        for cat in CAT_KEYS:
            color = CAT_COLORS[cat]
            btn = TabButton(cat, color)
            btn.clicked.connect(lambda *, c=cat: self._switch_tab(c))
            tab_bar.addWidget(btn)
            self._tabs[cat] = btn
            self._tab_order.append(cat)

        tab_bar.addStretch()
        root.addLayout(tab_bar)

        # 分隔线
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:#F1F5F9;")
        root.addWidget(sep)

        # ═══ 内容区（可滚动） ═══
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:vertical{background:transparent;width:6px;margin:0;}"
            "QScrollBar::handle:vertical{background:#CBD5E1;border-radius:3px;min-height:40px;}"
            "QScrollBar::handle:vertical:hover{background:#94A3B8;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0px;}"
            "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:none;}"
        )

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background:transparent;")

        for cat in CAT_KEYS:
            color = CAT_COLORS[cat]
            panel = CategoryPanel(cat, color)
            self._panels[cat] = panel
            self.stack.addWidget(panel)

        scroll.setWidget(self.stack)
        root.addWidget(scroll, 1)

        # 默认选中第一个
        if self._tab_order:
            self._switch_tab(self._tab_order[0])

    def _switch_tab(self, cat):
        for c, btn in self._tabs.items():
            btn.set_active(c == cat)
        idx = self._tab_order.index(cat)
        self.stack.setCurrentIndex(idx)

    def refresh(self):
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("⏳ 获取中…")
        self.progress.setValue(0)
        self._status("正在拉取海外热点数据…")
        for panel in self._panels.values():
            panel.set_items([], "")

        self._worker = FetchWorker()
        self._worker.progress.connect(self._on_progress)
        self._worker.done_section.connect(self._on_section)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _on_progress(self, pct, name):
        self.progress.setValue(pct)
        self._status(f"⏳ 正在获取「{name}」…")

    def _on_section(self, category, items, summary):
        panel = self._panels.get(category)
        if panel:
            panel.set_items(items, summary)

    def _on_all_done(self):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄  刷新热点")
        self.progress.setValue(100)
        self._status("✅ 热点更新完成")
        QTimer.singleShot(3000, lambda: self.progress.setValue(0))

    def _status(self, msg):
        self.status.setText(msg)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
