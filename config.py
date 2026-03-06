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

请按以下六个维度分类分析今日变化，没有变化的维度写"无变化"：

## 一、产品页面
- 新品上架（型号、参数）：
- 价格调整：
- 库存状态变化：
- 产品描述优化（标题/关键词/卖点）：

## 二、内容页面
- 博客/新闻更新：
- 案例研究新增：
- FAQ更新：

## 三、营销页面
- Landing Page变化（促销活动）：
- 优惠/Coupon更新：
- 免费样品/报价入口变化：

## 四、技术页面
- 新功能上线（在线咨询/计算器/配置器）：
- 下载中心更新（Catalog/Datasheet/Manual）：
- 多语言版本变化：

## 五、信任页面
- 客户/合作伙伴Logo更新：
- 证书/认证新增（ISO/CE/ROHS）：
- 参展信息更新：
- 团队介绍/工厂展示更新：

## 六、SEO维度
- Title/Description变化：
- URL结构调整：
- 新增页面/分类：
- 删除页面/产品：

## 七、综合分析
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

请按以下六个维度全面分析当前网站状态，没有相关内容的维度写"未涉及"：

## 一、产品页面
- 主要产品型号与参数：
- 价格策略：
- 库存/交货状态：
- 产品标题与卖点关键词：

## 二、内容页面
- 博客/新闻内容方向：
- 案例研究类型：
- FAQ涵盖问题：

## 三、营销页面
- 当前促销活动/Landing Page：
- 优惠/Coupon入口：
- 免费样品/报价入口：

## 四、技术页面
- 在线工具（咨询/计算器/配置器）：
- 下载资料（Catalog/Datasheet/Manual）：
- 语言版本：

## 五、信任页面
- 客户/合作伙伴展示：
- 认证证书（ISO/CE/ROHS等）：
- 参展/展会信息：
- 团队/工厂展示：

## 六、SEO维度
- Title/Description关键词：
- URL结构特点：
- 页面/分类体系：
- 内容缺口（明显未覆盖的方向）：

## 七、综合分析
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
