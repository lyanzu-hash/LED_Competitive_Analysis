"""
网页爬虫模块：抓取竞品官网页面内容
提取维度：
  SEO基础     - Title / Meta Description / H1~H3 / Canonical / hreflang
  内容信号    - 正文节选 / 文章标题列表 / 页面类型
  产品信号    - 价格文本 / 规格参数表 / 图片 Alt 文本
  营销信号    - CTA 按钮文本 / 表单入口 / 优惠关键词
  技术信号    - PDF/Catalog 下载链接 / 视频嵌入标题 / 多语言选项
  信任信号    - 认证证书关键词 / 展会信息
  结构信号    - Open Graph 标签 / Schema.org 类型 / 导航链接
"""

import hashlib
import json
import logging
import re
import time
from collections import Counter
from html import unescape
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.exceptions import ProxyError

from config import REQUEST_TIMEOUT, REQUEST_DELAY, MAX_PAGES_PER_SITE, MAX_CONTENT_CHARS

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}

# 价格相关正则（$99 / USD 99 / ¥99 / 99USD 等）
_PRICE_RE = re.compile(
    r"(?:USD?|CNY|EUR|GBP|¥|\$|€)\s*[\d,]+(?:\.\d+)?"
    r"|[\d,]+(?:\.\d+)?\s*(?:USD?|CNY|EUR)",
    re.IGNORECASE,
)

# 认证证书关键词
_CERT_KWS = [
    "ISO", "CE", "ROHS", "RoHS", "FCC", "UL", "ETL", "SAA",
    "EN62368", "IEC", "TÜV", "TUV", "certif", "certificat",
]

# 展会/参展关键词
_EXPO_KWS = [
    "ISE", "InfoComm", "LED Expo", "CES", "NAB", "Prolight",
    "exhib", "trade show", "booth", "fair", "expo",
]

# PDF/下载文件扩展名
_DL_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar"}
_STATIC_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg", ".ico",
    ".css", ".js", ".map", ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".webm", ".mp3", ".wav", ".avi", ".mov",
    ".xml", ".json", ".txt",
}

_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "your", "you", "our", "are",
    "was", "were", "have", "has", "had", "not", "but", "can", "will", "all", "new",
    "led", "display", "screen", "video", "panel", "china", "factory", "manufacturer",
    "solution", "solutions", "about", "news", "blog", "article", "case", "project",
    "home", "page", "more", "contact", "quote", "request", "download", "product", "products",
}


def _normalize_url(raw_url: str, base_url: str) -> str:
    """规范化 URL：解码实体、补全绝对地址、去锚点。"""
    href = unescape((raw_url or "").strip())
    if not href:
        return ""
    if href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return ""
    full = urljoin(base_url, href)
    full, _ = urldefrag(full)
    return full


def _is_probably_html_url(url: str) -> bool:
    """
    判断 URL 是否像“HTML 页面”而不是静态资源。
    目标：避免把图片/CDN资源/XML文件当页面抓取。
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    path = parsed.path.lower()
    if "/_ipx/" in path:
        return False
    tail = path.rsplit("/", 1)[-1]
    if "." in tail:
        ext = "." + tail.rsplit(".", 1)[-1]
        if ext in _STATIC_EXTS:
            return False
    return True


def _fetch_html(url: str) -> str | None:
    def _do_get(use_proxy: bool):
        kwargs = {
            "headers": HEADERS,
            "timeout": REQUEST_TIMEOUT,
        }
        # 当本机代理（如 127.0.0.1:7892）失效时，改为直连
        if not use_proxy:
            kwargs["proxies"] = {"http": "", "https": ""}
        return requests.get(url, **kwargs)

    try:
        if not _is_probably_html_url(url):
            return None
        try:
            resp = _do_get(use_proxy=True)
        except ProxyError:
            logger.warning(f"[代理不可用，改为直连] {url}")
            resp = _do_get(use_proxy=False)
        resp.raise_for_status()
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "text/html" not in ctype and "application/xhtml+xml" not in ctype:
            logger.info(f"[跳过非HTML] {url}  Content-Type: {ctype or 'unknown'}")
            return None
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except Exception as e:
        logger.warning(f"[爬取失败] {url}  原因: {e}")
        return None


# ── 各类信号提取函数 ─────────────────────────────────────────────────────────

def _extract_og(soup: BeautifulSoup) -> dict:
    """Open Graph 标签。"""
    og = {}
    for tag in soup.find_all("meta", property=lambda p: p and p.startswith("og:")):
        key = tag.get("property", "")[3:]
        og[key] = tag.get("content", "")
    return {
        "og_title":       og.get("title", ""),
        "og_description": og.get("description", ""),
        "og_type":        og.get("type", ""),
        "og_image":       og.get("image", ""),
    }


def _extract_canonical_hreflang(soup: BeautifulSoup) -> dict:
    """Canonical URL 和 hreflang（多语言版本）。"""
    canonical = ""
    tag = soup.find("link", rel="canonical")
    if tag:
        canonical = tag.get("href", "")

    langs = []
    for tag in soup.find_all("link", rel="alternate"):
        hl = tag.get("hreflang", "")
        if hl:
            langs.append(hl)

    return {"canonical": canonical, "hreflang_langs": langs}


def _extract_schema_types(soup: BeautifulSoup) -> list[str]:
    """从 JSON-LD 提取 Schema.org @type 列表。"""
    types = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, dict):
                t = data.get("@type")
                if t:
                    types.append(t if isinstance(t, str) else str(t))
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type"):
                        types.append(str(item["@type"]))
        except Exception:
            pass
    return list(set(types))


def _extract_price_mentions(soup: BeautifulSoup) -> list[str]:
    """提取页面中出现的价格文本（去重，最多 10 条）。"""
    text = soup.get_text(" ", strip=True)
    found = list({m.group() for m in _PRICE_RE.finditer(text)})
    return found[:10]


def _extract_spec_table(soup: BeautifulSoup) -> str:
    """提取规格参数表格文本（table/dl）。"""
    parts = []
    for table in soup.find_all("table")[:3]:
        rows = []
        for tr in table.find_all("tr")[:10]:
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            parts.append("\n".join(rows))
    for dl in soup.find_all("dl")[:2]:
        items = []
        for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
            items.append(f"{dt.get_text(strip=True)}: {dd.get_text(strip=True)}")
        if items:
            parts.append("\n".join(items))
    return "\n\n".join(parts)[:1500]


def _extract_img_alts(soup: BeautifulSoup) -> list[str]:
    """提取图片 alt 文本（过滤空值和纯数字，最多 20 条）。"""
    alts = []
    for img in soup.find_all("img", alt=True):
        alt = img["alt"].strip()
        if alt and not alt.isdigit() and len(alt) > 2:
            alts.append(alt)
    return list(dict.fromkeys(alts))[:20]  # 去重保序


def _extract_video_embeds(soup: BeautifulSoup) -> list[str]:
    """提取视频嵌入标题（YouTube/Vimeo iframe title 或 src 中的 video id）。"""
    videos = []
    for iframe in soup.find_all("iframe"):
        src   = iframe.get("src", "")
        title = iframe.get("title", "")
        if "youtube" in src or "vimeo" in src or "video" in src.lower():
            label = title or src
            if label:
                videos.append(label[:120])
    return videos[:10]


def _extract_downloads(soup: BeautifulSoup, base_url: str) -> list[str]:
    """提取可下载文件链接（PDF / Catalog / Datasheet 等）。"""
    found = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        ext  = "." + href.rsplit(".", 1)[-1].lower() if "." in href else ""
        text = a.get_text(strip=True)
        is_dl_ext  = ext in _DL_EXTS
        is_dl_text = any(kw in text.lower() for kw in
                         ["catalog", "datasheet", "manual", "brochure", "download", "pdf"])
        if is_dl_ext or is_dl_text:
            full = urljoin(base_url, href)
            found.append(f"{text} → {full}" if text else full)
    return list(dict.fromkeys(found))[:15]


def _extract_forms(soup: BeautifulSoup) -> list[str]:
    """提取表单入口（提交按钮文字 / form action）。"""
    found = []
    for form in soup.find_all("form"):
        btns = form.find_all(["button", "input"], type=lambda t: t in ("submit", None))
        for btn in btns:
            txt = btn.get("value", "") or btn.get_text(strip=True)
            if txt and len(txt) > 1:
                found.append(txt)
    return list(dict.fromkeys(found))[:10]


def _extract_cta_buttons(soup: BeautifulSoup) -> list[str]:
    """提取 CTA 按钮文本（a/button 标签中的行动词）。"""
    cta_kws = ["get quote", "free sample", "contact", "inquiry", "request",
               "buy", "order", "price", "demo", "download", "try", "start"]
    found = []
    for tag in soup.find_all(["a", "button"]):
        txt = tag.get_text(strip=True).lower()
        if any(kw in txt for kw in cta_kws) and 2 < len(txt) < 60:
            found.append(tag.get_text(strip=True))
    return list(dict.fromkeys(found))[:10]


def _extract_lang_options(soup: BeautifulSoup) -> list[str]:
    """提取多语言选项（select option / 语言切换链接文本）。"""
    langs = []
    lang_kws = ["english", "chinese", "español", "deutsch", "français",
                "arabic", "русский", "português", "日本語", "한국어"]
    for opt in soup.find_all("option"):
        txt = opt.get_text(strip=True).lower()
        if any(kw in txt for kw in lang_kws) or len(txt) in (2, 5):
            langs.append(opt.get_text(strip=True))
    return list(dict.fromkeys(langs))[:8]


def _extract_cert_expo(text: str) -> dict:
    """在正文中扫描认证和展会关键词。"""
    text_lower = text.lower()
    certs = [kw for kw in _CERT_KWS if kw.lower() in text_lower]
    expos = [kw for kw in _EXPO_KWS if kw.lower() in text_lower]
    return {
        "cert_mentions": list(dict.fromkeys(certs))[:10],
        "expo_mentions": list(dict.fromkeys(expos))[:10],
    }


def _extract_article_titles(soup: BeautifulSoup) -> list[str]:
    """提取博客/新闻文章标题（article / .post / h2+time 组合）。"""
    titles = []
    for article in soup.find_all(["article", "li"], limit=20):
        hx = article.find(["h2", "h3", "h4"])
        if hx:
            txt = hx.get_text(strip=True)
            if txt and 5 < len(txt) < 120:
                titles.append(txt)
    return list(dict.fromkeys(titles))[:15]


def _extract_keywords(meta_kw: str, title: str, h1_list: list[str], h2_list: list[str],
                      article_titles: list[str], body_text: str) -> tuple[list[str], list[str]]:
    """
    提取页面核心关键词与长尾词（启发式）：
    - 核心词：来自 meta keywords + 标题/标题词频
    - 长尾词：来自标题/H2/文章标题中的 2~6 词短语
    """
    seed = " ".join([title, " ".join(h1_list), " ".join(h2_list), " ".join(article_titles)])
    body = body_text[:3000]

    # 1) 核心词：优先 meta keywords
    core_terms: list[str] = []
    if meta_kw:
        raw = re.split(r"[,，;；|/]", meta_kw)
        core_terms.extend([t.strip() for t in raw if t.strip()])

    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", f"{seed} {body}".lower())
    freq = Counter(t for t in tokens if t not in _STOPWORDS and len(t) <= 32)
    for term, _ in freq.most_common(20):
        if term not in core_terms:
            core_terms.append(term)

    # 2) 长尾词：从标题类文本抓 2~6 词短语
    phrase_src = [title] + h1_list + h2_list + article_titles
    long_tail: list[str] = []
    for src in phrase_src:
        clean = re.sub(r"\s+", " ", src.strip())
        if not clean:
            continue
        words = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{1,}", clean)
        if len(words) >= 2:
            phrase = " ".join(words[: min(6, len(words))]).lower()
            if phrase not in long_tail and 8 <= len(phrase) <= 80:
                long_tail.append(phrase)

    return core_terms[:12], long_tail[:12]


def _detect_page_type(url: str, title: str, h1_list: list) -> str:
    """根据 URL 和标题推断页面类型。"""
    u = url.lower()
    t = (title + " ".join(h1_list)).lower()
    if any(kw in u for kw in ["blog", "news", "article", "post"]):
        return "博客/新闻"
    if any(kw in u for kw in ["case", "project", "portfolio", "client"]):
        return "案例页"
    if any(kw in u for kw in ["product", "led-display", "led-screen", "indoor", "outdoor"]):
        return "产品页"
    if any(kw in u for kw in ["solution", "application", "industry"]):
        return "解决方案页"
    if any(kw in u for kw in ["about", "company", "factory", "team"]):
        return "关于页"
    if any(kw in u for kw in ["contact", "inquiry", "quote", "support"]):
        return "询盘/联系页"
    if any(kw in u for kw in ["download", "catalog", "resource"]):
        return "下载页"
    if any(kw in u for kw in ["faq", "help", "support"]):
        return "FAQ页"
    if u.rstrip("/").count("/") <= 3:
        return "首页"
    return "其他"


# ── sitemap 发现页面 ──────────────────────────────────────────────────────────

def _fetch_sitemap_urls(base_url: str, max_urls: int = 30) -> list[str]:
    """
    尝试读取 sitemap.xml，提取同域 URL。
    优先含 product/blog/case/news 的 URL。
    """
    sitemap_candidates = [
        urljoin(base_url, "/sitemap.xml"),
        urljoin(base_url, "/sitemap_index.xml"),
        urljoin(base_url, "/sitemap-index.xml"),
    ]
    domain = urlparse(base_url).netloc
    urls: list[str] = []

    def _collect_urls_from_sitemap(xml_text: str) -> list[str]:
        soup = BeautifulSoup(xml_text, "lxml-xml")
        return [tag.get_text(strip=True) for tag in soup.find_all("loc")]

    def _get(url: str, timeout: int = 10):
        try:
            return requests.get(url, headers=HEADERS, timeout=timeout)
        except ProxyError:
            logger.warning(f"[代理不可用，sitemap 直连重试] {url}")
            return requests.get(
                url, headers=HEADERS, timeout=timeout,
                proxies={"http": "", "https": ""},
            )

    for sm_url in sitemap_candidates:
        try:
            resp = _get(sm_url, timeout=10)
            if resp.status_code != 200:
                continue
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "xml" not in ctype and "text/plain" not in ctype and "text/xml" not in ctype:
                continue

            locs = _collect_urls_from_sitemap(resp.text)
            if not locs:
                continue

            # sitemap_index 里经常是子 sitemap.xml，进一步展开一层
            if all(urlparse(u).path.lower().endswith(".xml") for u in locs[: min(5, len(locs))]):
                expanded = []
                for child in locs[:8]:
                    try:
                        r2 = _get(child, timeout=10)
                        if r2.status_code == 200:
                            expanded.extend(_collect_urls_from_sitemap(r2.text))
                    except Exception:
                        pass
                locs = expanded or locs

            normalized = [_normalize_url(u, base_url) for u in locs]
            same_domain = [
                u for u in normalized
                if u and urlparse(u).netloc == domain and _is_probably_html_url(u)
            ]
            if same_domain:
                logger.info(f"[sitemap] {base_url} 发现 {len(same_domain)} 个 URL")
                urls = same_domain
                break
        except Exception:
            pass

    if not urls:
        return []

    priority_kws = ["product", "blog", "news", "case", "solution", "application",
                    "indoor", "outdoor", "rental", "faq", "catalog", "about"]
    priority = [u for u in urls if any(kw in u.lower() for kw in priority_kws)]
    others   = [u for u in urls if u not in set(priority)]
    return (priority + others)[:max_urls]


# ── 单页面解析 ────────────────────────────────────────────────────────────────

def _parse_page(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    # 移除无用标签（保留 main/article 内容）
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    # ── SEO 基础 ──────────────────────────────────────────────────────────────
    title     = soup.title.get_text(strip=True) if soup.title else ""
    h1_list   = [h.get_text(strip=True) for h in soup.find_all("h1") if h.get_text(strip=True)]
    h2_list   = [h.get_text(strip=True) for h in soup.find_all("h2") if h.get_text(strip=True)]
    h3_list   = [h.get_text(strip=True) for h in soup.find_all("h3") if h.get_text(strip=True)]
    meta_desc = ""
    meta_kw   = ""
    if soup.find("meta", attrs={"name": "description"}):
        meta_desc = soup.find("meta", attrs={"name": "description"}).get("content", "")
    if soup.find("meta", attrs={"name": "keywords"}):
        meta_kw   = soup.find("meta", attrs={"name": "keywords"}).get("content", "")

    # ── 正文 ──────────────────────────────────────────────────────────────────
    for tag in soup(["footer", "header", "nav"]):
        tag.decompose()
    body_text = soup.get_text(separator="\n", strip=True)
    body_text = "\n".join(l for l in body_text.splitlines() if l.strip())
    body_text = body_text[:MAX_CONTENT_CHARS]

    # ── 导航链接 ──────────────────────────────────────────────────────────────
    nav_links = []
    for a in soup.find_all("a", href=True):
        full = _normalize_url(a["href"], url)
        if full and _is_probably_html_url(full):
            nav_links.append(full)

    # ── 新增扩展字段 ──────────────────────────────────────────────────────────
    og          = _extract_og(soup)
    cl          = _extract_canonical_hreflang(soup)
    schema_types= _extract_schema_types(soup)
    price_mts   = _extract_price_mentions(soup)
    spec_table  = _extract_spec_table(soup)
    img_alts    = _extract_img_alts(soup)
    videos      = _extract_video_embeds(soup)
    downloads   = _extract_downloads(soup, url)
    forms       = _extract_forms(soup)
    cta_btns    = _extract_cta_buttons(soup)
    lang_opts   = _extract_lang_options(soup)
    cert_expo   = _extract_cert_expo(body_text)
    art_titles  = _extract_article_titles(soup)
    page_type   = _detect_page_type(url, title, h1_list)
    core_kws, long_tail_kws = _extract_keywords(meta_kw, title, h1_list, h2_list, art_titles, body_text)
    body_digest = re.sub(r"\s+", " ", body_text)[:1200]

    # ── 内容哈希（含扩展字段）────────────────────────────────────────────────
    hash_src = (
        title
        + "|".join(h1_list)
        + "|".join(h2_list[:8])
        + "|".join(h3_list[:8])
        + meta_desc
        + "|".join(price_mts)
        + "|".join(downloads[:5])
        + body_text[:3000]
    )
    content_hash = hashlib.md5(hash_src.encode("utf-8", errors="ignore")).hexdigest()

    return {
        # SEO 基础
        "url":              url,
        "page_type":        page_type,
        "title":            title,
        "meta_description": meta_desc,
        "meta_keywords":    meta_kw,
        "h1":               h1_list,
        "h2":               h2_list,
        "h3":               h3_list,
        # OG / Schema
        "og_title":         og["og_title"],
        "og_description":   og["og_description"],
        "og_type":          og["og_type"],
        "canonical":        cl["canonical"],
        "hreflang_langs":   cl["hreflang_langs"],
        "schema_types":     schema_types,
        # 产品信号
        "price_mentions":   price_mts,
        "spec_table":       spec_table,
        "img_alts":         img_alts,
        # 营销信号
        "cta_buttons":      cta_btns,
        "forms":            forms,
        # 技术信号
        "downloads":        downloads,
        "video_embeds":     videos,
        "lang_options":     lang_opts,
        # 信任信号
        "cert_mentions":    cert_expo["cert_mentions"],
        "expo_mentions":    cert_expo["expo_mentions"],
        # 内容信号
        "article_titles":   art_titles,
        "core_keywords":    core_kws,
        "long_tail_keywords": long_tail_kws,
        "body_text":        body_text,
        "body_digest":      body_digest,
        # 结构
        "nav_links":        nav_links,
        "content_hash":     content_hash,
    }


# ── 子页面筛选 ────────────────────────────────────────────────────────────────

def _pick_sub_urls(base_url: str, nav_links: list[str],
                   sitemap_urls: list[str], max_pages: int) -> list[str]:
    """
    合并 sitemap + 导航链接，按优先级筛选同域子页面。
    """
    base_domain   = urlparse(base_url).netloc
    priority_kws  = ["product", "solution", "case", "blog", "news",
                     "indoor", "outdoor", "rental", "gob", "cob",
                     "application", "download", "catalog", "faq"]
    seen          = {base_url}
    priority: list[str] = []
    others:   list[str] = []

    all_links = sitemap_urls + nav_links

    for link in all_links:
        clean_link = _normalize_url(link, base_url)
        if not clean_link:
            continue
        if urlparse(clean_link).netloc != base_domain:
            continue
        if not _is_probably_html_url(clean_link):
            continue
        if clean_link in seen:
            continue
        seen.add(clean_link)
        if any(kw in clean_link.lower() for kw in priority_kws):
            priority.append(clean_link)
        else:
            others.append(clean_link)

    return (priority + others)[: max_pages - 1]


# ── 主入口 ────────────────────────────────────────────────────────────────────

def scrape_competitor(competitor: dict) -> dict:
    """
    爬取单个竞品网站（首页 + sitemap + 优选子页，最多 MAX_PAGES_PER_SITE 页）。
    """
    name     = competitor["name"]
    base_url = competitor["url"]
    logger.info(f"[开始爬取] {name}  {base_url}")

    pages: list[dict] = []

    # ── 首页 ──────────────────────────────────────────────────────────────────
    html = _fetch_html(base_url)
    if html is None:
        logger.error(f"[跳过] {name} 首页无法访问")
        return {"name": name, "base_url": base_url, "pages": [], "combined_text": ""}

    home_page = _parse_page(html, base_url)
    pages.append(home_page)
    time.sleep(REQUEST_DELAY)

    # ── 尝试 sitemap 发现更多页面 ─────────────────────────────────────────────
    sitemap_urls = _fetch_sitemap_urls(base_url, max_urls=50)
    time.sleep(REQUEST_DELAY)

    # ── 子页面 ────────────────────────────────────────────────────────────────
    sub_urls = _pick_sub_urls(
        base_url, home_page["nav_links"],
        sitemap_urls, MAX_PAGES_PER_SITE,
    )
    for sub_url in sub_urls:
        logger.info(f"  ↳ {sub_url}")
        sub_html = _fetch_html(sub_url)
        if sub_html:
            pages.append(_parse_page(sub_html, sub_url))
        time.sleep(REQUEST_DELAY)

    # ── 合并文本供 LLM 分析 ───────────────────────────────────────────────────
    parts = []
    for pg in pages:
        section = [
            f"--- [{pg['page_type']}] {pg['url']} ---",
            f"Title: {pg['title']}",
            f"Meta: {pg['meta_description']}",
            f"H1: {' | '.join(pg['h1'])}",
            f"H2: {' | '.join(pg['h2'][:8])}",
        ]
        if pg["price_mentions"]:
            section.append(f"价格信息: {' / '.join(pg['price_mentions'])}")
        if pg["downloads"]:
            section.append(f"下载文件: {' | '.join(pg['downloads'][:5])}")
        if pg["video_embeds"]:
            section.append(f"视频: {' | '.join(pg['video_embeds'][:3])}")
        if pg["cta_buttons"]:
            section.append(f"CTA按钮: {' | '.join(pg['cta_buttons'][:5])}")
        if pg["cert_mentions"]:
            section.append(f"认证: {' / '.join(pg['cert_mentions'])}")
        if pg["expo_mentions"]:
            section.append(f"展会: {' / '.join(pg['expo_mentions'])}")
        if pg["article_titles"]:
            section.append(f"文章标题: {' | '.join(pg['article_titles'][:5])}")
        if pg["core_keywords"]:
            section.append(f"核心关键词: {' | '.join(pg['core_keywords'][:8])}")
        if pg["long_tail_keywords"]:
            section.append(f"长尾词: {' | '.join(pg['long_tail_keywords'][:8])}")
        if pg["lang_options"]:
            section.append(f"语言版本: {' / '.join(pg['lang_options'])}")
        if pg["spec_table"]:
            section.append(f"规格参数:\n{pg['spec_table'][:500]}")
        section.append(f"正文节选:\n{pg['body_text'][:1500]}")
        parts.append("\n".join(section))

    combined = "\n\n".join(parts)
    combined = combined[:MAX_CONTENT_CHARS * MAX_PAGES_PER_SITE]

    logger.info(f"[完成] {name}  共爬取 {len(pages)} 个页面")
    return {
        "name":          name,
        "base_url":      base_url,
        "pages":         pages,
        "combined_text": combined,
    }
