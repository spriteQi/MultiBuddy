"""UI 主题与复用组件：配色、字体、按钮/徽标/卡片/树视图/状态栏。"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# 配色（浅色后台管理风格）
COLORS = {
    "bg": "#F5F6FA",
    "card": "#FFFFFF",
    "text": "#1F2329",
    "sub": "#646A73",
    "border": "#E3E6ED",
    "primary": "#165DFF",
    "primary_h": "#0E42D2",
    "primary_lt": "#E8F1FF",
    "danger": "#FF4D4F",
    "danger_h": "#D63A3C",
    "danger_lt": "#FFECE8",
    "warn": "#FF7D00",
    "warn_lt": "#FFF3E8",
    "success": "#00B42A",
    "success_lt": "#E8FFEA",
    "green_dot": "#00B42A",
    "red_dot": "#FF4D4F",
    "gray_dot": "#C9CDD4",
}

FONT_FAM = "Microsoft YaHei UI"
_FONT_CHECKS = ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Segoe UI")


def _pick_font(root: tk.Misc) -> str:
    fams = set(tkfont.families(root))
    for f in _FONT_CHECKS:
        if f in fams:
            return f
    return "TkDefaultFont"


def _build_fonts(root: tk.Misc) -> dict:
    fam = _pick_font(root)
    return {
        "ui": fam,
        "title": tkfont.Font(family=fam, size=15, weight="bold"),
        "subtitle": tkfont.Font(family=fam, size=12, weight="bold"),
        "body": tkfont.Font(family=fam, size=11),
        "body_bold": tkfont.Font(family=fam, size=11, weight="bold"),
        "small": tkfont.Font(family=fam, size=9),
        "mono": tkfont.Font(family="Consolas", size=10),
    }


def setup_theme(root: tk.Tk) -> dict:
    """应用全局配色与 ttk 样式，返回字体表。"""
    c = COLORS
    fonts = _build_fonts(root)
    root.option_add("*Font", fonts["body"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TNotebook", background=c["bg"], borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        padding=(16, 8),
        font=fonts["body_bold"],
        background=c["bg"],
        foreground=c["sub"],
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", c["card"]), ("active", "#ECEEF3")],
        foreground=[("selected", c["primary"])],
    )
    style.configure("Treeview", font=fonts["body"], rowheight=28, fieldbackground="#FFFFFF", background="#FFFFFF")
    style.configure(
        "Treeview.Heading",
        font=tkfont.Font(family=fonts["ui"], size=10, weight="bold"),
        background="#F7F8FA",
        foreground=c["text"],
        borderwidth=0,
    )
    style.map("Treeview", background=[("selected", c["primary_lt"])], foreground=[("selected", c["text"])])
    style.configure("Vertical.TScrollbar", background="#D5D8DF", troughcolor="#FFFFFF", width=12)
    return fonts


def create_button(parent, text, kind="default", command=None, width=None, font=None, padx=14, pady=6) -> tk.Button:
    """创建语义配色按钮（kind: primary/danger/default/ghost）。"""
    c = COLORS
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        relief="flat",
        bd=0,
        cursor="hand2",
        padx=padx,
        pady=pady,
        font=font or tkfont.Font(family=_FONT_CHECKS[0], size=11),
        takefocus=0,
    )
    scheme = {
        "primary": (c["primary"], "#FFFFFF", c["primary_h"]),
        "danger": (c["danger"], "#FFFFFF", c["danger_h"]),
        "default": (c["card"], c["text"], "#F1F3F6"),
        "ghost": (c["bg"], c["text"], "#ECEEF3"),
    }[kind]
    bg, fg, hover = scheme
    btn.configure(bg=bg, fg=fg, activebackground=hover, activeforeground=fg)

    def _on_enter(_e):
        if btn["state"] != "disabled":
            btn.configure(bg=hover)

    def _on_leave(_e):
        if btn["state"] != "disabled":
            btn.configure(bg=bg)

    btn.bind("<Enter>", _on_enter)
    btn.bind("<Leave>", _on_leave)
    return btn


def create_dot(canvas: tk.Canvas, color: str, x: int = 6, y: int = 6, r: int = 4) -> None:
    canvas.delete("all")
    canvas.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="")


def fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size / 1024:.1f} KB"
    if size < 1024**3:
        return f"{size / 1024**2:.1f} MB"
    return f"{size / 1024**3:.2f} GB"


def fmt_dt(iso: str) -> str:
    """ISO 时间显示为 YYYY-MM-DD HH:MM。"""
    if not iso:
        return "-"
    return iso.replace("T", " ")[:16]


class Card(tk.Frame):
    """白色卡片容器。"""

    def __init__(self, parent, **kw):
        c = COLORS
        super().__init__(
            parent, bg=c["card"], highlightbackground=c["border"], highlightthickness=1, **kw
        )


class SectionTitle(tk.Frame):
    """区块标题（圆点 + 标题 + 右侧计数）。"""

    def __init__(self, parent, text, fonts, hint=""):
        super().__init__(parent, bg=COLORS["bg"])
        dot = tk.Canvas(self, width=14, height=16, bg=COLORS["bg"], highlightthickness=0)
        dot.create_oval(3, 4, 11, 12, fill=COLORS["primary"], outline="")
        dot.pack(side="left", anchor="w")
        tk.Label(self, text=text, bg=COLORS["bg"], fg=COLORS["text"], font=fonts["body_bold"]).pack(side="left")
        if hint:
            tk.Label(self, text=hint, bg=COLORS["bg"], fg=COLORS["sub"], font=fonts["small"]).pack(side="left", padx=(6, 0))


class StatusBar(tk.Frame):
    """底部状态栏：左侧状态消息，右侧全局信息。"""

    def __init__(self, parent, fonts):
        super().__init__(parent, bg="#F0F1F5", height=30, highlightbackground=COLORS["border"], highlightthickness=1)
        self._fonts = fonts
        self._left = tk.Label(self, text="就绪", anchor="w", bg="#F0F1F5", fg=COLORS["text"], font=fonts["body"])
        self._left.pack(side="left", padx=10, fill="x", expand=True)
        self._right = tk.Label(self, text="", anchor="e", bg="#F0F1F5", fg=COLORS["sub"], font=fonts["small"])
        self._right.pack(side="right", padx=10)

    def message(self, text: str, ok: bool = True) -> None:
        self._left.config(text=text, fg=COLORS["success"] if ok else COLORS["danger"])

    def info(self, text: str) -> None:
        self._right.config(text=text)


class SimpleTree(ttk.Treeview):
    """带表头并关闭内置排序的封装树。"""

    def __init__(self, parent, columns, headings, widths, fonts, selectmode="browse", stretch_last=True):
        super().__init__(
            parent,
            columns=columns,
            show="headings",
            selectmode=selectmode,
            style="Treeview",
        )
        for col, head, w in zip(columns, headings, widths):
            self.heading(col, text=head)
            self.column(col, width=w, minwidth=30, anchor="w", stretch=(stretch_last and col == columns[-1]))
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.yview, style="Vertical.TScrollbar")
        self.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.pack(side="left", fill="both", expand=True)
