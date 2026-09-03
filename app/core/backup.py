"""备份引擎：将源目录下勾选的凭证镜像备份到 user/<账号名>/，原子落盘。"""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from .model import BackupManifest, Candidate, ManifestFile, SourceProfile, snapshot_entry
from .store import BackupStore


class BackupError(RuntimeError):
    """备份失败（缺少可用凭证等）。"""


def _copy_entry(src_root: Path, files_dst: Path, mf: ManifestFile) -> None:
    """按 manifest 条目类型把源内容复制到 files_dst 下（目标位置如存在则先移除）。"""
    src_path = src_root / mf.rel
    dst_path = files_dst / mf.rel
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    if dst_path.exists() or dst_path.is_symlink():
        if dst_path.is_dir() and not dst_path.is_symlink():
            shutil.rmtree(dst_path, ignore_errors=True)
        else:
            dst_path.unlink()
    if mf.type == "file":
        shutil.copy2(src_path, dst_path)
    else:
        shutil.copytree(src_path, dst_path)


def _candidate_for(root: Path, rel: str) -> Candidate | None:
    """把用户传入的 rel 规整为候选（优先匹配 profile 内定义，其次按实际类型推断）。"""
    src = root / rel
    if src.is_file():
        return Candidate(rel, "file")
    if src.is_dir():
        return Candidate(rel, "dir")
    return None


def create_backup(
    store: BackupStore,
    profile: SourceProfile,
    name: str,
    rels: list[str],
    now: str | None = None,
) -> tuple[BackupManifest, list[str]]:
    """备份源根下指定 rel 清单到 user/<name>，返回 (manifest, missing)。

    流程：快照（含 sha256）→ 写临时目录（files/ 镜像 + manifest.json）→ 原子改名；
    同名旧备份仅在全新备份就绪后才被移除，避免留下半成品。
    """
    name = store.validate_name(name)
    root = Path(profile.root)
    cand_by_rel = {c.rel: c for c in profile.candidates}

    # 1) 对勾选清单做快照
    snaps: list[ManifestFile] = []
    missing: list[str] = []
    for rel in rels:
        cand = cand_by_rel.get(rel) or _candidate_for(root, rel)
        snap = snapshot_entry(root, cand) if cand else None
        if snap is None:
            missing.append(rel)
        else:
            snaps.append(snap)

    if not snaps:
        raise BackupError("未检测到任何可备份的凭证文件，备份已取消。")

    final_dir = store.backup_dir(name)
    staging = store.user_dir / f".staging-{uuid.uuid4().hex}"
    try:
        # 2) 先建临时目录再写镜像与清单
        staging.mkdir(parents=True, exist_ok=True)
        files_dst = staging / "files"
        for mf in snaps:
            _copy_entry(root, files_dst, mf)
        resolved_root = str(root.resolve())
        manifest = BackupManifest(
            name=name,
            client=profile.client,
            created_at=now or datetime.now().isoformat(timespec="seconds"),
            source_root=resolved_root,
            files=snaps,
        )
        (staging / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 3) 原子落位：先删旧（此时新备份已完整就绪），再改名
        if final_dir.exists():
            shutil.rmtree(final_dir, ignore_errors=True)
        staging.rename(final_dir)
        return manifest, missing
    except Exception as exc:  # noqa: BLE001 任何失败清理暂存并上抛
        shutil.rmtree(staging, ignore_errors=True)
        msg = f"备份失败：{exc}"
        if isinstance(exc, (OSError, PermissionError)) and "Permission" in str(exc):
            msg += "。部分凭证文件被客户端占用，请先退出 CodeBuddy / WorkBuddy 后重试。"
        raise BackupError(msg) from exc
