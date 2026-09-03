"""还原引擎：←写入（删-写/失败中止）、写入空 clear_to_empty、当前登录态是否已备份判定。"""
from __future__ import annotations

import shutil
from pathlib import Path

from .model import (
    BackupManifest,
    ManifestFile,
    OperationResult,
    SourceProfile,
    entry_current_fingerprint,
    snapshot_entry,
)
from .store import BackupStore

_SKIP_HINT = "（若文件被客户端占用，请先退出相应客户端后重试）"


def _delete_target(path: Path) -> None:
    """删除文件或目录（含软链接），不存在视为成功。"""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _copy_to_target(src: Path, target: Path, mf: ManifestFile) -> None:
    """把备份内的条目复制到源位置（target 需已删除）。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    if mf.type == "file":
        shutil.copy2(src, target)
    else:
        shutil.copytree(src, target)


def write_from_backup(store: BackupStore, manifest: BackupManifest) -> OperationResult:
    """把备份写回源位置：对每个条目先删除源旧文件、删除成功后再写入，失败即中止。

    中止后已完成的条目保留、未处理的保持不变，不做自动回滚，便于排查。
    """
    res = OperationResult(ok=True, message=f"账号“{manifest.name}”写入完成。")
    root = Path(manifest.source_root)
    if not root.is_dir():
        res.add_fail(f"源目录不存在：{root}")
        return res

    for mf in manifest.files:
        # 1) 删除源旧文件
        target = root / mf.rel
        try:
            if target.exists() or target.is_symlink():
                _delete_target(target)
        except OSError as exc:
            res.add_fail(f"无法删除 {mf.rel}：{exc} {_SKIP_HINT}")
            return res

        # 2) 写入备份文件
        src = store.files_dir(manifest.name) / mf.rel
        try:
            _copy_to_target(src, target, mf)
        except OSError as exc:
            res.add_fail(f"写入 {mf.rel} 失败：{exc}")
            return res

        # 3) 还原后校验一致性
        cur = entry_current_fingerprint(root, mf)
        if cur is None or cur != mf.sha256:
            res.add_fail(f"{mf.rel} 还原后校验不一致，请检查文件是否被占用。")
            return res
        res.add_success(f"已写入 {mf.rel}")
    return res


def clear_to_empty(root: Path, rels: list[str]) -> OperationResult:
    """写入空：按 rels 删除源位置中的凭证文件/目录，供登录新账号。

    逐个删除并捕获失败（文件占用为最常见原因），任一失败即中止。
    """
    res = OperationResult(ok=True, message="已清空本地凭证，客户端将回到未登录状态。")
    root = Path(root)
    for rel in rels:
        target = root / rel
        if not (target.exists() or target.is_symlink()):
            res.add_success(f"已跳过（不存在） {rel}")
            continue
        try:
            _delete_target(target)
        except OSError as exc:
            res.add_fail(f"无法删除 {rel}：{exc} {_SKIP_HINT}")
            return res
        res.add_success(f"已删除 {rel}")
    return res


def current_fingerprints(profile: SourceProfile, rels: list[str]) -> dict[str, ManifestFile]:
    """对当前源中指定 rel 计算快照（仅存在项），供"是否已备份"比对。"""
    out: dict[str, ManifestFile] = {}
    root = Path(profile.root)
    cand_by_rel = {c.rel: c for c in profile.candidates}
    for rel in rels:
        cand = cand_by_rel.get(rel)
        snap = snapshot_entry(root, cand) if cand else None
        if snap is not None:
            out[rel] = snap
    return out


def current_is_backed_up(
    store: BackupStore, profile: SourceProfile, rels: list[str], source_root: str | None = None
) -> bool:
    """判定当前本地登录态是否已完整存在于任一备份（同客户端、同源根、指纹一致）。

    用作切换/写入空前的防丢失检查：任一勾选文件找不到指纹一致的备份即视为未备份。
    """
    if not rels:
        return True
    root = str(Path(source_root or profile.root).resolve())
    cur = current_fingerprints(profile, rels)
    if not cur:
        return True
    for m in store.list_backups(profile.client):
        if Path(m.source_root).resolve().as_posix() != Path(root).resolve().as_posix():
            continue
        by_rel = {f.rel: f for f in m.files}
        if all(
            rel in by_rel and by_rel[rel].sha256 == snap.sha256
            for rel, snap in cur.items()
        ):
            return True
    return False
