#!/usr/bin/env python3
"""课堂派资料批量下载 - 图形界面"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from ketangpai_batch_download import (
    DEFAULT_CONFIG,
    KetangpaiClient,
    extract_course_id,
    load_config,
    resolve_token,
    run_download,
    save_config,
)

FONT = ("Microsoft YaHei UI", 10)
TITLE_FONT = ("Microsoft YaHei UI", 12, "bold")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("课堂派资料批量下载")
        self.geometry("720x620")
        self.minsize(640, 520)

        self.config_path = DEFAULT_CONFIG
        self.courses: list[dict] = []
        self.course_map: dict[str, str] = {}
        self.busy = False
        self.worker: threading.Thread | None = None

        self._build_ui()
        self._load_config_to_form()

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 4}
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        ttk.Label(root, text="课堂派资料批量下载", font=TITLE_FONT).pack(anchor=tk.W)

        auth = ttk.LabelFrame(root, text="登录", padding=8)
        auth.pack(fill=tk.X, pady=(8, 4))

        row1 = ttk.Frame(auth)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Token", width=8).pack(side=tk.LEFT)
        self.token_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.token_var, show="*").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4)
        )
        ttk.Button(row1, text="?", width=3, command=self._show_token_help).pack(side=tk.LEFT)

        row2 = ttk.Frame(auth)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="账号", width=8).pack(side=tk.LEFT)
        self.email_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.email_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 12)
        )
        ttk.Label(row2, text="密码").pack(side=tk.LEFT)
        self.password_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.password_var, show="*").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0)
        )

        course = ttk.LabelFrame(root, text="课程", padding=8)
        course.pack(fill=tk.X, pady=4)

        row3 = ttk.Frame(course)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="选择课程", width=8).pack(side=tk.LEFT)
        self.course_var = tk.StringVar()
        self.course_combo = ttk.Combobox(
            row3, textvariable=self.course_var, state="readonly"
        )
        self.course_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
        ttk.Button(row3, text="刷新课程", command=self._refresh_courses).pack(side=tk.LEFT)

        row4 = ttk.Frame(course)
        row4.pack(fill=tk.X, pady=2)
        ttk.Label(row4, text="课程 ID", width=8).pack(side=tk.LEFT)
        self.course_id_var = tk.StringVar()
        ttk.Entry(row4, textvariable=self.course_id_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0)
        )

        row5 = ttk.Frame(course)
        row5.pack(fill=tk.X, pady=2)
        ttk.Label(row5, text="资料 URL", width=8).pack(side=tk.LEFT)
        self.course_url_var = tk.StringVar()
        ttk.Entry(row5, textvariable=self.course_url_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0)
        )

        opts = ttk.LabelFrame(root, text="选项", padding=8)
        opts.pack(fill=tk.X, pady=4)

        row6 = ttk.Frame(opts)
        row6.pack(fill=tk.X, pady=2)
        ttk.Label(row6, text="保存到", width=8).pack(side=tk.LEFT)
        self.output_var = tk.StringVar(value="downloads")
        ttk.Entry(row6, textvariable=self.output_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4)
        )
        ttk.Button(row6, text="浏览...", command=self._pick_output).pack(side=tk.LEFT)

        row7 = ttk.Frame(opts)
        row7.pack(fill=tk.X, pady=2)
        self.skip_existing_var = tk.BooleanVar(value=True)
        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            row7, text="跳过已下载", variable=self.skip_existing_var
        ).pack(side=tk.LEFT)
        ttk.Checkbutton(row7, text="仅预览（不下载）", variable=self.dry_run_var).pack(
            side=tk.LEFT, padx=(16, 0)
        )

        btns = ttk.Frame(root)
        btns.pack(fill=tk.X, pady=8)
        self.download_btn = ttk.Button(btns, text="开始下载", command=self._start_download)
        self.download_btn.pack(side=tk.LEFT)
        ttk.Button(btns, text="保存配置", command=self._save_config_from_form).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(btns, text="打开目录", command=self._open_output).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        self.progress = ttk.Progressbar(root, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(0, 4))

        log_frame = ttk.LabelFrame(root, text="日志", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=14, font=("Consolas", 9), state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(root, textvariable=self.status_var).pack(anchor=tk.W, pady=(4, 0))

        self.course_combo.bind("<<ComboboxSelected>>", self._on_course_selected)

    def _show_token_help(self) -> None:
        messagebox.showinfo(
            "如何获取 Token",
            "1. 浏览器登录课堂派\n"
            "2. 按 F12 打开开发者工具\n"
            "3. Application -> Local Storage\n"
            "4. 复制 token 的值粘贴到上方",
        )

    def _log(self, msg: str) -> None:
        def append() -> None:
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        self.after(0, append)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.download_btn.configure(state=state)
        self.status_var.set("处理中..." if busy else "就绪")

    def _set_progress(self, current: int, total: int) -> None:
        def update() -> None:
            self.progress["maximum"] = max(total, 1)
            self.progress["value"] = current
            self.status_var.set(f"进度 {current}/{total}")

        self.after(0, update)

    def _form_to_config(self) -> dict:
        return {
            "token": self.token_var.get().strip(),
            "email": self.email_var.get().strip(),
            "password": self.password_var.get().strip(),
            "course_id": self.course_id_var.get().strip(),
            "course_url": self.course_url_var.get().strip(),
            "output": self.output_var.get().strip() or "downloads",
            "list_courses": False,
            "dry_run": self.dry_run_var.get(),
            "skip_existing": self.skip_existing_var.get(),
        }

    def _load_config_to_form(self) -> None:
        if not self.config_path.exists():
            return
        try:
            cfg = load_config(self.config_path)
        except Exception as e:
            self._log(f"读取配置失败: {e}")
            return

        self.token_var.set(cfg.get("token", ""))
        self.email_var.set(cfg.get("email", ""))
        self.password_var.set(cfg.get("password", ""))
        self.course_id_var.set(cfg.get("course_id", ""))
        self.course_url_var.set(cfg.get("course_url", ""))
        self.output_var.set(cfg.get("output", "downloads"))
        self.skip_existing_var.set(cfg.get("skip_existing", True))
        self.dry_run_var.set(cfg.get("dry_run", False))
        self._log(f"已加载配置: {self.config_path}")

    def _save_config_from_form(self) -> None:
        try:
            save_config(self.config_path, self._form_to_config())
            self._log(f"配置已保存: {self.config_path}")
            messagebox.showinfo("保存成功", f"已保存到 {self.config_path}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="选择下载目录")
        if path:
            self.output_var.set(path)

    def _open_output(self) -> None:
        path = Path(self.output_var.get().strip() or "downloads")
        course_id = self.course_id_var.get().strip()
        if course_id:
            path = path / course_id
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)

    def _on_course_selected(self, _event: object = None) -> None:
        label = self.course_var.get()
        cid = self.course_map.get(label, "")
        if cid:
            self.course_id_var.set(cid)

    def _run_in_thread(self, target) -> None:
        if self.busy:
            return

        self._set_busy(True)
        self.progress["value"] = 0

        def wrapper() -> None:
            try:
                target()
            except Exception as e:
                self._log(f"错误: {e}")
                self.after(0, lambda: messagebox.showerror("错误", str(e)))
            finally:
                self.after(0, lambda: self._set_busy(False))

        self.worker = threading.Thread(target=wrapper, daemon=True)
        self.worker.start()

    def _get_client(self) -> KetangpaiClient:
        config = self._form_to_config()
        token = resolve_token(config, self.config_path, log=self._log, save_token=True)
        self.token_var.set(token)
        return KetangpaiClient(token)

    def _refresh_courses(self) -> None:
        def task() -> None:
            self._log("正在获取课程列表...")
            client = self._get_client()
            courses = client.list_courses()
            self.courses = courses

            labels: list[str] = []
            self.course_map = {}
            for c in courses:
                cid = str(c.get("id") or c.get("courseid") or "")
                name = c.get("coursename") or c.get("name") or "未命名"
                teacher = c.get("teachername") or c.get("teacher") or ""
                label = f"{name} ({teacher})" if teacher else name
                labels.append(label)
                self.course_map[label] = cid

            def update_combo() -> None:
                self.course_combo["values"] = labels
                if labels:
                    self.course_combo.current(0)
                    self._on_course_selected()
                self._log(f"已加载 {len(labels)} 门课程")

            self.after(0, update_combo)

        self._run_in_thread(task)

    def _start_download(self) -> None:
        config = self._form_to_config()
        course_url = config.get("course_url", "")
        if course_url and not config.get("course_id"):
            parsed = extract_course_id(course_url)
            if parsed:
                config["course_id"] = parsed
                self.course_id_var.set(parsed)

        if not config.get("course_id") and not config.get("course_url"):
            messagebox.showwarning("提示", "请选择课程或填写课程 ID / 资料 URL")
            return

        def task() -> None:
            self._log("=" * 40)
            self._log("开始任务...")
            client = self._get_client()
            result = run_download(
                client,
                config,
                log=self._log,
                on_progress=self._set_progress,
            )
            save_config(self.config_path, config)

            def done() -> None:
                root = result.get("output_root")
                if root:
                    self.status_var.set(f"完成，保存于 {root}")
                else:
                    self.status_var.set("完成")

            self.after(0, done)

        self._run_in_thread(task)


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
