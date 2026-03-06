"""
报告生成模块
Excel 结构（仅 2 个 Sheet）：
  Sheet1 - 今日竞品分析  （每行一个竞品，六维度 + 综合分析，彩色区分有无变化）
  Sheet2 - 竞品日报摘要  （LLM 综合日报全文）
"""

import os
import re
import logging
from datetime import datetime

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from config import OUTPUT_DIR

logger = logging.getLogger(__name__)

# ── 颜色 ──────────────────────────────────────────────────────────────────────
C_HEADER   = "1F4E79"   # 深蓝（表头背景）
C_WHITE    = "FFFFFF"   # 白字
C_CHANGED  = "FFF2CC"   # 淡黄 - 今日有变化
C_NOCHANGE = "F2F2F2"   # 浅灰 - 今日无变化
C_FIRST    = "E2EFDA"   # 浅绿 - 首次建档
C_ACCENT   = "ED7D31"   # 橙色（大标题）
C_SECTION  = "D6E4F0"   # 节标题背景

# 六维度标签（与提示词保持一致）
DIMENSIONS = [
    "一、产品页面",
    "二、内容页面",
    "三、营销页面",
    "四、技术页面",
    "五、信任页面",
    "六、SEO维度",
    "七、综合分析",
]


def _border() -> Border:
    s = Side(style="thin", color="BFBFBF")
    return Border(left=s, right=s, top=s, bottom=s)


def _hcell(ws, row, col, value, bg=C_HEADER, fg=C_WHITE, size=10, bold=True):
    c = ws.cell(row=row, column=col, value=value)
    c.font      = Font(bold=bold, color=fg, size=size)
    c.fill      = PatternFill("solid", fgColor=bg)
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    c.border    = _border()
    return c


def _dcell(ws, row, col, value, bg=C_WHITE, size=9, bold=False):
    c = ws.cell(row=row, column=col, value=str(value) if value is not None else "")
    c.font      = Font(size=size, bold=bold)
    c.fill      = PatternFill("solid", fgColor=bg)
    c.alignment = Alignment(vertical="top", wrap_text=True)
    c.border    = _border()
    return c


def _set_width(ws, col, w):
    ws.column_dimensions[get_column_letter(col)].width = w


# ── 把 LLM 文本按 ## 标题拆分为字典 ─────────────────────────────────────────────
def _parse_sections(text: str) -> dict[str, str]:
    """
    将 LLM 输出的 markdown 文本按 '## 一、' 这类二级标题拆分。
    返回 { "一、产品页面": "内容...", ... }
    """
    sections: dict[str, str] = {}
    current_key = None
    buf: list[str] = []

    for line in text.splitlines():
        m = re.match(r"^##\s+(.+)", line.strip())
        if m:
            if current_key is not None:
                sections[current_key] = "\n".join(buf).strip()
            current_key = m.group(1).strip()
            buf = []
        else:
            buf.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(buf).strip()

    return sections


def _get_dim(sections: dict, dim_label: str) -> str:
    """模糊匹配维度标题，提取对应内容。"""
    key_num = dim_label.split("、")[0]   # "一" / "二" / ...
    for k, v in sections.items():
        if key_num in k:
            return v or "—"
    return "—"


# ── Sheet 1：今日竞品分析 ─────────────────────────────────────────────────────
def _write_analysis_sheet(wb: openpyxl.Workbook, analyses: list[dict], diffs: dict, date_str: str):
    ws = wb.active
    ws.title = "今日竞品分析"

    # ── 大标题 ──────────────────────────────────────────────────────────────
    col_count = 9   # 竞品 + 状态 + 六维度 + 综合分析
    ws.merge_cells(f"A1:{get_column_letter(col_count)}1")
    c = ws["A1"]
    c.value     = f"LED显示屏竞品日报  {date_str}  （由 AI 自动生成）"
    c.font      = Font(bold=True, size=14, color=C_ACCENT)
    c.fill      = PatternFill("solid", fgColor="FFF2CC")
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32

    # ── 列标题 ──────────────────────────────────────────────────────────────
    headers = ["竞品名称", "今日状态",
               "①产品页面", "②内容页面", "③营销页面",
               "④技术页面", "⑤信任页面", "⑥SEO维度",
               "综合分析（主推/关键词/风格/机会点）"]
    widths  = [14, 12, 36, 36, 36, 36, 36, 36, 55]

    for col, (h, w) in enumerate(zip(headers, widths), start=1):
        _hcell(ws, 2, col, h)
        _set_width(ws, col, w)
    ws.row_dimensions[2].height = 24

    # ── 数据行 ──────────────────────────────────────────────────────────────
    for r, a in enumerate(analyses, start=3):
        name  = a.get("name", "")
        diff  = diffs.get(name)
        text  = a.get("analysis", "") or ""

        # 行背景色
        if diff is None or diff.get("is_first_run"):
            bg = C_FIRST
            status = "🟢 首次建档"
        elif diff.get("has_changes"):
            bg = C_CHANGED
            status = "🟡 今日有更新"
        else:
            bg = C_NOCHANGE
            status = "⚪ 今日无变化"

        if not text or text.startswith("（今日该竞品"):
            # 无更新 - 只填前两列
            _dcell(ws, r, 1, name, bg=bg, bold=True)
            _dcell(ws, r, 2, status, bg=bg)
            for col in range(3, col_count + 1):
                _dcell(ws, r, col, "今日无变化", bg=bg)
            ws.row_dimensions[r].height = 30
            continue

        # 解析 LLM 输出的各维度内容
        sections = _parse_sections(text)

        dim_contents = [
            _get_dim(sections, "一、产品页面"),
            _get_dim(sections, "二、内容页面"),
            _get_dim(sections, "三、营销页面"),
            _get_dim(sections, "四、技术页面"),
            _get_dim(sections, "五、信任页面"),
            _get_dim(sections, "六、SEO维度"),
            _get_dim(sections, "七、综合分析"),
        ]

        _dcell(ws, r, 1, name, bg=bg, bold=True)
        _dcell(ws, r, 2, status, bg=bg)
        for col, content in enumerate(dim_contents, start=3):
            _dcell(ws, r, col, content, bg=bg)

        # 行高按内容估算，最小 80
        max_len = max((len(c) for c in dim_contents), default=0)
        ws.row_dimensions[r].height = min(400, max(80, max_len // 4))

    ws.freeze_panes = "A3"


# ── Sheet 2：竞品日报摘要 ─────────────────────────────────────────────────────
def _write_summary_sheet(wb: openpyxl.Workbook, date_str: str, summary_text: str):
    ws = wb.create_sheet("竞品日报摘要")

    ws.merge_cells("A1:B1")
    c = ws["A1"]
    c.value     = f"LED显示屏竞品日报  {date_str}"
    c.font      = Font(bold=True, size=15, color=C_ACCENT)
    c.fill      = PatternFill("solid", fgColor="FFF2CC")
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 35

    ws.merge_cells("A2:B2")
    ws["A2"].value     = "由 AI 大模型自动生成 · 每日更新"
    ws["A2"].font      = Font(italic=True, size=9, color="808080")
    ws["A2"].alignment = Alignment(horizontal="center")

    for i, line in enumerate(summary_text.splitlines(), start=3):
        ws.merge_cells(f"A{i}:B{i}")
        c = ws[f"A{i}"]
        c.value     = line
        c.alignment = Alignment(vertical="top", wrap_text=True)
        if line.startswith("## "):
            c.font = Font(bold=True, size=12, color="1F4E79")
            c.fill = PatternFill("solid", fgColor=C_SECTION)
        elif line.startswith("- ") or line.startswith("  -"):
            c.font = Font(size=10)
        else:
            c.font = Font(size=10)

    _set_width(ws, 1, 80)
    _set_width(ws, 2, 10)
    ws.freeze_panes = "A3"


# ── 主入口 ────────────────────────────────────────────────────────────────────
def save_report(
    scrape_results: list[dict],
    analyses:       list[dict],
    summary:        str,
    diffs:          dict | None = None,
) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    filepath = os.path.join(OUTPUT_DIR, f"LED竞品日报_{date_str}.xlsx")

    wb = openpyxl.Workbook()
    _write_analysis_sheet(wb, analyses, diffs or {}, date_str)
    _write_summary_sheet(wb, date_str, summary)

    wb.save(filepath)
    logger.info(f"[报告已保存] {filepath}")
    return filepath
