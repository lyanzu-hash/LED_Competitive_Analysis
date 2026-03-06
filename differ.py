"""
差异检测模块：对比今日爬取数据与昨日快照，输出字段级变化明细。
"""

import logging

logger = logging.getLogger(__name__)

# 需要逐字段对比的维度（与 readme 分析维度对齐）
TRACKED_FIELDS = {
    # SEO 基础
    "title":            "页面标题(Title)",
    "meta_description": "Meta描述",
    "h1":               "H1标题",
    "h2":               "H2标题(前8个)",
    "h3":               "H3标题(前8个)",
    "canonical":        "Canonical URL",
    "hreflang_langs":   "多语言版本(hreflang)",
    # 产品信号
    "price_mentions":   "价格信息",
    "downloads":        "下载文件(Catalog/PDF)",
    "spec_table":       "规格参数表",
    # 营销信号
    "cta_buttons":      "CTA行动按钮",
    "forms":            "表单入口",
    # 信任信号
    "cert_mentions":    "认证证书",
    "expo_mentions":    "展会信息",
    # 内容信号
    "article_titles":   "文章/博客标题",
    "core_keywords":    "核心关键词",
    "long_tail_keywords": "长尾关键词",
    "body_digest":      "页面正文摘要",
    "video_embeds":     "视频嵌入",
    # 结构信号
    "schema_types":     "Schema类型",
    "lang_options":     "语言切换选项",
}


def compute_diff(today_pages: list[dict], yesterday_snapshot: dict | None) -> dict:
    """
    对比今日页面列表与昨日快照，返回差异结构：
    {
        "is_first_run":    bool,
        "has_changes":     bool,
        "new_pages":       [url, ...],
        "removed_pages":   [url, ...],
        "changed_pages":   [{"url": str, "changes": {label: {"old":..,"new":..}}}, ...],
        "unchanged_count": int,
    }
    """
    if yesterday_snapshot is None:
        return {
            "is_first_run":    True,
            "has_changes":     True,
            "new_pages":       [pg["url"] for pg in today_pages],
            "removed_pages":   [],
            "changed_pages":   [],
            "unchanged_count": 0,
        }

    today_map      = {pg["url"]: pg for pg in today_pages}
    yesterday_urls = set(yesterday_snapshot.keys())
    today_urls     = set(today_map.keys())

    new_pages     = sorted(today_urls - yesterday_urls)
    removed_pages = sorted(yesterday_urls - today_urls)
    changed_pages = []
    unchanged     = 0

    for url in today_urls & yesterday_urls:
        today_pg = today_map[url]
        yest_pg  = yesterday_snapshot[url]

        # 用 hash 快速跳过无变化页面
        if (today_pg.get("content_hash")
                and yest_pg.get("hash")
                and today_pg["content_hash"] == yest_pg["hash"]):
            unchanged += 1
            continue

        field_changes = {}
        for field, label in TRACKED_FIELDS.items():
            old_val = yest_pg.get(field, "")
            new_val = today_pg.get(field, "")
            # 列表统一转字符串
            if isinstance(old_val, list):
                old_val = " | ".join(old_val[:8])
            if isinstance(new_val, list):
                new_val = " | ".join(new_val[:8])
            if str(old_val).strip() != str(new_val).strip():
                field_changes[label] = {"old": str(old_val), "new": str(new_val)}

        if field_changes:
            changed_pages.append({"url": url, "changes": field_changes})
        else:
            unchanged += 1

    has_changes = bool(new_pages or removed_pages or changed_pages)
    logger.info(
        f"[差异] 新增页面={len(new_pages)}  "
        f"下线页面={len(removed_pages)}  "
        f"内容变化={len(changed_pages)}  "
        f"无变化={unchanged}"
    )
    return {
        "is_first_run":    False,
        "has_changes":     has_changes,
        "new_pages":       new_pages,
        "removed_pages":   removed_pages,
        "changed_pages":   changed_pages,
        "unchanged_count": unchanged,
    }


def format_diff_for_llm(diff: dict, today_pages: list[dict]) -> str:
    """将 diff 结构格式化为 LLM 可读的文本。"""
    if diff["is_first_run"]:
        return "（首次运行，无历史数据，请基于当前内容进行全量分析）"

    if not diff["has_changes"]:
        return "（今日该竞品网站无任何更新）"

    today_map = {pg["url"]: pg for pg in today_pages}
    parts = []

    if diff["new_pages"]:
        parts.append("【新增页面】")
        for url in diff["new_pages"]:
            pg = today_map.get(url, {})
            lines = [
                f"  + [{pg.get('page_type', '?')}] {url}",
                f"    Title: {pg.get('title', '')}",
                f"    H1: {' | '.join(pg.get('h1', []))}",
                f"    H2: {' | '.join(pg.get('h2', [])[:5])}",
                f"    Meta描述: {pg.get('meta_description', '')}",
            ]
            if pg.get("price_mentions"):
                lines.append(f"    价格: {' / '.join(pg['price_mentions'])}")
            if pg.get("cta_buttons"):
                lines.append(f"    CTA: {' | '.join(pg['cta_buttons'][:3])}")
            if pg.get("cert_mentions"):
                lines.append(f"    认证: {' / '.join(pg['cert_mentions'])}")
            if pg.get("downloads"):
                lines.append(f"    下载: {' | '.join(pg['downloads'][:3])}")
            parts.append("\n".join(lines))

    if diff["removed_pages"]:
        parts.append("\n【删除/下线页面】")
        for url in diff["removed_pages"]:
            parts.append(f"  - {url}")

    if diff["changed_pages"]:
        parts.append("\n【内容变化页面】")
        for item in diff["changed_pages"]:
            parts.append(f"  ~ {item['url']}")
            for field_name, vals in item["changes"].items():
                old = vals["old"][:300] or "（空）"
                new = vals["new"][:300] or "（空）"
                parts.append(f"    [{field_name}]")
                parts.append(f"      旧：{old}")
                parts.append(f"      新：{new}")

    return "\n".join(parts)


def diff_summary_line(name: str, diff: dict) -> str:
    """生成单行摘要，用于日报概览。"""
    if diff["is_first_run"]:
        return f"{name}：首次建立基准快照"
    if not diff["has_changes"]:
        return f"{name}：今日无更新"
    parts = []
    if diff["new_pages"]:
        parts.append(f"新增{len(diff['new_pages'])}个页面")
    if diff["removed_pages"]:
        parts.append(f"下线{len(diff['removed_pages'])}个页面")
    if diff["changed_pages"]:
        parts.append(f"{len(diff['changed_pages'])}个页面内容变化")
    return f"{name}：{'、'.join(parts)}"
