"""客户端源定义：三类默认源与候选凭证清单，支持用户覆盖配置与按命名规则扫描。

默认基线（可在界面修改，修改项持久化到 user/config.json 的 overrides）：
- codebuddy-cn-ide：%APPDATA%\\CodeBuddy CN（CodeBuddy CN IDE 登录态）
- codebuddy-cli    ：%USERPROFILE%\\.codebuddy
- workbuddy        ：%LOCALAPPDATA%\\CodeBuddyExtension\\Data\\Public，凭证目录为 auth
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .model import Candidate, SourceProfile

# GUI 标签页 -> 其下包含的客户端源
GROUP_PROFILES = {
    "codebuddy": ["codebuddy-cn-ide", "codebuddy-cli"],
    "workbuddy": ["workbuddy"],
}

# 供"自定义源按命名规则扫描"识别的凭证相关名称（命中即纳入候选）
_CRED_NAME_HINTS = (
    "auth", "token", "login", "credential", "cred", "account", "session",
    "cookie", "secret", ".auth", ".login", "keyring", "stoken", "ckey",
)


def _env_dir(var: str, default_rel: str) -> Path:
    val = os.environ.get(var)
    if val:
        return Path(val)
    return Path.home() / default_rel


def default_profiles() -> dict[str, SourceProfile]:
    """构造三类客户端的内置默认源定义。"""
    appdata = _env_dir("APPDATA", "AppData/Roaming")
    localappdata = _env_dir("LOCALAPPDATA", "AppData/Local")
    home = Path.home()

    ide = SourceProfile(
        client="codebuddy-cn-ide",
        title="CodeBuddy CN IDE",
        root=appdata / "CodeBuddy CN",
        desc="CodeBuddy CN IDE 登录态数据目录",
        candidates=[
            Candidate("User/globalStorage/storage.json", "file"),
            Candidate("User/globalStorage/state.vscdb", "file"),
            Candidate("User/globalStorage/state.vscdb.backup", "file"),
            Candidate("codebuddy-sessions.vscdb", "file"),
            Candidate("Network/Cookies", "file"),
            Candidate("Local Storage", "dir"),
            Candidate("Session Storage", "dir"),
        ],
    )
    cli = SourceProfile(
        client="codebuddy-cli",
        title="CodeBuddy CLI",
        root=home / ".codebuddy",
        desc="CodeBuddy CLI 配置与本地存储目录",
        candidates=[
            Candidate("local_storage", "dir"),
            Candidate("settings.local.json", "file"),
        ],
    )
    wb = SourceProfile(
        client="workbuddy",
        title="WorkBuddy",
        root=localappdata / "CodeBuddyExtension" / "Data" / "Public",
        desc="WorkBuddy 数据目录（凭证目录 auth 由客户端登录时自动创建）",
        candidates=[
            Candidate("auth", "dir"),
        ],
    )
    return {p.client: p for p in (ide, cli, wb)}


def scan_custom_source(root: Path, depth: int = 3) -> list[Candidate]:
    """在自定义源根内按命名规则扫描凭证候选（文件/目录均可能命中）。

    仅用于用户添加自定义客户端源时的辅助发现，不深读内容。
    """
    if not root.is_dir():
        return []
    hits: list[Candidate] = []
    seen: set[str] = set()

    def walk(base: Path, rel: str, level: int) -> None:
        if level > depth:
            return
        try:
            entries = sorted(base.iterdir(), key=lambda x: x.name.lower())
        except OSError:
            return
        for ent in entries:
            child_rel = f"{rel}/{ent.name}".lstrip("/")
            name_l = ent.name.lower()
            is_cred = any(h in name_l for h in _CRED_NAME_HINTS)
            if is_cred and child_rel not in seen:
                seen.add(child_rel)
                kind = "dir" if ent.is_dir() else "file"
                hits.append(Candidate(child_rel, kind))
            if ent.is_dir() and not name_l.startswith(".") and not is_cred:
                walk(ent, child_rel, level + 1)

    walk(root, "", 1)
    return hits


def _cand_to_dict(c: Candidate) -> dict:
    return {"rel": c.rel, "kind": c.kind}


def _cand_from_dict(d: dict) -> Candidate:
    return Candidate(str(d["rel"]), str(d.get("kind", "file")))


@dataclass
class ProfileRegistry:
    """源定义注册表：内置默认 + 用户覆盖（持久化到 user/config.json）。"""

    config_file: Path
    _overrides: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.load()

    def load(self) -> None:
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                self._overrides = data.get("overrides", {})
            except (json.JSONDecodeError, OSError):
                self._overrides = {}

    def save(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"overrides": self._overrides}
        self.config_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def all_profiles(self) -> dict[str, SourceProfile]:
        out = default_profiles()
        for client, ov in self._overrides.items():
            if client not in out:
                continue
            base = out[client]
            if "root" in ov and ov["root"]:
                base.root = Path(ov["root"])
            if "candidates" in ov:
                base.candidates = [_cand_from_dict(c) for c in ov["candidates"]]
        return out

    def profiles_for_group(self, group: str) -> list[SourceProfile]:
        profiles = self.all_profiles()
        return [profiles[c] for c in GROUP_PROFILES.get(group, []) if c in profiles]

    def profile(self, client: str) -> SourceProfile | None:
        return self.all_profiles().get(client)

    def set_root(self, client: str, root: str) -> None:
        ov = self._overrides.setdefault(client, {})
        ov["root"] = root
        self.save()

    def set_candidates(self, client: str, rels: list[str], kind_of: dict[str, str]) -> None:
        """以完整清单覆盖某客户端的候选（用于添加/移除自定义项后落盘）。"""
        cands = []
        for rel in rels:
            if rel:
                cands.append(_cand_to_dict(Candidate(rel, kind_of.get(rel, "file"))))
        self._overrides.setdefault(client, {})["candidates"] = cands
        self.save()
