import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM API 配置 ──────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ── 竞品网站列表 ───────────────────────────────────────────────────────────────
COMPETITORS = [
    {"name": "EagerLED",       "url": "https://www.eagerled.com/"},
    {"name": "Kinglight",      "url": "https://en.kinglight.com/"},
    {"name": "ColorlitLED",    "url": "https://www.colorlitled.com/"},
    {"name": "DoitVision",     "url": "https://www.doitvision.com/"},
    {"name": "LEDScreenFactory","url": "https://ledscreenfactory.com/"},
    {"name": "TopDanceLED",    "url": "https://topdanceled.com/"},
    {"name": "SZLEDWorld",     "url": "https://szledworld.com/"},
    {"name": "BibLED",         "url": "https://www.bibiled.com/"},
    {"name": "MileStrong",     "url": "https://www.mile-strong.com/"},
    {"name": "SZJYLED",        "url": "https://www.szjy-led.com/"},
]

# ── 爬取配置 ───────────────────────────────────────────────────────────────────
REQUEST_TIMEOUT = 20          # 单次请求超时（秒）
REQUEST_DELAY   = 1.5         # 每次请求间隔（秒），避免被封
MAX_PAGES_PER_SITE = 9        # 每个站点最多爬取页面数（首页 + sitemap子页）
MAX_CONTENT_CHARS = 8000      # 单页传给 LLM 的最大字符数（避免超出 token 限制）

# ── 输出配置 ───────────────────────────────────────────────────────────────────
OUTPUT_DIR = "output"         # Excel 日报输出目录

# ── LLM 提示词 ─────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = "你是LED显示屏行业资深SEO与竞品分析师。请用中文输出分析结果。"

CHANGE_ANALYSIS_PROMPT = """\
你是LED显示屏行业资深SEO与竞品分析师。
以下是竞品【{competitor_name}】官网今日检测到的变化内容：

{diff_text}

请输出结构化结果，必须包含以下部分：

一、今日更新清单（仅列出有变化项）
1. 博客页面关键词变动：
2. 页面内容更新（正文/文案）：
3. 标题更新（Title）：
4. H1/H2更新：
5. 产品信息更新：
6. 视频标题更新：

二、页面基本信息
1. 页面类型：首页/产品页/案例页/新闻页/解决方案页
2. 页面标题（Title）：
3. 页面H1和H2：
4. 核心关键词：
5. 主要长尾词：

三、页面内容分析
1. 内容主题：
2. 主推产品：
3. 产品卖点：
4. 文案风格：

四、SEO优缺点
优点：
缺点：

五、可超越机会点（我们能做的）
1. 关键词空白：
2. 内容空白：
3. 结构优化点：
4. 文案差异化方向：

六、综合分析
1. 竞品在主推什么产品？（室内/户外/租赁/小间距/GOB/COB）
2. 他们重点布局哪些关键词？
3. 内容风格是什么？（工厂/品质/案例/价格）
4. SEO优缺点是什么？
5. 我们可以超越的机会点：
   - 哪些关键词有空隙：
   - 哪些内容他们没写：
   - 哪些内容我们可以补充：
   - 哪些视频主题我们能做：
"""

PAGE_ANALYSIS_PROMPT = """\
你是LED显示屏行业资深SEO与竞品分析师。
以下是竞品【{competitor_name}】官网当前内容（首次建立基准快照）：

{page_content}

页面URL：{url}

请输出结构化结果，必须包含以下部分：

一、页面基本信息
1. 页面类型：首页/产品页/案例页/新闻页/解决方案页
2. 页面标题（Title）：
3. 页面H1和H2：
4. 核心关键词：
5. 主要长尾词：

二、页面内容分析
1. 内容主题：
2. 主推产品：
3. 产品卖点：
4. 文案风格：

三、SEO优缺点
优点：
缺点：

四、可超越机会点（我们能做的）
1. 关键词空白：
2. 内容空白：
3. 结构优化点：
4. 文案差异化方向：

五、综合分析
1. 竞品在主推什么产品？（室内/户外/租赁/小间距/GOB/COB）
2. 他们重点布局哪些关键词？
3. 内容风格是什么？（工厂/品质/案例/价格）
4. SEO优缺点是什么？
5. 我们可以超越的机会点：
   - 哪些关键词有空隙：
   - 哪些内容他们没写：
   - 哪些内容我们可以补充：
   - 哪些视频主题我们能做：
"""

DAILY_SUMMARY_PROMPT = """\
你是LED显示屏行业资深SEO与竞品分析师。
以下是今日所有竞品的分析结果：

{all_analyses}

请综合输出一份简洁的《LED显示屏竞品日报》：

## 今日变化速览
（有变化的竞品各用1-2句话点明核心动作；无变化的归为一行带过）

## 竞品综合分析
1. 竞品在主推什么产品？（室内/户外/租赁/小间距/GOB/COB）
2. 他们重点布局哪些关键词？
3. 内容风格是什么？（工厂/品质/案例/价格）
4. SEO优缺点是什么？
5. 我们可以超越的机会点：
   - 哪些关键词有空隙：
   - 哪些内容他们没写：
   - 哪些内容我们可以补充：
   - 哪些视频主题我们能做：

## 下周内容计划
- 推荐文章标题（10个）：
- 推荐关键词（3个）：
"""
