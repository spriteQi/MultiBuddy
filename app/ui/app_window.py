"""主窗口：标题栏 + CodeBuddy / WorkBuddy 两个标签页 + 全局状态栏。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..core.sources import ProfileRegistry
from ..core.store import BackupStore
from .client_page import ClientPage
from .widgets import COLORS, StatusBar, setup_theme

FONT = "Microsoft YaHei UI"


class AppWindow:
    """应用主窗口，持有两个客户端标签页并共享 registry / store。"""

    def __init__(self, root: tk.Tk, registry: ProfileRegistry, store: BackupStore):
        self.root = root
        self.registry = registry
        self.store = store
        self.fonts = setup_theme(root)
        self.pages: dict[str, ClientPage] = {}

        root.title("MultiBuddy · CodeBuddy / WorkBuddy 账号凭证管理")
        root.geometry("1140x700")
        root.minsize(980, 620)
        root.configure(bg=COLORS["bg"])
        root.fonts = self.fonts

        self._build_header()
        self._build_tabs()
        self._build_statusbar()
        self.refresh_summary()

    # ---------- 界面搭建 ----------
    def _build_header(self):
        c = COLORS
        header = tk.Frame(self.root, bg=c["bg"])
        header.pack(fill="x", padx=20, pady=(14, 6))
        tk.Label(
            header, text="MultiBuddy", bg=c["bg"], fg=c["primary"],
            font=self.fonts["title"],
        ).pack(side="left")
        tk.Label(
            header, text="· 本地登录凭证的保存与多账号切换", bg=c["bg"], fg=c["sub"],
            font=self.fonts["body"],
        ).pack(side="left", padx=(8, 0))
        self._summary_lbl = tk.Label(
            header, text="", bg=c["bg"], fg=c["sub"], font=self.fonts["small"], anchor="e",
        )
        self._summary_lbl.pack(side="right")

    def _build_tabs(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=12, pady=(2, 4))
        cb = ClientPage(nb, self.fonts, self.registry, self.store, "codebuddy", self._on_status)
        wb = ClientPage(nb, self.fonts, self.registry, self.store, "workbuddy", self._on_status)
        nb.add(cb, text="  CodeBuddy  ")
        nb.add(wb, text="  WorkBuddy  ")
        self.pages = {"codebuddy": cb, "workbuddy": wb}

    def _build_statusbar(self):
        self.statusbar = StatusBar(self.root, self.fonts)
        self.statusbar.pack(fill="x", side="bottom")

    # ---------- 状态与汇总 ----------
    def _on_status(self, text: str, ok: bool = True):
        self.statusbar.message(text, ok)
        self.refresh_summary()

    def refresh_summary(self):
        total = len(self.store.list_backups())
        self._summary_lbl.config(text=f"共 {total} 个账号备份 · user/{self.store.user_dir.name}")
        self.statusbar.info(f"user 目录：{self.store.user_dir}")

    def run(self):
        self.root.mainloop()
