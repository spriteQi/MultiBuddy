"""MultiBuddy 核心数据模型：客户端源、凭证条目、备份清单与操作结果。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

# 客户端标识：CodeBuddy CN IDE / CodeBuddy CLI / WorkBuddy
CLIENT_IDS = ("codebuddy-cn-ide", "codebuddy-cli", "workbuddy")


def sha256_bytes(data: bytes) -> str:
    """计算字节串的 sha256。"""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """计算单个文件的 sha256。"""
    h = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            block = fp.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def dir_total_size(path: Path) -> int:
    """递归统计目录内所有文件的总字节数（跳过子目录本身）。"""
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


@dataclass
class ChildHash:
    """目录内部某个文件的快照。"""

    rel: str  # 相对所属目录的相对路径（POSIX 分隔符）
    size: int
    sha256: str


@dataclass
class Candidate:
    """源目录下的候选凭证路径。"""

    rel: str   # 相对源根路径（POSIX 分隔符）
    kind: str  # file | dir


@dataclass
class CredentialItem:
    """本地检测出的凭证条目（候选清单在本机的存在情况）。"""

    rel: str
    kind: str    # file | dir
    exists: bool
    size: int = 0  # 文件字节数 / 目录递归总字节数


@dataclass
class SourceProfile:
    """一个客户端源：源根目录 + 候选凭证清单。"""

    client: str  # CLIENT_IDS 之一
    title: str
    root: Path
    candidates: list[Candidate] = field(default_factory=list)
    desc: str = ""

    def detect(self) -> list[CredentialItem]:
        """检测各候选在本机的存在状态（不读取内容）。"""
        items: list[CredentialItem] = []
        for cand in self.candidates:
            p = self.root / cand.rel
            if p.is_file():
                items.append(CredentialItem(cand.rel, "file", True, p.stat().st_size))
            elif p.is_dir():
                items.append(CredentialItem(cand.rel, "dir", True, dir_total_size(p)))
            else:
                items.append(CredentialItem(cand.rel, cand.kind, False, 0))
        return items


@dataclass
class ManifestFile:
    """备份清单中的单个条目（文件或整个目录）。"""

    rel: str
    type: str  # file | dir
    size: int  # file：字节数；dir：递归总字节数
    sha256: str  # file：文件摘要；dir：按 children 计算的递归聚合摘要
    children: list[ChildHash] = field(default_factory=list)  # dir 内部文件明细

    def to_dict(self) -> dict:
        return {
            "rel": self.rel,
            "type": self.type,
            "size": self.size,
            "sha256": self.sha256,
            "children": [{"rel": c.rel, "size": c.size, "sha256": c.sha256} for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ManifestFile":
        children = [
            ChildHash(c["rel"], int(c.get("size", 0)), c["sha256"])
            for c in data.get("children", [])
        ]
        return cls(
            rel=data["rel"],
            type=data.get("type", "file"),
            size=int(data.get("size", 0)),
            sha256=data.get("sha256", ""),
            children=children,
        )


def snapshot_entry(root: Path, cand: Candidate) -> ManifestFile | None:
    """对源根下的候选做快照；不存在返回 None。

    dir 条目递归收集每个文件（rel 为相对该目录），sha256 为聚合摘要。
    """
    src = root / cand.rel
    if cand.kind == "dir" and src.is_dir():
        children: list[ChildHash] = []
        total = 0
        for p in sorted(src.rglob("*"), key=lambda x: x.as_posix()):
            if p.is_file():
                rel = p.relative_to(src).as_posix()
                size = p.stat().st_size
                children.append(ChildHash(rel, size, sha256_file(p)))
                total += size
        agg = sha256_bytes("<empty-dir>".encode())
        if children:
            agg = sha256_bytes(
                "\n".join(f"{c.rel}\0{c.sha256}" for c in children).encode()
            )
        return ManifestFile(cand.rel, "dir", total, agg, children)
    if cand.kind == "file" and src.is_file():
        return ManifestFile(cand.rel, "file", src.stat().st_size, sha256_file(src))
    return None


def entry_current_fingerprint(root: Path, mf: ManifestFile) -> str | None:
    """计算源位置当前同路径条目的摘要；不存在或类型不符返回 None。

    dir 采用 snapshot 聚合摘要，file 直接计算文件摘要。
    """
    p = root / mf.rel
    if mf.type == "file":
        return sha256_file(p) if p.is_file() else None
    if mf.type == "dir":
        if not p.is_dir():
            return None
        snap = snapshot_entry(root, Candidate(mf.rel, "dir"))
        return snap.sha256 if snap else None
    return None


@dataclass
class BackupManifest:
    """一份账号备份的元数据清单。"""

    name: str
    client: str
    created_at: str  # ISO 时间串
    source_root: str  # 备份时的源根绝对路径
    files: list[ManifestFile] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "client": self.client,
            "created_at": self.created_at,
            "source_root": self.source_root,
            "files": [f.to_dict() for f in self.files],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BackupManifest":
        return cls(
            name=data["name"],
            client=data["client"],
            created_at=data.get("created_at", ""),
            source_root=data.get("source_root", ""),
            files=[ManifestFile.from_dict(f) for f in data.get("files", [])],
        )


@dataclass
class OperationResult:
    """操作结果汇总（备份 / 还原 / 写入空共用）。"""

    ok: bool
    message: str = ""
    steps: list[str] = field(default_factory=list)  # 逐文件结果描述
    success_count: int = 0
    fail_count: int = 0

    def add_success(self, text: str) -> None:
        self.steps.append(text)
        self.success_count += 1

    def add_fail(self, text: str) -> None:
        self.steps.append(text)
        self.fail_count += 1
        self.ok = False
