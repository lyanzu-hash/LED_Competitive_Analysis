"""
LED竞品日报 · 图形界面启动器
功能：配置 API Key / 立即运行 / 设置每日定时任务 / 查看日志
"""

import sys
import os
import queue
import logging
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
ENV_FILE = BASE_DIR / ".env"
LOG_DIR  = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

PRESET_PROVIDERS = {
    "OpenAI（官方）":          ("https://api.openai.com/v1",                         "gpt-4o-mini"),
    "DeepSeek":                ("https://api.deepseek.com/v1",                        "deepseek-chat"),
    "月之暗面 Moonshot":        ("https://api.moonshot.cn/v1",                         "moonshot-v1-8k"),
    "通义千问 DashScope":       ("https://dashscope.aliyuncs.com/compatible-mode/v1",  "qwen-turbo"),
    "自定义":                  ("", ""),
}


# ── 读写 .env ──────────────────────────────────────────────────────────────────
def read_env() -> dict:
    cfg = {"OPENAI_API_KEY": "", "OPENAI_BASE_URL": "", "OPENAI_MODEL": ""}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            cfg[k.strip()] = v.strip()
    return cfg


def write_env(api_key: str, base_url: str, model: str):
    lines = [
        f"OPENAI_API_KEY={api_key}",
        f"OPENAI_BASE_URL={base_url}",
        f"OPENAI_MODEL={model}",
    ]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── 定时任务注册 ───────────────────────────────────────────────────────────────
def _write_run_bat(path: Path):
    """
    生成 run_daily.bat，使用绝对路径保证任务计划程序能正确执行。
    bat 文件保存到 D:/LED_Daily_Report/ 以避免中文路径问题。
    """
    python_exe = str(sys.executable)
    work_dir   = str(BASE_DIR)

    if getattr(sys, "frozen", False):
        run_cmd = f'"{python_exe}" --headless'
    else:
        run_cmd = f'"{python_exe}" "{BASE_DIR / "run_daily.py"}"'

    log_dir = BASE_DIR / "logs"
    content = (
        "@echo off\n"
        "chcp 65001 >nul\n"
        f'cd /d "{work_dir}"\n'
        f'if not exist "{log_dir}" mkdir "{log_dir}"\n'
        f'echo [bat] starting at %DATE% %TIME% >> "{log_dir}\\scheduler.log"\n'
        f'{run_cmd} >> "{log_dir}\\scheduler.log" 2>&1\n'
        f'echo [bat] exit code %ERRORLEVEL% at %TIME% >> "{log_dir}\\scheduler.log"\n'
        "exit /b %ERRORLEVEL%\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="gbk")


def register_task(hour: int, minute: int) -> tuple[bool, str]:
    """
    注册 / 更新 Windows 任务计划。
    bat 文件写到 D:/LED_Daily_Report/run_daily.bat（纯英文路径，schtasks 可靠识别）。
    """
    task_name = "LED竞品日报_每日生成"

    # D 盘根目录下的纯英文路径，彻底避免中文路径问题
    safe_dir  = Path("D:/LED_Daily_Report")
    bat_path  = safe_dir / "run_daily.bat"
    _write_run_bat(bat_path)   # 每次注册都重新生成，保证路径最新

    time_str = f"{hour:02d}:{minute:02d}"

    # 注意：不加 /RL HIGHEST，普通用户权限即可运行
    cmd = [
        "schtasks", "/Create",
        "/TN", task_name,
        "/TR", f'"{bat_path}"',
        "/SC", "DAILY",
        "/ST", time_str,
        "/F",
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="gbk", errors="replace"
    )
    out = (result.stdout + result.stderr).strip()
    if result.returncode == 0:
        msg = f"✅ 定时任务已设置：每天 {time_str} 自动运行\n   bat位置: {bat_path}"
        return True, msg
    else:
        # 尝试以管理员权限重新注册
        return False, f"❌ 注册失败（{out}）\n请右键 EXE → 以管理员身份运行后再试"


# ── 把 logging 模块的输出实时转发到 Tk 文本框 ──────────────────────────────────
class _TkLogHandler(logging.Handler):
    """将 logging 日志记录放入队列，由 Tk 主线程定时拉取并写入文本框。"""
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
        self.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s",
                                            datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord):
        try:
            self.log_queue.put_nowait(self.format(record))
        except Exception:
            pass


# ── 主窗口 ─────────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LED竞品日报 · 管理面板")
        self.geometry("780x640")
        self.resizable(True, True)
        self.configure(bg="#f0f4f8")
        self._running = False

        # 日志队列：后台线程写入，主线程定时读取
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._attach_log_handler()

        self._build_ui()
        self._load_env()
        self._poll_log_queue()   # 启动轮询

    # ── 日志 Handler 挂载 ─────────────────────────────────────────────────────
    def _attach_log_handler(self):
        """把自定义 Handler 挂到根 logger，捕获所有模块的日志。"""
        handler = _TkLogHandler(self._log_queue)
        handler.setLevel(logging.DEBUG)
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(handler)

    def _poll_log_queue(self):
        """每 100ms 从队列中取出日志行并追加到文本框。"""
        try:
            while True:
                line = self._log_queue.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _append_log(self, text: str):
        """向日志框末尾追加一行，区分 ERROR/WARNING 用不同颜色。"""
        self.log_box.config(state="normal")
        # 根据级别着色
        if "ERROR" in text or "失败" in text or "❌" in text:
            tag = "err"
        elif "WARNING" in text or "警告" in text:
            tag = "warn"
        elif "✅" in text or "完成" in text or "成功" in text:
            tag = "ok"
        else:
            tag = "normal"
        self.log_box.insert("end", text + "\n", tag)
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    # ── UI 构建 ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Title.TLabel",  font=("微软雅黑", 16, "bold"), background="#f0f4f8", foreground="#1a365d")
        style.configure("Head.TLabel",   font=("微软雅黑", 10, "bold"), background="#f0f4f8")
        style.configure("TLabel",        font=("微软雅黑", 10),          background="#f0f4f8")
        style.configure("TEntry",        font=("微软雅黑", 10))
        style.configure("Run.TButton",   font=("微软雅黑", 11, "bold"),  padding=8)
        style.configure("Small.TButton", font=("微软雅黑", 9),           padding=4)

        # ── 标题栏 ──────────────────────────────────────────────────────────
        header = tk.Frame(self, bg="#1a365d", pady=14)
        header.pack(fill="x")
        tk.Label(header, text="  💡 LED竞品日报  自动生成工具",
                 font=("微软雅黑", 15, "bold"), fg="white", bg="#1a365d").pack(side="left")

        body = tk.Frame(self, bg="#f0f4f8", padx=20, pady=12)
        body.pack(fill="both", expand=True)

        # ── API 配置卡片 ────────────────────────────────────────────────────
        card = tk.LabelFrame(body, text="  🔑 API 配置  ", font=("微软雅黑", 10, "bold"),
                             bg="#ffffff", fg="#2d3748", bd=1, relief="solid", padx=16, pady=12)
        card.pack(fill="x", pady=(0, 12))

        # 服务商快捷选择
        ttk.Label(card, text="服务商：", background="#ffffff").grid(row=0, column=0, sticky="w", pady=4)
        self.var_provider = tk.StringVar(value="DeepSeek")
        cb = ttk.Combobox(card, textvariable=self.var_provider,
                          values=list(PRESET_PROVIDERS.keys()), width=22, state="readonly")
        cb.grid(row=0, column=1, sticky="w", padx=(6, 0))
        cb.bind("<<ComboboxSelected>>", self._on_provider_change)

        ttk.Label(card, text="API Key：", background="#ffffff").grid(row=1, column=0, sticky="w", pady=4)
        self.var_key = tk.StringVar()
        ttk.Entry(card, textvariable=self.var_key, width=52, show="*").grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(6, 0))

        ttk.Label(card, text="Base URL：", background="#ffffff").grid(row=2, column=0, sticky="w", pady=4)
        self.var_url = tk.StringVar()
        ttk.Entry(card, textvariable=self.var_url, width=52).grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=(6, 0))

        ttk.Label(card, text="模型名称：", background="#ffffff").grid(row=3, column=0, sticky="w", pady=4)
        self.var_model = tk.StringVar()
        ttk.Entry(card, textvariable=self.var_model, width=30).grid(
            row=3, column=1, sticky="w", padx=(6, 0))

        ttk.Button(card, text="💾 保存配置", style="Small.TButton",
                   command=self._save_env).grid(row=3, column=2, padx=(12, 0))
        card.columnconfigure(1, weight=1)

        # ── 定时任务卡片 ────────────────────────────────────────────────────
        card2 = tk.LabelFrame(body, text="  ⏰ 每日定时任务  ", font=("微软雅黑", 10, "bold"),
                              bg="#ffffff", fg="#2d3748", bd=1, relief="solid", padx=16, pady=12)
        card2.pack(fill="x", pady=(0, 12))

        ttk.Label(card2, text="每天执行时间：", background="#ffffff").grid(row=0, column=0, sticky="w")
        self.var_hour   = tk.StringVar(value="08")
        self.var_minute = tk.StringVar(value="00")
        ttk.Spinbox(card2, from_=0, to=23, textvariable=self.var_hour,
                    width=4, format="%02.0f").grid(row=0, column=1, padx=(6, 2))
        ttk.Label(card2, text="时", background="#ffffff").grid(row=0, column=2)
        ttk.Spinbox(card2, from_=0, to=59, textvariable=self.var_minute,
                    width=4, format="%02.0f").grid(row=0, column=3, padx=(2, 2))
        ttk.Label(card2, text="分", background="#ffffff").grid(row=0, column=4)
        ttk.Button(card2, text="✅ 注册 / 更新定时任务", style="Small.TButton",
                   command=self._register_task).grid(row=0, column=5, padx=(16, 0))
        self.lbl_task = ttk.Label(card2, text="", background="#ffffff", foreground="#2f855a")
        self.lbl_task.grid(row=1, column=0, columnspan=6, sticky="w", pady=(4, 0))

        # ── 操作按钮 ────────────────────────────────────────────────────────
        btn_row = tk.Frame(body, bg="#f0f4f8")
        btn_row.pack(fill="x", pady=(0, 8))
        self.btn_run = ttk.Button(btn_row, text="▶  立即运行一次", style="Run.TButton",
                                  command=self._run_now)
        self.btn_run.pack(side="left", padx=(0, 12))
        ttk.Button(btn_row, text="📂 打开输出目录", style="Small.TButton",
                   command=self._open_output).pack(side="left")

        # ── 日志输出框 ──────────────────────────────────────────────────────
        log_frame = tk.LabelFrame(body, text="  📋 运行日志  ", font=("微软雅黑", 10, "bold"),
                                  bg="#ffffff", fg="#2d3748", bd=1, relief="solid")
        log_frame.pack(fill="both", expand=True)
        self.log_box = scrolledtext.ScrolledText(
            log_frame, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white", wrap="word", state="disabled", height=12)
        self.log_box.pack(fill="both", expand=True, padx=6, pady=6)
        # 颜色标签
        self.log_box.tag_config("err",    foreground="#f87171")   # 红
        self.log_box.tag_config("warn",   foreground="#fbbf24")   # 黄
        self.log_box.tag_config("ok",     foreground="#6ee7b7")   # 绿
        self.log_box.tag_config("normal", foreground="#d4d4d4")   # 默认灰白

    # ── 事件处理 ───────────────────────────────────────────────────────────────
    def _on_provider_change(self, _=None):
        name = self.var_provider.get()
        base_url, model = PRESET_PROVIDERS.get(name, ("", ""))
        if name != "自定义":
            self.var_url.set(base_url)
            self.var_model.set(model)

    def _load_env(self):
        cfg = read_env()
        self.var_key.set(cfg.get("OPENAI_API_KEY", ""))
        self.var_url.set(cfg.get("OPENAI_BASE_URL", ""))
        self.var_model.set(cfg.get("OPENAI_MODEL", ""))
        # 尝试匹配服务商
        url = cfg.get("OPENAI_BASE_URL", "")
        for name, (preset_url, _) in PRESET_PROVIDERS.items():
            if preset_url and preset_url == url:
                self.var_provider.set(name)
                break

    def _save_env(self):
        key   = self.var_key.get().strip()
        url   = self.var_url.get().strip()
        model = self.var_model.get().strip()
        if not key:
            messagebox.showwarning("提示", "请先填写 API Key")
            return
        write_env(key, url, model)
        self._log("✅ 配置已保存到 .env 文件")
        messagebox.showinfo("保存成功", "配置已保存！")

    def _register_task(self):
        self._save_env()
        try:
            h = int(self.var_hour.get())
            m = int(self.var_minute.get())
        except ValueError:
            messagebox.showerror("错误", "时间格式不正确")
            return
        ok, msg = register_task(h, m)
        self.lbl_task.config(text=msg, foreground="#2f855a" if ok else "#c53030")
        self._log(msg)
        if not ok:
            messagebox.showerror("注册失败", msg + "\n\n请尝试以管理员身份运行本程序。")

    def _run_now(self):
        if self._running:
            messagebox.showinfo("提示", "任务正在运行中，请稍候...")
            return
        self._save_env()

        def worker():
            self._running = True
            self.btn_run.config(state="disabled", text="⏳ 运行中...")

            # ── 为本次手动运行添加独立的文件日志 handler ──────────────────────
            from log_setup import setup_logging
            log_file   = setup_logging("manual")   # → logs/manual_YYYY-MM-DD_HHMMSS.log
            run_logger = logging.getLogger()
            # 找到刚刚添加的最后一个 FileHandler，记录以便运行完后移除
            new_fh = next(
                (h for h in reversed(run_logger.handlers)
                 if isinstance(h, logging.FileHandler)),
                None,
            )

            self._log("=" * 48)
            self._log(f"  开始运行  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log(f"  日志文件: {log_file.name}")
            self._log("=" * 48)
            try:
                os.environ["OPENAI_API_KEY"]  = self.var_key.get().strip()
                os.environ["OPENAI_BASE_URL"] = self.var_url.get().strip()
                os.environ["OPENAI_MODEL"]    = self.var_model.get().strip()

                import importlib
                import config as _cfg
                importlib.reload(_cfg)
                import analyzer as _ana
                importlib.reload(_ana)
                import main as _main
                importlib.reload(_main)

                filepath = _main.run_pipeline()
                self._log(f"✅ 日报已生成：{filepath}")
                self.after(0, lambda: messagebox.showinfo(
                    "完成", f"日报已生成：\n{filepath}\n\n日志：{log_file}"))
            except Exception as e:
                self._log(f"❌ 运行失败：{e}")
                self.after(0, lambda: messagebox.showerror("失败", str(e)))
            finally:
                # 移除本次运行的文件 handler，避免下次运行重复写入同一文件
                if new_fh:
                    new_fh.close()
                    run_logger.removeHandler(new_fh)
                self._running = False
                self.after(0, lambda: self.btn_run.config(
                    state="normal", text="▶  立即运行一次"))

        threading.Thread(target=worker, daemon=True).start()

    def _open_output(self):
        output_dir = BASE_DIR / "output"
        output_dir.mkdir(exist_ok=True)
        os.startfile(str(output_dir))

    def _log(self, msg: str):
        """界面内部直接调用的日志方法，放入队列统一处理。"""
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_queue.put_nowait(f"[{ts}]  {msg}")


# ── 无头模式（定时任务后台调用）─────────────────────────────────────────────────
def headless_run():
    """不弹窗，直接执行 run_daily.py 的重试逻辑。"""
    import importlib, sys as _sys
    _sys.path.insert(0, str(BASE_DIR))
    spec = importlib.util.spec_from_file_location("run_daily", BASE_DIR / "run_daily.py")
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


if __name__ == "__main__":
    if "--headless" in sys.argv:
        headless_run()
    else:
        app = App()
        app.mainloop()
