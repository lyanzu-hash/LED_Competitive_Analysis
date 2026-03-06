"""
统一日志配置模块。
无论脚本模式还是 EXE 模式，日志文件始终写到 EXE/脚本同目录下的 logs/ 文件夹。

两种模式，日志文件分开：
  定时自动执行  → logs/scheduled_YYYY-MM-DD.log        （每天覆盖追加）
  手动界面运行  → logs/manual_YYYY-MM-DD_HHMM.log      （每次新建）
"""

import logging
import sys
from datetime import datetime
from pathlib import Path


def get_base_dir() -> Path:
    """返回项目根目录：EXE 模式取 EXE 所在目录，脚本模式取本文件所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def setup_logging(mode: str = "manual") -> Path:
    """
    向根 logger 添加 FileHandler，不清除已有 handler（如 GUI 的 TkLogHandler）。

    mode:
      "scheduled" → logs/scheduled_YYYY-MM-DD.log
      "manual"    → logs/manual_YYYY-MM-DD_HHMM.log

    返回日志文件完整路径。
    """
    base_dir = get_base_dir()
    log_dir  = base_dir / "logs"
    log_dir.mkdir(exist_ok=True)

    ts       = datetime.now()
    if mode == "scheduled":
        filename = f"scheduled_{ts.strftime('%Y-%m-%d')}.log"
    else:
        filename = f"manual_{ts.strftime('%Y-%m-%d_%H%M%S')}.log"

    log_file = log_dir / filename
    fmt      = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # 文件 handler（始终添加）
    fh = logging.FileHandler(log_file, encoding="utf-8", mode="a")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # 控制台 handler（定时模式下添加，输出由 bat 重定向到 scheduler.log）
    if mode == "scheduled":
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root.addHandler(sh)

    return log_file
