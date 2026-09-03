"""MultiBuddy 程序入口：初始化目录、日志与用户配置，启动主窗口。

运行方式（在项目根目录）：
    python -m app.main
或双击双击本文件（脚本模式自动加入项目根到 sys.path）。
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.sources import ProfileRegistry  # noqa: E402
from app.core.store import BackupStore  # noqa: E402
from app.ui.app_window import AppWindow  # noqa: E402


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _setup_logging(root: Path) -> None:
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
        ],
    )
    logging.getLogger("multibuddy").info("MultiBuddy 启动")


def main() -> None:
    project_root = _project_root()
    user_dir = project_root / "user"
    config_file = user_dir / "config.json"
    _setup_logging(project_root)

    registry = ProfileRegistry(config_file)
    store = BackupStore(user_dir)

    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as exc:  # 无图形环境时给出明确提示
        print(f"无法启动图形界面：{exc}", file=sys.stderr)
        sys.exit(1)
    app = AppWindow(root, registry, store)
    app.run()


if __name__ == "__main__":
    main()
