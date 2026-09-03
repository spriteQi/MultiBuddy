"""MultiBuddy 命令行模式（独立入口）：保存 / 写入 / 写入空 / 备份管理。

不带参数运行进入“数字菜单”交互模式（单字符选择）；
带子命令则单次执行，如：
    python -m app.main_cli list
    python -m app.main_cli save codebuddy-cn-ide 账号A
    python -m app.main_cli write codebuddy-cn-ide 账号A        # 交互确认
    python -m app.main_cli empty codebuddy-cn-ide --yes        # 非交互清空
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.backup import BackupError, create_backup  # noqa: E402
from app.core.model import CLIENT_IDS  # noqa: E402
from app.core.restore import (  # noqa: E402
    clear_to_empty,
    current_is_backed_up,
    write_from_backup,
)
from app.core.sources import ProfileRegistry  # noqa: E402
from app.core.store import BackupStore  # noqa: E402

CLIENT_HELP = " / ".join(CLIENT_IDS)
CLIENT_ALIASES = {
    "ide": "codebuddy-cn-ide",
    "cli": "codebuddy-cli",
    "wb": "workbuddy",
    "workbuddy": "workbuddy",
    "codebuddy-ide": "codebuddy-cn-ide",
}


def _resolve_client(raw: str) -> str:
    if raw in CLIENT_IDS:
        return raw
    if raw in CLIENT_ALIASES:
        return CLIENT_ALIASES[raw]
    raise SystemExit(f"未知客户端：{raw}（可用：{CLIENT_HELP}，别名 ide/cli/wb）")


def _setup() -> tuple[Path, ProfileRegistry, BackupStore]:
    root = Path(__file__).resolve().parents[1]
    user_dir = root / "user"
    config_file = user_dir / "config.json"
    registry = ProfileRegistry(config_file)
    store = BackupStore(user_dir)
    return root, registry, store


class CliExit(Exception):
    """命令中断：单命令模式据此转为退出码，交互模式据此返回主菜单。"""

    def __init__(self, code: int = 0):
        super().__init__(code)
        self.code = code


def _ask(text: str) -> str:
    try:
        return input(text).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _read_choice(prompt: str = "请选择 > ") -> str:
    """单键读取数字选择（Windows 下无需回车；非交互时回退为整行输入）。"""
    print(prompt, end="", flush=True)
    try:
        if sys.platform == "win32" and sys.stdin.isatty():
            import msvcrt  # Windows 专用，无缓冲读键

            while True:
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    print()
                    return ""  # 回车 = 空选择（默认不操作）
                if ch in ("\x00", "\xe0"):  # 方向键/功能键前导字节，吞掉后续字节
                    msvcrt.getwch()
                    continue
                if ch == "\x08":  # 退格忽略
                    continue
                if ch == "\x03":  # Ctrl+C
                    raise KeyboardInterrupt
                if ch.isdigit() or ch.isalpha():
                    print()
                    return ch.lower()
                # 其它控制字符忽略
        else:
            line = input().strip().lstrip("\ufeff").lower()
            return line[:1] if line else ""
    except (EOFError, KeyboardInterrupt):
        print()
        return "0"


def _prompt_yn(text: str, default: bool = False) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    ans = _ask(text + suffix).lower()
    if not ans:
        return default
    return ans in ("y", "yes")


def _clear_screen() -> None:
    """每次展示菜单前清屏（交互终端有效；重定向/管道时跳过以免污染输出）。"""
    if not sys.stdin.isatty():
        return
    if os.name == "nt":
        os.system("cls")
    else:
        print("\x1b[2J\x1b[H", end="")


def _missing_root_hint(profile) -> str:
    return (
        f"  ✗ 源目录不存在：{profile.root}\n"
        "    请先安装并登录对应客户端，或在界面“编辑源路径…”/ config.json 中修正。"
    )


def _list_backups(store, client) -> str:
    """生成“已备份”区块文本：区块上方恒有 --- 横线分割行，与本地凭证信息区分。"""
    backups = store.list_backups(client)
    lines = ["  ----------", "  已备份: " + ("无" if not backups else "")]
    for m in sorted(backups, key=lambda x: x.created_at, reverse=True):
        total = sum(f.size for f in m.files)
        lines.append(f"    - {m.name}（{m.created_at[:16]}，{len(m.files)} 项 / {total} B）")
    return "\n".join(lines)


# ---------- 各子命令 ----------
def cmd_list(args, registry, store):
    if args.client:
        clients = [_resolve_client(args.client)]
    else:
        clients = list(CLIENT_IDS)
    for client in clients:
        profile = registry.profile(client)
        if profile is None:
            continue
        line = f"[{client}] {profile.title}\n  源目录: {profile.root}"
        if not profile.root.is_dir():
            # 目录不存在：直接提示，不再逐项列出“缺失”
            line += "\n" + _missing_root_hint(profile)
        else:
            items = profile.detect()
            exists = [i for i in items if i.exists]
            line += f"\n  本地凭证: {len(exists)}/{len(items)} 项（存在：{', '.join(i.rel for i in exists) or '无'}）"
        print(line, "\n" + _list_backups(store, client), "\n")


def cmd_detect(args, registry, store):
    profile = registry.profile(args.client)
    if not profile.root.is_dir():
        print(f"{profile.title} 源目录: {profile.root}")
        print(_missing_root_hint(profile))
        return
    items = profile.detect()
    print(f"{profile.title} 源目录: {profile.root}")
    for item in items:
        mark = "存在" if item.exists else "缺失"
        size = item.size if item.exists else "-"
        print(f"  [{mark:2}] {item.kind:4} {item.rel:<58} {size}")


def cmd_save(args, registry, store):
    profile = registry.profile(args.client)
    if not profile.root.is_dir():
        print(f"源目录不存在：{profile.root}，无法保存。", file=sys.stderr)
        raise CliExit(1)
    rels = args.rel or None
    items = profile.detect()
    exist_rel = {i.rel for i in items if i.exists}
    if rels is None:
        targets = sorted(exist_rel)
    else:
        targets = []
        for rel in rels:
            if rel not in exist_rel:
                print(f"警告：{rel} 不存在或不在清单中，已跳过", file=sys.stderr)
            else:
                targets.append(rel)
    if not targets:
        print("未检测到任何本地凭证，无法保存。", file=sys.stderr)
        raise CliExit(1)
    try:
        manifest, missing = create_backup(store, profile, args.name, targets)
    except BackupError as exc:
        print(f"备份失败：{exc}", file=sys.stderr)
        raise CliExit(1)
    for mf in manifest.files:
        print(f"已备份 {mf.rel}")
    for rel in missing:
        print(f"跳过缺失项 {rel}", file=sys.stderr)
    print(f"完成：账号“{manifest.name}”已保存到 user/ 目录。")


def cmd_write(args, registry, store):
    profile = registry.profile(args.client)
    if not profile.root.is_dir():
        print(f"源目录不存在：{profile.root}，无法写入。请先确认客户端数据目录。", file=sys.stderr)
        raise CliExit(1)
    manifest = next((m for m in store.list_backups(args.client) if m.name == args.name), None)
    if manifest is None:
        print(f"备份不存在：{args.client} / {args.name}", file=sys.stderr)
        raise CliExit(1)
    current = [i.rel for i in profile.detect() if i.exists]
    if current and not current_is_backed_up(store, profile, current):
        print("提示：当前本地凭证尚未备份，写入后当前登录态将丢失。")
        choice = _ask("[b] 先备份当前 / [i] 忽略并继续 / [c] 取消（默认 c）: ").lower()
        if choice == "b":
            new_name = _ask("为新账号输入备份名（留空取消）: ")
            if not new_name:
                print("已取消。", file=sys.stderr)
                raise CliExit(0)
            try:
                create_backup(store, profile, new_name, current)
            except BackupError as exc:
                print(f"备份当前失败：{exc}", file=sys.stderr)
                raise CliExit(1)
            print(f"已先备份当前登录态为“{new_name}”，继续写入……")
        elif choice != "i":
            print("已取消。")
            raise CliExit(0)
    if not args.yes:
        if not _prompt_yn(
            f"将用备份“{manifest.name}”（{len(manifest.files)} 项）覆盖源目录 {manifest.source_root}，是否继续",
            default=False,
        ):
            print("已取消。")
            raise CliExit(0)
    res = write_from_backup(store, manifest)
    for step in res.steps:
        print(step)
    if res.ok:
        print("完成：重启客户端后登录态生效。")
    else:
        print("写入未完成，请参考上方失败原因（如文件占用，请先退出客户端）。", file=sys.stderr)
        raise CliExit(1)


def cmd_empty(args, registry, store):
    profile = registry.profile(args.client)
    if not profile.root.is_dir():
        print(f"源目录不存在：{profile.root}，没有可清除的凭证。", file=sys.stderr)
        raise CliExit(1)
    items = profile.detect()
    if args.rel:
        exist = {i.rel for i in items if i.exists}
        rels = [r for r in args.rel if r in exist]
    else:
        rels = [i.rel for i in items if i.exists]
    if not rels:
        print("没有可清除的本地凭证。", file=sys.stderr)
        raise CliExit(1)
    if not current_is_backed_up(store, profile, rels):
        print("提示：当前本地凭证尚未备份，清除后当前登录态将丢失。")
        if not args.yes and not _prompt_yn("仍要清除（建议先用 save 备份）", default=False):
            print("已取消。")
            raise CliExit(0)
    if not args.yes:
        if not _prompt_yn(f"将删除 {len(rels)} 个本地凭证文件/目录：{', '.join(rels)}", default=False):
            print("已取消。")
            raise CliExit(0)
    res = clear_to_empty(profile.root, rels)
    for step in res.steps:
        print(step)
    if res.ok:
        print("完成：客户端将回到未登录状态，请登录新账号后再用 save 备份。")
    else:
        print("清除未完成，请参考上方失败原因（如文件占用，请先退出客户端）。", file=sys.stderr)
        raise CliExit(1)


def cmd_delete(args, registry, store):
    manifest = next((m for m in store.list_backups(args.client) if m.name == args.name), None)
    if manifest is None:
        print(f"备份不存在：{args.client} / {args.name}", file=sys.stderr)
        raise CliExit(1)
    if not args.yes:
        if not _prompt_yn(f"将永久删除备份“{manifest.name}”（{len(manifest.files)} 项）", default=False):
            print("已取消。")
            raise CliExit(0)
    store.delete_backup(args.name)
    print(f"已删除备份“{args.name}”。")


def cmd_rename(args, registry, store):
    try:
        store.rename_backup(args.old, args.new)
    except Exception as exc:
        print(f"重命名失败：{exc}", file=sys.stderr)
        raise CliExit(1)
    print(f"已重命名为“{args.new}”。")


def cmd_info(args, registry, store):
    manifest = next((m for m in store.list_backups(args.client) if m.name == args.name), None)
    if manifest is None:
        print(f"备份不存在：{args.client} / {args.name}", file=sys.stderr)
        raise CliExit(1)
    print(f"账号   : {manifest.name}")
    print(f"客户端 : {manifest.client}")
    print(f"时间   : {manifest.created_at}")
    print(f"源目录 : {manifest.source_root}")
    print("文件:")
    for mf in manifest.files:
        print(f"  [{mf.type}] {mf.rel}  ({mf.size} B, sha256 {mf.sha256[:12]}…)")
        for child in mf.children[:8]:
            print(f"      - {child.rel} ({child.size} B)")
        if len(mf.children) > 8:
            print(f"      … 等 {len(mf.children)} 个内部文件")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="multibuddy-cli",
        description="CodeBuddy / WorkBuddy 账号凭证保存切换工具（命令行）",
    )
    sub = parser.add_subparsers(dest="command")

    def add_client(p):
        p.add_argument(
            "client", help=f"客户端：{CLIENT_HELP}（别名 ide / cli / wb）",
        )

    p = sub.add_parser("list", help="查看各客户端本地凭证与已备份账号")
    p.add_argument("client", nargs="?", help="仅查看某客户端")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("detect", help="检测本地凭证文件存在情况")
    add_client(p)
    p.set_defaults(func=cmd_detect)

    p = sub.add_parser("save", help="把当前本地凭证保存为账号备份（默认全部存在项）")
    add_client(p)
    p.add_argument("name", help="账号名")
    p.add_argument("--rel", action="append", help="仅备份指定相对路径，可多次指定")
    p.set_defaults(func=cmd_save)

    p = sub.add_parser("write", help="把备份写回本地源位置（覆盖）")
    add_client(p)
    p.add_argument("name", help="账号名")
    p.add_argument("--yes", action="store_true", help="跳过确认（非交互）")
    p.set_defaults(func=cmd_write)

    p = sub.add_parser("empty", help="写入空：清除本地凭证，用于登录新账号")
    add_client(p)
    p.add_argument("--rel", action="append", help="仅清除指定相对路径，可多次指定")
    p.add_argument("--yes", action="store_true", help="跳过确认（非交互）")
    p.set_defaults(func=cmd_empty)

    p = sub.add_parser("delete", help="删除一个备份")
    add_client(p)
    p.add_argument("name", help="账号名")
    p.add_argument("--yes", action="store_true", help="跳过确认（非交互）")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("rename", help="重命名备份")
    add_client(p)
    p.add_argument("old", help="原账号名")
    p.add_argument("new", help="新账号名")
    p.set_defaults(func=cmd_rename)

    p = sub.add_parser("info", help="查看备份清单详情")
    add_client(p)
    p.add_argument("name", help="账号名")
    p.set_defaults(func=cmd_info)
    return parser


def _pick_backup(store, client):
    """列出该客户端已备份账号并让用户选一个（单字符数字）。"""
    backups = store.list_backups(client)
    backups.sort(key=lambda m: m.created_at, reverse=True)
    if not backups:
        print("  该客户端暂无备份。")
        return None
    print("  已备份账号：")
    for i, m in enumerate(backups, 1):
        total = sum(f.size for f in m.files)
        print(f"    {i}. {m.name}（{m.created_at[:16]}，{len(m.files)} 项 / {total} B）")
    ch = _read_choice("  按序号键选择（回车取消）> ")
    if not ch.isdigit():
        return None
    idx = int(ch) - 1
    if not 0 <= idx < len(backups):
        print("  序号无效。")
        return None
    return backups[idx]


def _interactive(registry, store) -> None:
    """无参数进入：数字菜单交互，单字符选择，循环执行直到输入 0 退出。"""
    clients = list(CLIENT_IDS)
    cur = 0
    while True:
        _clear_screen()
        client = clients[cur]
        profile = registry.profile(client)
        ok_root = profile.root.is_dir()
        items = profile.detect() if ok_root else []
        exist = sum(1 for i in items if i.exists)
        backups = store.list_backups(client)
        print(f"MultiBuddy CLI 交互模式 · 按数字键直接操作 · 0 退出")
        print("=" * 56)
        title = f"目标客户端：{profile.title}  [{client}]"
        if not ok_root:
            title += "  ※ 源目录不存在"
        print(title)
        print(f"  源目录：{profile.root}")
        if ok_root:
            print(f"  本地凭证 {exist}/{len(items)} 项 · 已备份 {len(backups)} 个账号")
        print("-" * 56)
        print(" 1 切换客户端      2 查看本地凭证     3 检测凭证文件")
        print(" 4 保存当前凭证    5 写入备份到本地   6 写入空（登录新账号）")
        print(" 7 删除备份        8 重命名备份       9 查看备份详情")
        print(" 0 退出")
        choice = _read_choice()

        if choice == "0":
            print("再见。")
            return
        if choice == "1":
            print("  选择客户端：")
            for i, c in enumerate(clients, 1):
                p = registry.profile(c)
                print(f"    {i}. {c}（{p.title}）")
            c = _read_choice("    > ")
            if c.isdigit() and 1 <= int(c) <= len(clients):
                cur = int(c) - 1
            continue
        if choice == "2":
            cmd_list(SimpleNamespace(client=client), registry, store)
            continue
        if choice == "3":
            cmd_detect(SimpleNamespace(client=client), registry, store)
            continue
        if choice == "4":
            name = _ask("  账号名（回车取消）> ")
            if not name:
                continue
            try:
                cmd_save(SimpleNamespace(client=client, name=name, rel=None), registry, store)
            except CliExit:
                pass
            continue
        if choice == "5":
            m = _pick_backup(store, client)
            if m:
                try:
                    cmd_write(SimpleNamespace(client=client, name=m.name, yes=False), registry, store)
                except CliExit:
                    pass
            continue
        if choice == "6":
            try:
                cmd_empty(SimpleNamespace(client=client, rel=None, yes=False), registry, store)
            except CliExit:
                pass
            continue
        if choice == "7":
            m = _pick_backup(store, client)
            if m:
                try:
                    cmd_delete(SimpleNamespace(client=client, name=m.name, yes=False), registry, store)
                except CliExit:
                    pass
            continue
        if choice == "8":
            m = _pick_backup(store, client)
            if m:
                new = _ask(f"  将“{m.name}”重命名为（回车取消）> ")
                if new:
                    try:
                        cmd_rename(SimpleNamespace(client=client, old=m.name, new=new), registry, store)
                    except CliExit:
                        pass
            continue
        if choice == "9":
            m = _pick_backup(store, client)
            if m:
                cmd_info(SimpleNamespace(client=client, name=m.name), registry, store)
            continue
        print("  无效选择，请输入菜单前的数字。")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()

    if not argv:
        # 无参数进入：数字菜单交互模式
        _, registry, store = _setup()
        _interactive(registry, store)
        return 0

    # 带参数的单命令模式：参数错误保留非零退出码
    args = parser.parse_args(argv)
    raw = getattr(args, "client", None)
    if raw:
        args.client = _resolve_client(raw)  # 未知客户端会 SystemExit(码 1)
    _, registry, store = _setup()
    try:
        args.func(args, registry, store)
    except CliExit as exc:
        return exc.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
