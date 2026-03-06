"""
每日定时运行入口：失败自动重试（最多 3 次），完成后发 Windows 系统通知。
"""

import sys
import time
import logging
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

# 确保从脚本所在目录运行，保证相对导入正确
BASE_DIR = Path(__file__).parent if not getattr(sys, "frozen", False) else Path(sys.executable).parent
sys.path.insert(0, str(BASE_DIR))

# ── 日志必须在导入其他模块之前配置，否则 basicConfig 会被抢先调用 ──────────────
from log_setup import setup_logging
LOG_FILE = setup_logging("scheduled")   # → logs/scheduled_YYYY-MM-DD.log

from main import run_pipeline

MAX_RETRIES = 3
RETRY_WAIT  = 300   # 每次重试间隔（秒）

logger = logging.getLogger(__name__)


# ── Windows 系统通知（气泡消息）──────────────────────────────────────────────
def _send_notification(title: str, body: str, is_error: bool = False):
    """
    使用 PowerShell 发送 Windows Toast 通知（Win10/11）。
    在后台静默执行，不影响主流程。
    """
    icon = "❌" if is_error else "✅"
    # 转义单引号，防止 PowerShell 解析错误
    safe_title = title.replace("'", "`'")
    safe_body  = body.replace("'", "`'").replace("\n", " ")
    ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Information
$n.Visible = $true
$n.BalloonTipTitle = '{safe_title}'
$n.BalloonTipText  = '{safe_body}'
$n.BalloonTipIcon  = 'Info'
$n.ShowBalloonTip(8000)
Start-Sleep -Milliseconds 8500
$n.Dispose()
"""
    try:
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", ps_script],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.debug(f"[通知] 发送失败（不影响主流程）: {e}")


def main():
    logger.info("=" * 52)
    logger.info(f"  LED竞品日报  定时任务启动  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info(f"  日志文件: {LOG_FILE}")
    logger.info("=" * 52)

    last_error  = None
    output_path = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"[第 {attempt}/{MAX_RETRIES} 次尝试]")
            output_path = run_pipeline()
            logger.info(f"✅ 任务成功完成：{output_path}")

            # ── 成功通知 ─────────────────────────────────────────────────────
            _send_notification(
                title="LED竞品日报 已生成 ✅",
                body=f"今日日报已保存至：{Path(output_path).name}",
            )
            return

        except Exception:
            last_error = traceback.format_exc()
            logger.error(f"❌ 第 {attempt} 次失败：\n{last_error}")
            if attempt < MAX_RETRIES:
                logger.info(f"  {RETRY_WAIT} 秒后重试...")
                time.sleep(RETRY_WAIT)

    # ── 全部失败通知 ──────────────────────────────────────────────────────────
    logger.critical(f"💥 已重试 {MAX_RETRIES} 次，全部失败。\n{last_error}")
    _send_notification(
        title="LED竞品日报 生成失败 ❌",
        body=f"重试 {MAX_RETRIES} 次均失败，请查看日志：{LOG_FILE.name}",
        is_error=True,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
