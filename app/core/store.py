"""/user 备份存储管理：账号名校验、列表/读取/删除/重命名，manifest 读写。"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .model import BackupManifest

INVALID_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
MANIFEST_NAME = "manifest.json"


class BackupNameError(ValueError):
    """备份账号名不合法。"""


@dataclass
class BackupStore:
    """管理项目 user/ 目录下的所有账号备份。

    每个备份 = user/<账号名>/，内部为 files/（镜像）+ manifest.json。
    """

    user_dir: Path

    def __post_init__(self) -> None:
        self.user_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def validate_name(name: str) -> str:
        name = (name or "").strip()
        if not name:
            raise BackupNameError("账号名不能为空。")
        if name in (".", ".."):
            raise BackupNameError("账号名不合法。")
        if INVALID_NAME_CHARS.search(name):
            raise BackupNameError("账号名不能包含 \\ / : * ? \" < > | 等字符。")
        if len(name) > 64:
            raise BackupNameError("账号名过长（最多 64 字符）。")
        return name

    def backup_dir(self, name: str) -> Path:
        return self.user_dir / self.validate_name(name)

    def files_dir(self, name: str) -> Path:
        return self.backup_dir(name) / "files"

    def manifest_path(self, name: str) -> Path:
        return self.backup_dir(name) / MANIFEST_NAME

    def list_names(self) -> list[str]:
        if not self.user_dir.is_dir():
            return []
        names = []
        for d in self.user_dir.iterdir():
            if d.is_dir() and (d / MANIFEST_NAME).is_file():
                names.append(d.name)
        return sorted(names)

    def read_manifest(self, name: str) -> BackupManifest | None:
        path = self.manifest_path(name)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return BackupManifest.from_dict(data)
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            return None

    def list_backups(self, client: str | None = None) -> list[BackupManifest]:
        """列出全部（或某客户端）备份清单，跳过损坏项。"""
        out = []
        for name in self.list_names():
            m = self.read_manifest(name)
            if m and (client is None or m.client == client):
                out.append(m)
        return out

    def write_manifest(self, manifest: BackupManifest) -> None:
        """落盘 manifest（目录已存在时调用）。"""
        self.manifest_path(manifest.name).write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def delete_backup(self, name: str) -> bool:
        d = self.backup_dir(name)
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            return not d.exists()
        return False

    def rename_backup(self, old: str, new: str) -> None:
        new = self.validate_name(new)
        if old == new:
            return
        dst = self.backup_dir(new)
        if dst.exists():
            raise BackupNameError(f"已存在名为“{new}”的备份。")
        src = self.backup_dir(old)
        if not src.is_dir():
            raise BackupNameError(f"备份“{old}”不存在。")
        src.rename(dst)
        # 同步 manifest 中的 name 字段
        m = self.read_manifest(new)
        if m and m.name != new:
            m.name = new
            self.write_manifest(m)
