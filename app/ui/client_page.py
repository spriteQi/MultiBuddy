"""单客户端页：源工具条 + 左"本地凭证" + 右"已备份凭证" + 中缝操作区。"""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, simpledialog, ttk

from ..core.backup import BackupError, create_backup
from ..core.model import (
    BackupManifest,
    Candidate,
    OperationResult,
    SourceProfile,
)
from ..core.restore import clear_to_empty, current_is_backed_up, write_from_backup
from ..core.sources import ProfileRegistry, scan_custom_source
from ..core.store import BackupStore
from .backup_dialog import BackupDialog
from .confirm_dialogs import choice3, confirm, error, info, show_result
from .widgets import COLORS, SectionTitle, SimpleTree, create_button, fmt_dt, fmt_size

CHECKED, UNCHECKED = "✓", " "


class ManageCandidatesDialog:
    """管理当前源的候选凭证清单：增删文件/目录、自动扫描命名命中项。"""

    def __init__(self, parent, fonts, registry: ProfileRegistry, profile: SourceProfile):
        self.parent = parent
        self.fonts = fonts
        self.registry = registry
        self.profile = profile
        self._rows: list[Candidate] = [Candidate(c.rel, c.kind) for c in profile.candidates]

    def exec(self):
        from .confirm_dialogs import _make_modal, _wait

        win = _make_modal(self.parent, "管理凭证候选清单", self.fonts, 620, 460)
        self._win = win
        tk.Label(
            win, text="凭证候选清单（勾选范围即备份/清除边界）", bg=COLORS["card"],
            fg=COLORS["text"], font=self.fonts["body_bold"],
        ).pack(anchor="w", padx=24, pady=(16, 4))
        tk.Label(
            win, text=f"源目录：{self.profile.root}", bg=COLORS["card"], fg=COLORS["sub"],
            font=self.fonts["small"], wraplength=560, justify="left",
        ).pack(anchor="w", padx=24)

        tree = SimpleTree(
            win,
            columns=("kind", "rel", "state"),
            headings=("类型", "相对路径", "状态"),
            widths=(60, 380, 80),
            fonts=self.fonts,
        )
        tree.pack(fill="both", expand=True, padx=24, pady=(8, 4))
        self._tree = tree
        self._refresh_rows()

        bar = tk.Frame(win, bg=COLORS["card"])
        bar.pack(fill="x", padx=24, pady=2)
        create_button(bar, "添加文件…", "ghost", self._add_file, font=self.fonts["body"]).pack(side="left", padx=2)
        create_button(bar, "添加目录…", "ghost", self._add_dir, font=self.fonts["body"]).pack(side="left", padx=2)
        create_button(bar, "自动扫描", "ghost", self._auto_scan, font=self.fonts["body"]).pack(side="left", padx=2)
        create_button(bar, "删除选中", "ghost", self._remove_selected, font=self.fonts["body"]).pack(side="left", padx=2)

        foot = tk.Frame(win, bg=COLORS["card"])
        foot.pack(fill="x", padx=24, pady=(2, 16))
        create_button(foot, "取消", "default", win.destroy, font=self.fonts["body"], width=10).pack(side="right", padx=4)
        create_button(foot, "保存修改", "primary", self._save, font=self.fonts["body"], width=12).pack(side="right", padx=4)
        _wait(win)

    def _refresh_rows(self):
        tree = self._tree
        tree.delete(*tree.get_children())
        root = self.profile.root
        for idx, c in enumerate(self._rows):
            p = root / c.rel
            state = "存在" if p.exists() else "缺失"
            kind = "目录" if c.kind == "dir" else "文件"
            tree.insert("", "end", iid=str(idx), values=(kind, c.rel, state))

    def _rel_of(self, path: str) -> str:
        try:
            return os.path.relpath(path, str(self.profile.root))
        except ValueError:
            return path

    def _add_file(self):
        path = filedialog.askopenfilename(parent=self._win, title="选择凭证文件（位于源目录内）")
        if not path:
            return
        rel = self._rel_of(path).replace("\\", "/")
        if rel.startswith(".."):
            error(self._win, self.fonts, "路径不在源目录内", "请选择源目录内的文件。")
            return
        self._rows.append(Candidate(rel, "file"))
        self._refresh_rows()

    def _add_dir(self):
        path = filedialog.askdirectory(parent=self._win, title="选择凭证目录（位于源目录内）")
        if not path:
            return
        rel = self._rel_of(path).replace("\\", "/")
        if rel.startswith(".."):
            error(self._win, self.fonts, "路径不在源目录内", "请选择源目录内的目录。")
            return
        self._rows.append(Candidate(rel, "dir"))
        self._refresh_rows()

    def _auto_scan(self):
        hits = scan_custom_source(self.profile.root)
        have = {c.rel for c in self._rows}
        added = 0
        for c in hits:
            if c.rel not in have:
                self._rows.append(c)
                have.add(c.rel)
                added += 1
        if added:
            self._refresh_rows()
            info(self._win, self.fonts, "扫描完成", f"按命名规则新发现 {added} 个可能包含凭证的条目。")
        else:
            info(self._win, self.fonts, "扫描完成", "未发现新条目。")

    def _remove_selected(self):
        sel = self._tree.selection()
        if not sel:
            return
        idxs = sorted((int(i) for i in sel), reverse=True)
        for idx in idxs:
            if 0 <= idx < len(self._rows):
                self._rows.pop(idx)
        self._refresh_rows()

    def _save(self):
        self.registry.set_candidates(
            self.profile.client,
            [c.rel for c in self._rows],
            {c.rel: c.kind for c in self._rows},
        )
        self._win.destroy()


class ClientPage(tk.Frame):
    """一个客户端标签页（CodeBuddy 含 IDE/CLI 子源；WorkBuddy 单源）。"""

    def __init__(self, master, fonts, registry: ProfileRegistry, store: BackupStore,
                 group: str, on_status=None):
        super().__init__(master, bg=COLORS["bg"], bd=0, highlightthickness=0)
        self.fonts = fonts
        self.registry = registry
        self.store = store
        self.group = group
        self.on_status = on_status
        self.profiles = registry.profiles_for_group(group)
        self.profile: SourceProfile = self.profiles[0]
        self._items: list[CredentialItem] = []
        self._checked: dict[str, bool] = {}
        self._row_iid: dict[str, str] = {}
        self._backup_rows: dict[str, str] = {}  # iid -> name

        self._build_ui()
        self.refresh_all()

    # ---------- 布局 ----------
    def _build_ui(self):
        c = COLORS
        self.configure(bg=c["bg"])

        # 顶部源工具条
        bar = tk.Frame(self, bg=c["card"], highlightbackground=c["border"], highlightthickness=1)
        bar.pack(fill="x", padx=16, pady=(12, 8))
        inner = tk.Frame(bar, bg=c["card"])
        inner.pack(fill="x", padx=14, pady=10)
        tk.Label(inner, text=self.profiles[0].title if len(self.profiles) == 1 else self.group.title(),
                 bg=c["card"], fg=c["text"], font=self.fonts["body_bold"]).pack(side="left")
        tk.Label(inner, text="源：", bg=c["card"], fg=c["sub"], font=self.fonts["body"]).pack(side="left", padx=(16, 0))
        if len(self.profiles) > 1:
            self._src_var = tk.StringVar(value=self.profile.client)
            cb = ttk.Combobox(
                inner, textvariable=self._src_var, state="readonly", width=22, font=self.fonts["body"],
                values=[p.client for p in self.profiles],
            )
            cb.pack(side="left")
            cb.bind("<<ComboboxSelected>>", self._on_source_changed)
        else:
            tk.Label(inner, text=self.profile.client, bg=c["card"], fg=c["text"], font=self.fonts["body"]).pack(side="left")
        self._root_lbl = tk.Label(inner, text="", bg=c["card"], fg=c["sub"], font=self.fonts["small"], anchor="w")
        self._root_lbl.pack(side="left", padx=(12, 0), fill="x", expand=True)
        create_button(inner, "编辑源路径…", "ghost", self._edit_root, font=self.fonts["body"], padx=8).pack(side="right")
        create_button(inner, "管理候选…", "ghost", self._manage_candidates, font=self.fonts["body"], padx=8).pack(side="right", padx=6)
        create_button(inner, "刷新", "ghost", self.refresh_all, font=self.fonts["body"], padx=10).pack(side="right")

        # 中部双栏主体
        body = tk.Frame(self, bg=c["bg"])
        body.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # --- 左栏：本地凭证 ---
        left = tk.Frame(body, bg=c["bg"])
        left.pack(side="left", fill="both", expand=True)
        lhead = SectionTitle(left, "本地凭证", self.fonts)
        lhead.pack(fill="x")
        self._local_count = tk.Label(lhead, text="", bg=c["bg"], fg=c["sub"], font=self.fonts["small"])
        self._local_count.pack(side="right")
        self._local_zone = tk.Frame(left, bg=c["bg"])
        self._local_zone.pack(fill="both", expand=True, pady=(6, 0))
        self._local_card = tk.Frame(self._local_zone, bg=c["card"], highlightbackground=c["border"], highlightthickness=1)
        self._local_card.pack(fill="both", expand=True)
        self._local_tree = SimpleTree(
            self._local_card, columns=("sel", "kind", "rel", "size"),
            headings=("", "类型", "相对路径", "大小"),
            widths=(36, 52, 300, 90), fonts=self.fonts,
        )
        self._local_tree.tag_configure("ok", foreground=c["text"])
        self._local_tree.tag_configure("miss", foreground=c["gray_dot"])
        self._local_tree.bind("<Button-1>", self._on_local_click)
        self._empty_lbl = tk.Label(
            self._local_zone, text="未检测到登录凭证\n请确认该客户端已在本机登录，或点右上角“管理候选”调整检测范围。",
            bg=c["bg"], fg=c["sub"], font=self.fonts["body"], justify="center",
        )
        lf = tk.Frame(left, bg=c["bg"])
        lf.pack(fill="x", pady=(4, 0))
        create_button(lf, "全选存在项", "ghost", self._check_all, font=self.fonts["body"], padx=8).pack(side="left")
        create_button(lf, "清除勾选", "ghost", self._check_none, font=self.fonts["body"], padx=8).pack(side="left", padx=6)

        # --- 中缝操作区 ---
        mid = tk.Frame(body, bg=c["bg"], width=150)
        mid.pack(side="left", fill="y", padx=16)
        mid.pack_propagate(False)
        tk.Frame(mid, bg=c["bg"], height=40).pack()
        self._save_btn = create_button(mid, "→  保存", "primary", self.action_save, font=self.fonts["body_bold"], width=12, pady=10)
        self._save_btn.pack(pady=6)
        tk.Label(mid, text="保存到备份列表", bg=c["bg"], fg=c["sub"], font=self.fonts["small"]).pack()
        tk.Frame(mid, bg=c["bg"], height=26).pack()
        self._write_btn = create_button(mid, "←  写入", "danger", self.action_write, font=self.fonts["body_bold"], width=12, pady=10)
        self._write_btn.pack(pady=6)
        tk.Label(mid, text="还原到本地", bg=c["bg"], fg=c["sub"], font=self.fonts["small"]).pack()
        tk.Frame(mid, bg=c["bg"], height=26).pack()
        self._clear_btn = create_button(mid, "写入空", "danger", self.action_empty, font=self.fonts["body_bold"], width=12, pady=10)
        self._clear_btn.pack(pady=6)
        tk.Label(mid, text="清除本地凭证\n用于登录新账号", bg=c["bg"], fg=c["sub"], font=self.fonts["small"], justify="center").pack()

        # --- 右栏：已备份凭证 ---
        right = tk.Frame(body, bg=c["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(0, 0))
        rhead = SectionTitle(right, "已备份的凭证", self.fonts)
        rhead.pack(fill="x")
        self._backup_count = tk.Label(rhead, text="", bg=c["bg"], fg=c["sub"], font=self.fonts["small"])
        self._backup_count.pack(side="right")
        self._backup_zone = tk.Frame(right, bg=c["bg"])
        self._backup_zone.pack(fill="both", expand=True, pady=(6, 0))
        card_r = tk.Frame(self._backup_zone, bg=c["card"], highlightbackground=c["border"], highlightthickness=1)
        card_r.pack(fill="both", expand=True)
        self._backup_tree = SimpleTree(
            card_r, columns=("name", "files", "size", "time"),
            headings=("账号", "文件数", "大小", "备份时间"),
            widths=(120, 70, 90, 150), fonts=self.fonts,
        )
        self._backup_card = card_r
        self._empty_r = tk.Label(
            self._backup_zone, text="暂无备份\n使用左侧勾选“→ 保存”即可把当前登录凭证存入 user/ 目录。",
            bg=c["bg"], fg=c["sub"], font=self.fonts["body"], justify="center",
        )
        rbar = tk.Frame(right, bg=c["bg"])
        rbar.pack(fill="x", pady=(4, 0))
        create_button(rbar, "重命名", "ghost", self.action_rename, font=self.fonts["body"], padx=8).pack(side="right", padx=6)
        create_button(rbar, "删除备份", "ghost", self.action_delete, font=self.fonts["body"], padx=8).pack(side="right", padx=6)
        create_button(rbar, "← 写入所选", "default", self.action_write, font=self.fonts["body"], padx=10).pack(side="left")
        create_button(rbar, "在资源管理器中打开", "ghost", self._open_backup_dir, font=self.fonts["body"], padx=8).pack(side="left", padx=6)

    # ---------- 数据刷新 ----------
    def refresh_all(self):
        self.refresh_root_label()
        self.refresh_local()
        self.refresh_backups()

    def refresh_root_label(self):
        self._root_lbl.config(text=str(self.profile.root))

    def _on_source_changed(self, _e=None):
        client = self._src_var.get()
        p = self.registry.profile(client)
        if p:
            self.profile = p
            self.refresh_all()

    def refresh_local(self):
        tree = self._local_tree
        tree.delete(*tree.get_children())
        self._items = self.profile.detect()
        self._row_iid = {}
        existing = 0
        for i, item in enumerate(self._items):
            iid = str(i)
            self._row_iid[item.rel] = iid
            if item.exists:
                existing += 1
                self._checked[item.rel] = self._checked.get(item.rel, True)
            else:
                self._checked[item.rel] = False
            kind = "目录" if item.kind == "dir" else "文件"
            size = fmt_size(item.size) if item.exists else "缺失"
            tree.insert(
                "", "end", iid=iid,
                values=(CHECKED if self._checked[item.rel] else UNCHECKED, kind, item.rel, size),
                tags=("ok" if item.exists else "miss"),
            )
        self._local_count.config(text=f"{existing}/{len(self._items)} 项")
        if existing:
            self._local_card.pack(fill="both", expand=True, pady=(6, 0))
            self._empty_lbl.pack_forget()
        else:
            self._local_card.pack_forget()
            self._empty_lbl.pack(fill="both", expand=True, pady=(6, 0))

    def refresh_backups(self):
        tree = self._backup_tree
        tree.delete(*tree.get_children())
        self._backup_rows = {}
        backups = self.store.list_backups(self.profile.client)
        backups.sort(key=lambda m: m.created_at, reverse=True)
        for idx, m in enumerate(backups):
            iid = str(idx)
            total = sum(f.size for f in m.files)
            tree.insert("", "end", iid=iid, values=(m.name, len(m.files), fmt_size(total), fmt_dt(m.created_at)))
            self._backup_rows[iid] = m.name
        self._backup_count.config(text=f"{len(backups)} 个")
        if backups:
            self._backup_card.pack(fill="both", expand=True, pady=(6, 0))
            self._empty_r.pack_forget()
        else:
            self._backup_card.pack_forget()
            self._empty_r.pack(fill="both", expand=True, pady=(6, 0))

    # ---------- 本地勾选交互 ----------
    def _on_local_click(self, event):
        tree = self._local_tree
        region = tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = tree.identify_column(event.x)
        if col != "#1":  # 仅点击勾选列
            return
        row = tree.identify_row(event.y)
        if not row:
            return
        iid = int(row)
        item = self._items[iid]
        if not item.exists:
            return
        self._checked[item.rel] = not self._checked[item.rel]
        tree.set(row, "sel", CHECKED if self._checked[item.rel] else UNCHECKED)

    def _check_all(self):
        self._apply_check(True)

    def _check_none(self):
        self._apply_check(False)

    def _apply_check(self, value: bool):
        for item in self._items:
            if item.exists:
                self._checked[item.rel] = value
        tree = self._local_tree
        for rel, iid in self._row_iid.items():
            if self._checked.get(rel, False):
                tree.set(iid, "sel", CHECKED)
            else:
                tree.set(iid, "sel", UNCHECKED)

    def _checked_existing_rels(self) -> list[str]:
        return [rel for rel, ok in self._checked.items() if ok]

    # ---------- 操作：保存 / 写入 / 写入空 ----------
    def _status(self, text: str, ok: bool = True):
        if self.on_status:
            self.on_status(text, ok)

    def _ensure_local_exist(self) -> list[str] | None:
        rels = self._checked_existing_rels()
        exists = [r for r in rels if r in self._row_iid]
        if not exists:
            info(self, self.fonts, "没有可操作的凭证", "请先在左侧勾选存在于本机的凭证文件。")
            return None
        return exists

    def action_save(self):
        rels = self._ensure_local_exist()
        if rels is None:
            return
        dlg = BackupDialog(self, self.fonts, self.store, self.profile, self._items, set(rels))
        result = dlg.exec()
        if not result:
            return
        name, checked_rels = result
        try:
            manifest, missing = create_backup(self.store, self.profile, name, checked_rels)
        except BackupError as exc:
            error(self, self.fonts, "备份失败", str(exc))
            return
        res = OperationResult(ok=True, message=f"账号“{manifest.name}”已保存到 user/ 目录。")
        for mf in manifest.files:
            res.add_success(f"已备份 {mf.rel}")
        for rel in missing:
            res.add_fail(f"跳过缺失项 {rel}")
        show_result(self, self.fonts, "保存完成", res)
        self._status(f"已保存账号“{manifest.name}”（{len(manifest.files)} 项）。")
        self.refresh_backups()

    def _current_existing_rels(self) -> list[str]:
        return [i.rel for i in self.profile.detect() if i.exists]

    def _handle_missing_guard(self) -> bool:
        """若当前本地凭证未出现在任何备份中，则弹三选一（备份并继续/忽略/取消）。
        返回 True 表示允许继续执行后续操作。"""
        rels = self._current_existing_rels()
        if current_is_backed_up(self.store, self.profile, rels):
            return True
        choice = choice3(
            self, self.fonts, "当前登录态尚未备份",
            "当前本地凭证未出现在任何备份中。继续操作会使当前登录凭证丢失，"
            "建议先保存一份。",
            "备份当前并继续", "忽略并继续", "取消",
        )
        if choice == "a":  # 备份当前并继续
            dlg = BackupDialog(self, self.fonts, self.store, self.profile, self._items, set(rels))
            result = dlg.exec()
            if not result:
                return False
            try:
                create_backup(self.store, self.profile, result[0], result[1])
            except BackupError as exc:
                error(self, self.fonts, "备份失败", str(exc))
                return False
            self.refresh_backups()
            return True
        if choice == "c":
            return False
        return True  # b：忽略并继续

    def _selected_backup(self) -> BackupManifest | None:
        sel = self._backup_tree.selection()
        if not sel:
            info(self, self.fonts, "未选择备份", "请在右侧列表选中一个要写入的备份。")
            return None
        name = self._backup_rows.get(sel[0], "")
        return self.store.read_manifest(name) if name else None

    def action_write(self):
        manifest = self._selected_backup()
        if manifest is None:
            return
        if not self._handle_missing_guard():
            return
        n = len(manifest.files)
        total = sum(f.size for f in manifest.files)
        ok = confirm(
            self, self.fonts, "写入账号凭证",
            f"将用备份“{manifest.name}”（{n} 项 / {fmt_size(total)}）覆盖本地源目录：\n"
            f"{manifest.source_root}\n\n"
            "该操作会先删除本地现有文件再写入。若客户端正在运行导致文件被占用，会中断并提示。\n"
            "建议：先退出相应客户端再执行。",
            ok_text="开始写入", cancel_text="取消", danger=True,
        )
        if not ok:
            return
        res = write_from_backup(self.store, manifest)
        show_result(self, self.fonts, "写入结果", res)
        if res.ok:
            self._status(f"已写入账号“{manifest.name}”，重启客户端后登录态生效。")
        else:
            self._status("写入未完成，请查看失败原因。", ok=False)
        self.refresh_all()

    def action_empty(self):
        rels = self._ensure_local_exist()
        if rels is None:
            return
        if not self._handle_missing_guard():
            return
        ok = confirm(
            self, self.fonts, "写入空（清除本地凭证）",
            f"将从源目录删除 {len(rels)} 个本地凭证文件/目录：\n{self.profile.root}\n\n"
            "删除后客户端将回到未登录状态。重启客户端并登录新账号，即可再次点“→ 保存”备份新账号。",
            ok_text="确认清除", cancel_text="取消", danger=True,
        )
        if not ok:
            return
        res = clear_to_empty(self.profile.root, rels)
        show_result(self, self.fonts, "写入空完成", res)
        if res.ok:
            self._status("已写入空。请打开客户端登录新账号。")
        else:
            self._status("清除未完成，请查看失败原因。", ok=False)
        self.refresh_all()

    # ---------- 备份管理 ----------
    def action_delete(self):
        manifest = self._selected_backup()
        if manifest is None:
            return
        ok = confirm(
            self, self.fonts, "删除备份",
            f"将从 user/ 目录永久删除备份“{manifest.name}”（{len(manifest.files)} 项）。\n此操作不可恢复。",
            ok_text="删除", cancel_text="取消", danger=True,
        )
        if ok:
            self.store.delete_backup(manifest.name)
            self._status(f"已删除备份“{manifest.name}”。")
            self.refresh_backups()

    def action_rename(self):
        manifest = self._selected_backup()
        if manifest is None:
            return
        new = simpledialog.askstring("重命名备份", "新账号名：", initialvalue=manifest.name, parent=self)
        if not new:
            return
        try:
            self.store.rename_backup(manifest.name, new)
        except Exception as exc:
            error(self, self.fonts, "重命名失败", str(exc))
            return
        self._status(f"已重命名为“{new}”。")
        self.refresh_backups()

    def _open_backup_dir(self):
        os.startfile(self.store.user_dir)  # noqa: S606 Windows 资源管理器

    # ---------- 源配置 ----------
    def _edit_root(self):
        new = simpledialog.askstring(
            "编辑源路径", "客户端数据目录：", initialvalue=str(self.profile.root), parent=self,
        )
        if not new:
            return
        self.registry.set_root(self.profile.client, new)
        self.profile.root = Path(new)
        self.refresh_all()

    def _manage_candidates(self):
        dlg = ManageCandidatesDialog(self, self.fonts, self.registry, self.profile)
        dlg.exec()
        # 重新读取以反映可能变化
        refreshed = self.registry.profile(self.profile.client)
        if refreshed:
            self.profile = refreshed
            self.refresh_local()
