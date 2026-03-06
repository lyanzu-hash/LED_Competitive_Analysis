"""
LLM 分析模块：
- 首次运行 / 有变化：调用大模型分析
- 无变化：跳过，不消耗 token
"""

import logging
from openai import OpenAI

from config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    SYSTEM_PROMPT,
    PAGE_ANALYSIS_PROMPT,
    CHANGE_ANALYSIS_PROMPT,
    DAILY_SUMMARY_PROMPT,
)
from differ import format_diff_for_llm

logger = logging.getLogger(__name__)


def _get_client(timeout: float = 120.0) -> OpenAI:
    if not OPENAI_API_KEY:
        raise ValueError(
            "未配置 OPENAI_API_KEY，请在 .env 文件中设置，或直接设置环境变量。"
        )
    return OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=timeout)


def _stream_completion(client: OpenAI, messages: list, temperature: float = 0.3) -> str:
    """流式调用并拼接返回结果，避免长时间生成导致的连接超时。"""
    chunks = []
    stream = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            chunks.append(delta.content)
    return "".join(chunks).strip()


def analyze_competitor(scrape_result: dict, diff: dict | None = None) -> dict:
    """
    对单个竞品进行 LLM 分析。

    diff 为 None 或 is_first_run=True  → 全量分析（使用 PAGE_ANALYSIS_PROMPT）
    diff.has_changes = True            → 变化分析（使用 CHANGE_ANALYSIS_PROMPT）
    diff.has_changes = False           → 跳过 LLM，直接返回「无更新」

    返回：
    {
        "name":        str,
        "base_url":    str,
        "analysis":    str,
        "has_changes": bool,
        "diff":        dict | None,
        "error":       str | None,
    }
    """
    name     = scrape_result["name"]
    base_url = scrape_result["base_url"]
    pages    = scrape_result.get("pages", [])
    content  = scrape_result.get("combined_text", "")

    # ── 无内容可分析 ───────────────────────────────────────────────────────────
    if not content:
        logger.warning(f"[分析跳过] {name} 无内容")
        return {"name": name, "base_url": base_url, "analysis": "",
                "has_changes": False, "diff": diff, "error": "无爬取内容"}

    # ── 无变化，跳过 LLM ────────────────────────────────────────────────────────
    if diff is not None and not diff.get("is_first_run") and not diff.get("has_changes"):
        logger.info(f"[跳过] {name} 今日无变化，节省 token")
        return {"name": name, "base_url": base_url,
                "analysis": "（今日该竞品官网无任何更新，与昨日一致）",
                "has_changes": False, "diff": diff, "error": None}

    # ── 选择提示词 ─────────────────────────────────────────────────────────────
    is_first_run = (diff is None or diff.get("is_first_run", True))
    if is_first_run:
        prompt = PAGE_ANALYSIS_PROMPT.format(
            page_content=content,
            url=base_url,
            competitor_name=name,
        )
        mode = "全量分析（首次）"
    else:
        diff_text = format_diff_for_llm(diff, pages)
        prompt = CHANGE_ANALYSIS_PROMPT.format(
            diff_text=diff_text,
            competitor_name=name,
        )
        mode = "变化分析"

    logger.info(f"[LLM分析] {name} 发送请求（{mode}，流式）...")
    try:
        client = _get_client(timeout=120.0)
        analysis_text = _stream_completion(
            client,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.3,
        )
        logger.info(f"[LLM分析] {name} 完成，共 {len(analysis_text)} 字")
        return {"name": name, "base_url": base_url, "analysis": analysis_text,
                "has_changes": True, "diff": diff, "error": None}
    except Exception as e:
        logger.error(f"[LLM分析失败] {name}: {e}")
        return {"name": name, "base_url": base_url, "analysis": "",
                "has_changes": False, "diff": diff, "error": str(e)}


def generate_daily_summary(analyses: list[dict]) -> str:
    """
    汇总所有竞品分析，生成《LED显示屏竞品日报》。
    只把有实质内容的分析传给 LLM，节省 token。
    """
    valid = [a for a in analyses if a.get("analysis") and a["analysis"] != "（今日该竞品官网无任何更新，与昨日一致）"]
    if not valid:
        return "（今日所有竞品均无更新，无需生成日报摘要。）"

    parts = []
    for a in analyses:
        label = "【有更新】" if a.get("has_changes") else "【无更新】"
        parts.append(f"### {label} {a['name']} ({a['base_url']})\n\n{a['analysis']}")
    all_analyses_text = "\n\n---\n\n".join(parts)

    if len(all_analyses_text) > 60000:
        all_analyses_text = all_analyses_text[:60000] + "\n\n[...内容过长已截断...]"

    prompt = DAILY_SUMMARY_PROMPT.format(all_analyses=all_analyses_text)

    logger.info("[LLM日报] 生成综合日报（流式）...")
    try:
        client = _get_client(timeout=600.0)
        summary = _stream_completion(
            client,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.4,
        )
        logger.info(f"[LLM日报] 生成完成，共 {len(summary)} 字")
        return summary
    except Exception as e:
        logger.error(f"[LLM日报失败]: {e}")
        return f"（日报生成失败：{e}）"
