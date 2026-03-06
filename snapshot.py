"""
快照模块：每次运行后保存爬取结果，下次运行时与最近一次快照对比。
快照目录：snapshots/<竞品名>_<日期时间>.json
"""

import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


def _safe_name(name: str) -> str:
    return name.replace("/", "_").replace("\\", "_").replace(" ", "_")


def save_snapshot(name: str, pages: list[dict]) -> dict:
    """
    将本次爬取的 pages 序列化为快照 JSON。
    文件名：<竞品名>_<日期时间>.json，保留最近 30 份，自动清理旧文件。
    """
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    ts       = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"{_safe_name(name)}_{ts}.json"
    path     = SNAPSHOT_DIR / filename

    data = {}
    for pg in pages:
        data[pg["url"]] = {
            # 哈希
            "hash":             pg.get("content_hash", ""),
            # SEO 基础
            "title":            pg.get("title", ""),
            "meta_description": pg.get("meta_description", ""),
            "h1":               pg.get("h1", []),
            "h2":               pg.get("h2", []),
            "h3":               pg.get("h3", []),
            "canonical":        pg.get("canonical", ""),
            "hreflang_langs":   pg.get("hreflang_langs", []),
            # 产品信号
            "price_mentions":   pg.get("price_mentions", []),
            "downloads":        pg.get("downloads", []),
            "spec_table":       pg.get("spec_table", ""),
            # 营销信号
            "cta_buttons":      pg.get("cta_buttons", []),
            "forms":            pg.get("forms", []),
            # 信任信号
            "cert_mentions":    pg.get("cert_mentions", []),
            "expo_mentions":    pg.get("expo_mentions", []),
            # 内容信号
            "article_titles":   pg.get("article_titles", []),
            "video_embeds":     pg.get("video_embeds", []),
            "core_keywords":    pg.get("core_keywords", []),
            "long_tail_keywords": pg.get("long_tail_keywords", []),
            "body_digest":      pg.get("body_digest", ""),
            # 结构信号
            "schema_types":     pg.get("schema_types", []),
            "lang_options":     pg.get("lang_options", []),
            "page_type":        pg.get("page_type", ""),
        }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.debug(f"[快照] {name} 已保存 → {filename}（{len(data)} 个页面）")

    # 保留最近 30 份，清理更早的
    _cleanup_old_snapshots(name, keep=30)
    return data


def load_last_snapshot(name: str) -> dict | None:
    """
    读取该竞品最近一次（本次运行之前）的快照。
    按文件名时间戳降序排列，取第一个（最新）。
    若不存在则返回 None（首次运行）。
    """
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    prefix  = _safe_name(name) + "_"
    files   = sorted(
        [f for f in SNAPSHOT_DIR.glob(f"{prefix}*.json")],
        key=lambda f: f.stem,   # 文件名含时间戳，字典序即时间序
        reverse=True,
    )
    # 跳过正在本轮刚写入的（取第2新，即上一次的）
    # save_snapshot 在 load_last_snapshot 之后调用，所以这里 files[0] 就是上次的
    if not files:
        logger.info(f"[快照] {name} 无历史快照，将进行首次全量分析")
        return None
    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
        logger.info(f"[快照] {name} 加载上次快照：{files[0].name}（{len(data)} 页）")
        return data
    except Exception as e:
        logger.warning(f"[快照] {name} 读取快照失败：{e}")
        return None


def _cleanup_old_snapshots(name: str, keep: int = 30):
    """保留最新 keep 份，删除更早的快照文件。"""
    prefix = _safe_name(name) + "_"
    files  = sorted(
        [f for f in SNAPSHOT_DIR.glob(f"{prefix}*.json")],
        key=lambda f: f.stem,
        reverse=True,
    )
    for old in files[keep:]:
        try:
            old.unlink()
        except Exception:
            pass
