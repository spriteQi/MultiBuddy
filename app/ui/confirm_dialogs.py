"""通用弹窗：危险操作确认、未备份三选一、结果汇总、提示/错误。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..core.model import OperationResult
from .widgets import COLORS, create_button, fmt_dt

_MODAL_BG = COLORS["card"]


def _center(win: tk.Toplevel, parent: tk.Misc) -> None:
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")


def _make_modal(parent, title: str, fonts, w: int, h: int) -> tk.Toplevel:
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=_MODAL_BG)
    win.resizable(False, False)
    win.transient(parent)
    win.protocol("WM_DELETE_WINDOW", win.destroy)
    win.minsize(w, h)
    _center(win, parent)
    win.grab_set()
    win.bind("<Escape>", lambda _e: win.destroy())
    win.fonts = fonts
    return win


def _wait(win: tk.Toplevel) -> None:
    parent = win.master if isinstance(win.master, tk.Misc) else None
    try:
        if parent:
            parent.wait_window(win)
        else:
            win.wait_window()
    except tk.TclError:
        pass


def confirm(
    parent, fonts, title: str, message: str, ok_text: str = "继续", cancel_text: str = "取消",
    danger: bool = False,
) -> bool:
    """二次确认弹窗，返回是否继续。"""
    result = {"v": False}
    win = _make_modal(parent, title, fonts, 460, 240)
    tk.Label(
        win, text=("!" if danger else "i"), font=("Consolas", 26, "bold"),
        bg=_MODAL_BG, fg=COLORS["danger"] if danger else COLORS["primary"],
    ).pack(pady=(20, 0))
    tk.Label(
        win, text=message, wraplength=400, justify="left", bg=_MODAL_BG,
        fg=COLORS["text"], font=fonts["body"], anchor="n",
    ).pack(padx=28, pady=(12, 8), fill="both", expand=True)

    bar = tk.Frame(win, bg=_MODAL_BG)
    bar.pack(pady=(0, 16))

    def _ok():
        result["v"] = True
        win.destroy()

    if cancel_text:
        create_button(bar, cancel_text, "default", win.destroy, font=fonts["body"], width=10).pack(side="left", padx=6)
    create_button(bar, ok_text, "danger" if danger else "primary", _ok, font=fonts["body"], width=10).pack(side="left", padx=6)
    _wait(win)
    return result["v"]


def choice3(parent, fonts, title: str, message: str, a_text: str, b_text: str, c_text: str) -> str:
    """三选一弹窗（防丢失提示）：返回 'a' / 'b' / 'c'，关闭视为 'c'。"""
    result = {"v": "c"}
    win = _make_modal(parent, title, fonts, 500, 300)
    tk.Label(
        win, text="安全提示", font=("Consolas", 24, "bold"), bg=_MODAL_BG, fg=COLORS["warn"],
    ).pack(pady=(20, 0))
    tk.Label(
        win, text=message, wraplength=430, justify="left", bg=_MODAL_BG,
        fg=COLORS["text"], font=fonts["body"], anchor="n",
    ).pack(padx=30, pady=(10, 8), fill="both", expand=True)

    bar = tk.Frame(win, bg=_MODAL_BG)
    bar.pack(pady=(0, 18))

    def pick(v):
        result["v"] = v
        win.destroy()

    create_button(bar, c_text, "default", lambda: pick("c"), font=fonts["body"], width=12).pack(side="right", padx=5)
    create_button(bar, b_text, "ghost", lambda: pick("b"), font=fonts["body"], width=12).pack(side="right", padx=5)
    create_button(bar, a_text, "primary", lambda: pick("a"), font=fonts["body"], width=14).pack(side="right", padx=5)
    win.protocol("WM_DELETE_WINDOW", lambda: pick("c"))
    _wait(win)
    return result["v"]


def show_result(parent, fonts, title: str, res: OperationResult) -> None:
    """操作结果汇总：成功项绿、失败项红、逐条列出。"""
    win = _make_modal(parent, title, fonts, 560, 380)
    head = tk.Frame(win, bg=_MODAL_BG)
    head.pack(fill="x", padx=24, pady=(18, 4))
    tk.Label(
        head, text=("✓ 成功" if res.ok else "✕ 未完成"), bg=_MODAL_BG,
        fg=COLORS["success"] if res.ok else COLORS["danger"],
        font=("Consolas", 20, "bold"),
    ).pack(side="left")
    tk.Label(
        head, text=f"{res.success_count} 成功 · {res.fail_count} 失败", bg=_MODAL_BG,
        fg=COLORS["sub"], font=fonts["body"],
    ).pack(side="right")

    tk.Label(
        win, text=res.message, wraplength=510, justify="left", bg=_MODAL_BG,
        fg=COLORS["text"], font=fonts["body_bold"],
    ).pack(anchor="w", padx=24, pady=(2, 8))

    box = tk.Frame(win, bg="#FFFFFF", highlightbackground=COLORS["border"], highlightthickness=1)
    box.pack(fill="both", expand=True, padx=24)
    text = tk.Text(
        box, wrap="none", bg="#FFFFFF", fg=COLORS["text"], relief="flat",
        font=fonts["body"], height=9, padx=8, pady=6, borderwidth=0,
    )
    sb = ttk.Scrollbar(box, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    text.pack(fill="both", expand=True)
    text.tag_configure("ok", foreground=COLORS["success"])
    text.tag_configure("bad", foreground=COLORS["danger"])
    text.tag_configure("plain", foreground=COLORS["sub"])
    for step in res.steps:
        tag = "ok" if step.startswith(("已", "✓")) else "bad" if "失败" in step or "无法" in step else "plain"
        text.insert("end", step + "\n", tag)
    text.configure(state="disabled")

    create_button(win, "关闭", "primary", win.destroy, font=fonts["body"], width=14).pack(pady=14)
    _wait(win)


def info(parent, fonts, title: str, message: str) -> None:
    win = _make_modal(parent, title, fonts, 440, 210)
    tk.Label(
        win, text="i", font=("Consolas", 26, "bold"), bg=_MODAL_BG, fg=COLORS["primary"],
    ).pack(pady=(20, 0))
    tk.Label(
        win, text=message, wraplength=380, justify="left", bg=_MODAL_BG,
        fg=COLORS["text"], font=fonts["body"], anchor="n",
    ).pack(padx=26, pady=(10, 4), fill="both", expand=True)
    create_button(win, "知道了", "primary", win.destroy, font=fonts["body"], width=12).pack(pady=(0, 16))
    _wait(win)


def error(parent, fonts, title: str, message: str) -> None:
    win = _make_modal(parent, title, fonts, 460, 220)
    tk.Label(
        win, text="×", font=("Consolas", 26, "bold"), bg=_MODAL_BG, fg=COLORS["danger"],
    ).pack(pady=(20, 0))
    tk.Label(
        win, text=message, wraplength=400, justify="left", bg=_MODAL_BG,
        fg=COLORS["text"], font=fonts["body"], anchor="n",
    ).pack(padx=26, pady=(10, 4), fill="both", expand=True)
    create_button(win, "关闭", "primary", win.destroy, font=fonts["body"], width=12).pack(pady=(0, 16))
    _wait(win)
