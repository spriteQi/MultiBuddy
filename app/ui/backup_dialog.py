"""保存向导弹窗：为当前本地凭证命名账号并预览清单。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..core.model import CredentialItem, SourceProfile
from ..core.store import BackupStore
from .confirm_dialogs import _make_modal, _wait, error
from .widgets import COLORS, create_button, fmt_size


class BackupDialog:
    """为"→ 保存"命名账号并确认要备份的文件。

    exec() 返回 (账号名, 勾选相对路径列表)；取消返回 None。
    命名在对话框内校验，实际备份由调用方在对话框关闭后执行。
    """

    def __init__(self, parent, fonts, store: BackupStore, profile: SourceProfile,
                 items: list[CredentialItem], checked: set[str]):
        self.parent = parent
        self.fonts = fonts
        self.store = store
        self.profile = profile
        self.items = items
        exist = {i.rel for i in items if i.exists}
        self.checked = [rel for rel in checked if rel in exist]
        self._result = None
        self._win = None

    def exec(self):
        win = self._win = _make_modal(self.parent, "备份当前凭证", self.fonts, 580, 430)
        tk.Label(
            win, text="保存当前登录凭证", bg=COLORS["card"], fg=COLORS["text"], font=self.fonts["title"],
        ).pack(anchor="w", padx=28, pady=(18, 2))
        tk.Label(
            win, text=f"客户端：{self.profile.title}　源目录：{self.profile.root}",
            bg=COLORS["card"], fg=COLORS["sub"], font=self.fonts["small"],
            wraplength=520, justify="left",
        ).pack(anchor="w", padx=28)

        row = tk.Frame(win, bg=COLORS["card"])
        row.pack(fill="x", padx=28, pady=(16, 6))
        tk.Label(row, text="账号名 *", bg=COLORS["card"], fg=COLORS["text"], font=self.fonts["body"]).pack(side="left")
        self.var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.var, font=self.fonts["body"], width=30)
        entry.pack(side="left", padx=10)
        entry.focus_set()
        tk.Label(
            row, text="用于识别该备份，可随时重命名", bg=COLORS["card"], fg=COLORS["sub"], font=self.fonts["small"],
        ).pack(side="left")

        tk.Label(
            win, text=f"将备份 {len(self.checked)} 个凭证文件/目录：",
            bg=COLORS["card"], fg=COLORS["text"], font=self.fonts["body_bold"],
        ).pack(anchor="w", padx=28, pady=(8, 0))

        box = tk.Frame(win, bg="#FFFFFF", highlightbackground=COLORS["border"], highlightthickness=1)
        box.pack(fill="both", expand=True, padx=28, pady=(4, 4))
        text = tk.Text(
            box, wrap="none", bg="#FFFFFF", fg=COLORS["text"], relief="flat", borderwidth=0,
            font=self.fonts["body"], padx=8, pady=6, height=8,
        )
        sb = ttk.Scrollbar(box, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        for item in self.items:
            if item.rel in self.checked:
                text.insert("end", f"✓ {item.rel}  ({fmt_size(item.size)})\n")
        text.configure(state="disabled")

        tk.Label(
            win, text="提示：如想调整备份范围，可先在左侧列表勾选/取消后再点保存。",
            bg=COLORS["card"], fg=COLORS["warn"], font=self.fonts["small"],
        ).pack(anchor="w", padx=28)

        bar = tk.Frame(win, bg=COLORS["card"])
        bar.pack(fill="x", padx=28, pady=(8, 16))
        create_button(bar, "取消", "default", win.destroy, font=self.fonts["body"], width=10).pack(side="right", padx=4)
        create_button(bar, "开始备份", "primary", self._submit, font=self.fonts["body"], width=12).pack(side="right", padx=4)

        _wait(win)
        return self._result

    def _submit(self):
        name = self.var.get().strip()
        try:
            self.store.validate_name(name)
        except Exception as exc:
            error(self.parent, self.fonts, "命名无效", str(exc))
            return
        self._result = (name, list(self.checked))
        if self._win is not None:
            self._win.destroy()
