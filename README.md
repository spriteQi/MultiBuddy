<div align="center">

# 此项目完全由 CodeBuddy 编写，因为 token 用不完

</div>

# MultiBuddy

管理本机 CodeBuddy / WorkBuddy 客户端已登录账号的**凭证文件**，实现多账号保存与一键切换。

- 把当前本机登录态（凭证文件）备份到项目 `user/<账号名>/` 目录
- 通过 GUI 的「→ 保存 / ← 写入 / 写入空」完成账号的保存、切换与清除
- 纯标准库实现（Tkinter + pathlib + shutil），零第三方依赖

## 运行环境

需要**自带 Tcl/Tk 的完整版 Python**（SDK 精简版 Python 不含 Tk 脚本，无法启动界面）。

```powershell
# 例如本机可用于运行 GUI 的完整版 Python：
& 'C:\Users\chobit\.workbuddy\binaries\python\versions\3.14.3\python.exe' --version
```

## 启动（GUI）

```powershell
cd d:\develop\project\MultiBuddy
python -m app.main        # 或 python app\main.py
```

首次启动会自动创建 `user/`（凭证备份目录）、`logs/`（操作日志）与 `user/config.json`（源配置）。

## 命令行模式（CLI）

独立入口 `app/main_cli.py`，复用同一套 core 逻辑、无需图形界面：

```powershell
python -m app.main_cli                              # 不带参数：数字菜单交互模式（按数字键直操作、每步自动清屏，0 退出）
python -m app.main_cli --help                       # 查看全部子命令帮助
python -m app.main_cli list                         # 查看各客户端本地凭证与已备份账号
python -m app.main_cli detect codebuddy-cn-ide      # 检测本地凭证（codebuddy-cli / workbuddy，或别名 ide/cli/wb）
python -m app.main_cli save  codebuddy-cn-ide 账号A          # 把当前本地凭证保存为备份（--rel 可只备份指定项）
python -m app.main_cli write codebuddy-cn-ide 账号A          # 把备份写回本地（交互确认，--yes 跳过）
python -m app.main_cli empty workbuddy --yes                 # 写入空：清除本地凭证后登录新账号
python -m app.main_cli delete codebuddy-cn-ide 账号A --yes   # 删除备份
python -m app.main_cli rename codebuddy-cn-ide 旧名 新名     # 重命名备份
python -m app.main_cli info  workbuddy 账号A                 # 查看备份文件清单
```

命令行为与 GUI 一致：`write`/`empty` 前会自动做“当前登录态是否已备份”的防丢失检查，交互确认后才会执行；失败（如文件被客户端占用）会明确提示。

## 界面与使用流程

主窗口含两个标签页，互不混淆：

| 标签页 | 管理对象 | 默认源路径 |
|---|---|---|
| **CodeBuddy** | CodeBuddy CN IDE 登录态（可切换到 CLI 源 `~/.codebuddy`） | `%APPDATA%\CodeBuddy CN` |
| **WorkBuddy** | WorkBuddy 凭证目录 | `%LOCALAPPDATA%\CodeBuddyExtension\Data\Public`（其下 `auth` 目录，登录后自动生成） |

每页为「左右双栏 + 中缝操作」布局：

- **左栏·本地凭证**：列出当前源目录检测到的凭证文件/目录（默认全选，可勾选微调）
- **右栏·已备份的凭证**：列出 `user/` 下已保存的账号（名称、文件数、大小、时间），支持选中后重命名/删除
- **→ 保存**：把左侧勾选的本地凭证命名备份到右侧（同名覆盖）
- **← 写入**：把右侧选中的备份还原到本地源位置
- **写入空**：删除本地凭证，使客户端回到未登录态，随后打开客户端登录新账号，再「→ 保存」即可备份新账号

> 切换/写入空前若检测到**当前登录态尚未备份**，会弹「备份当前并继续 / 忽略并继续 / 取消」三选一，避免误丢凭证。

## 写入空（登录新账号）完整流程

1. 在 CodeBuddy / WorkBuddy 页点「写入空」→ 确认
2. **退出**正在运行的客户端
3. 重新打开客户端 → 使用新账号登录
4. 回到本工具，左侧会检测到新登录态 → 点「→ 保存」命名备份

## 凭证文件范围（可校准）

工具只处理“候选凭证清单”内的路径，**绝不触碰** IDE 设置（如 `User/settings.json`）与对话历史类数据。本机实测校准后的默认清单：

- **CodeBuddy CN IDE**（`%APPDATA%\CodeBuddy CN`）：
  - `User/globalStorage/storage.json`、`state.vscdb`、`state.vscdb.backup`
  - `codebuddy-sessions.vscdb`、`Network/Cookies`（文件）
  - `Local Storage`、`Session Storage`（目录）
- **CodeBuddy CLI**（`~/.codebuddy`）：`local_storage/`、`settings.local.json`（按存在性显示）
- **WorkBuddy**（`%LOCALAPPDATA%\CodeBuddyExtension\Data\Public`）：`auth/`（目录，登录后自动创建）

若你的凭证文件与默认不符：点页右上角 **「管理候选…」** 可添加/删除文件或目录，或「自动扫描」按命名规则（auth/token/session/cookie…）发现候选项；点 **「编辑源路径…」** 可修改客户端数据目录。修改会自动保存到 `user/config.json`。

## 重要提示

- `user/` 目录包含**登录凭证等敏感数据**：不要共享、不要提交到版本库（已被 `.gitignore` 忽略）。
- 执行「保存 / 写入 / 写入空」时若客户端正在运行，文件可能被占用（实测 `Network/Cookies` 在 CodeBuddy 运行期间无法读取）。请**先退出客户端**再操作；失败时工具会明确提示被占用的文件。
- 切换账号后需**重启客户端**，登录态才会生效。
- 备份与还原均校验 sha256；备份采用“临时目录 + 原子改名”，避免留下半成品。

## 目录结构

```
MultiBuddy/
├── app/
│   ├── main.py            # 图形界面入口
│   ├── main_cli.py        # 命令行入口（独立）
│   ├── core/              # 纯逻辑层（可单测）
│   │   ├── model.py       # 数据模型 / sha256 快照
│   │   ├── sources.py     # 三类客户端源定义与默认候选清单
│   │   ├── store.py       # user/ 备份存储与 manifest 管理
│   │   ├── backup.py      # 备份引擎
│   │   └── restore.py     # 还原/写入空引擎
│   └── ui/                # Tkinter 界面层
├── tests/                 # unittest 单测（临时目录模拟，不触碰真实凭证）
├── user/                  # 账号备份（运行后生成，不提交）
└── logs/                  # 操作日志（运行后生成，不提交）
```

## 测试

```powershell
python -m unittest discover -s tests -v
```
