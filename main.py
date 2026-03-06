"""
LED显示屏竞品日报生成器 - 主入口
流程：爬取 → 快照对比 → 差异驱动LLM分析 → 保存快照 → 生成Excel日报
"""

import logging
import sys
import os
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import COMPETITORS, OPENAI_API_KEY
from scraper import scrape_competitor
from snapshot import save_snapshot, load_last_snapshot
from differ import compute_diff, diff_summary_line
from analyzer import analyze_competitor, generate_daily_summary
from reporter import save_report

# 日志由调用方（run_daily.py 或 app.py）通过 log_setup 统一配置
logger = logging.getLogger(__name__)


def check_env():
    if not OPENAI_API_KEY:
        logger.error(
            "❌ 未找到 OPENAI_API_KEY！\n"
            "   请在项目根目录创建 .env 文件，写入：\n"
            "   OPENAI_API_KEY=sk-xxxxxxxxxxxx"
        )
        sys.exit(1)


def run_pipeline(
    competitors: list[dict] | None = None,
    max_workers: int = 3,
    skip_scrape: bool = False,
    force_full: bool = False,
) -> str:
    """
    执行完整工作流，返回生成的 Excel 文件路径。

    参数：
      competitors  - 若为 None 则使用 config.py 中的完整列表
      max_workers  - 并发爬取线程数
      skip_scrape  - True 时跳过爬取（调试用）
      force_full   - True 时强制全量分析，忽略昨日快照
    """
    targets  = competitors or COMPETITORS
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    logger.info("═" * 45)
    logger.info(f"  LED竞品日报  {date_str}")
    logger.info(f"  目标网站: {len(targets)} 个  |  模式: {'强制全量' if force_full else '差异监控'}")
    logger.info("═" * 45)

    # ── Step 1: 并发爬取 ────────────────────────────────────────────────────────
    scrape_results = []
    if skip_scrape:
        logger.warning("[DEBUG] skip_scrape=True，跳过爬取")
        scrape_results = [
            {"name": c["name"], "base_url": c["url"], "pages": [], "combined_text": "（调试模式）"}
            for c in targets
        ]
    else:
        logger.info(f"\n[Step 1/4] 开始爬取 {len(targets)} 个竞品网站 ...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(scrape_competitor, c): c for c in targets}
            for future in as_completed(future_map):
                result = future.result()
                scrape_results.append(result)
                pages_count = len(result.get("pages", []))
                logger.info(f"  ✓ {result['name']}  ({pages_count} 页)")

    # ── Step 2: 快照对比，计算差异 ─────────────────────────────────────────────
    logger.info(f"\n[Step 2/4] 与昨日快照对比，检测更新 ...")
    diffs = {}
    changed_count = 0

    for result in scrape_results:
        name  = result["name"]
        pages = result.get("pages", [])

        if force_full or not pages:
            diff = None  # 强制全量 或 无数据 → 不使用快照
        else:
            yesterday = load_last_snapshot(name)
            diff = compute_diff(pages, yesterday)

        diffs[name] = diff
        line = diff_summary_line(name, diff) if diff else f"{name}：全量分析模式"
        logger.info(f"  {line}")
        if diff and diff.get("has_changes"):
            changed_count += 1

    logger.info(f"  → 今日有变化竞品: {changed_count} / {len(scrape_results)}")

    # ── Step 3: 保存今日快照 ────────────────────────────────────────────────────
    logger.info(f"\n[Step 3/4] 保存今日快照 ...")
    for result in scrape_results:
        if result.get("pages"):
            save_snapshot(result["name"], result["pages"])
            logger.info(f"  ✓ {result['name']} 快照已保存")

    # ── Step 4: LLM 分析（只分析有变化的竞品）─────────────────────────────────
    logger.info(f"\n[Step 4/4] 调用大模型分析 ...")
    analyses = []
    for result in scrape_results:
        diff = diffs.get(result["name"])
        analysis = analyze_competitor(result, diff=diff)
        analyses.append(analysis)
        if analysis.get("has_changes"):
            logger.info(f"  ✅ {result['name']}（已分析）")
        else:
            logger.info(f"  ⏭  {result['name']}（无变化，跳过）")

    # ── Step 5: 生成综合日报 ─────────────────────────────────────────────────
    logger.info(f"\n[生成日报] 调用大模型生成综合日报 ...")
    summary = generate_daily_summary(analyses)

    # ── 写入 Excel ──────────────────────────────────────────────────────────────
    filepath = save_report(scrape_results, analyses, summary, diffs)

    logger.info(f"\n{'═' * 45}")
    logger.info(f"  ✅ 日报已生成：{os.path.abspath(filepath)}")
    logger.info(f"{'═' * 45}\n")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="LED显示屏竞品日报生成器")
    parser.add_argument("--sites", nargs="+", metavar="NAME",
                        help="只爬取指定竞品名称，如：--sites EagerLED Kinglight")
    parser.add_argument("--workers", type=int, default=3,
                        help="并发爬取线程数（默认 3）")
    parser.add_argument("--skip-scrape", action="store_true",
                        help="跳过爬取（调试用）")
    parser.add_argument("--full", action="store_true",
                        help="强制全量分析，忽略昨日快照")
    args = parser.parse_args()

    check_env()

    targets = None
    if args.sites:
        name_set = {s.lower() for s in args.sites}
        targets  = [c for c in COMPETITORS if c["name"].lower() in name_set]
        if not targets:
            logger.error(f"未找到匹配的竞品，可用名称：{[c['name'] for c in COMPETITORS]}")
            sys.exit(1)

    run_pipeline(
        competitors=targets,
        max_workers=args.workers,
        skip_scrape=args.skip_scrape,
        force_full=args.full,
    )


if __name__ == "__main__":
    main()
