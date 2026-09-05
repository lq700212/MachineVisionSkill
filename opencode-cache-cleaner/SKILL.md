---
name: opencode-cache-cleaner
description: 清理 opencode 自身缓存中残留的项目记录（已改名/移动/删除的项目在 opencode 项目列表里仍显示旧名）。当用户说"清理 opencode 缓存/工作区缓存"、"项目改名后 opencode 里还显示旧名字/旧路径"、"opencode 里有残留项目要删掉"、"删除 opencode 里的项目记录"、"opencode 项目列表有死项目"时使用。用 Python 脚本列出所有项目、让用户选择、执行清理（删 project/project_directory 记录 + snapshot 快照）。
---

# opencode 缓存清理（残留项目记录）

## 背景

opencode 把打开过的每个项目登记进 SQLite 数据库（默认 `~/.local/share/opencode/opencode.db`），
并在 `~/.local/share/opencode/snapshot/` 留存项目快照。项目在磁盘上改名 / 移动 / 删除后，
opencode 项目列表仍会残留旧记录（project / project_directory 指向已不存在的路径），
界面继续显示旧项目名（如 commonLib）。

本 skill 的目标：**列出所有项目 → 让用户选择要清理的 → 备份 → 删除数据库记录与磁盘快照 → 验证 → 提示重启生效**。

## 触发词

- 清理 opencode 缓存 / 工作区缓存 / 项目缓存
- 项目改名 / 移动后 opencode 里还显示旧名字（如 "commonLib"）
- opencode 项目列表里有残留 / 死项目 / 幽灵项目
- 删除 opencode 里的项目记录

## 工具与位置

- 脚本：`clean.py`（与本 SKILL.md 同目录）
- 数据库默认路径：`C:\Users\Administrator\.local\share\opencode\opencode.db`
- 快照目录：`...\opencode\snapshot\<项目id>\`（目录名 = 数据库 project.id）
- 备份目录：`%TEMP%\opencode-cleaner-backups\`（删除前自动备份，可手动恢复）

## 工作流程（AI 必须遵守）

### 第一步：列出项目

```
python "C:\Users\Administrator\.config\opencode\skills\opencode-cache-cleaner\clean.py" --list
```

把输出里的项目列表（含 project id、显示名、路径）展示给用户。
若用户关心孤儿快照，可加 `--orphans` 一并列出。

### 第二步：询问用户

用 question 工具列出可清理的项目，让用户选择（单选或多选）。
注意：`global` 项目不可删，脚本会自动跳过。孤儿快照单独询问。

### 第三步：执行清理

用户选定后，直接传 project id 执行（不交互）：

```
python "...\clean.py" <project_id1> [<project_id2> ...]
```

或清理孤儿快照：

```
python "...\clean.py" --orphans --yes
```

### 第四步：验证

重跑 `--list` 确认选中项目已消失、其他项目完好。把删除项与备份路径告知用户。

### 第五步：提示重启

opencode 的配置/数据在启动时载入，**必须提示用户重启 opencode（桌面版）后项目列表才会刷新**。

## 安全红线

1. **删除前必备份**：脚本已自动导出待删记录到 `%TEMP%\opencode-cleaner-backups\`，失败时可用该 json 手动恢复（INSERT 回 project / project_directory 表）。
2. **只删选中的项目**：绝不碰其他项目的 session / message / event / snapshot。
3. **global 项目不可删**：脚本已拦截，AI 不要尝试传 `global`。
4. **数据库可能被占用**：opencode 正在运行时会持有数据库，脚本带 30s busy_timeout；若删除失败报 locked，提示用户先关闭 opencode 再跑。
5. **交互模式仅供人工**：AI 调用一律用参数模式（`clean.py <id>`）或 `--yes`，不要用无参数的交互 `input()` 流程（AI 无法可靠应答终端输入）。

## 脚本用法速查

| 命令 | 作用 |
| --- | --- |
| `python clean.py --list` | 列出所有项目（只读） |
| `python clean.py` | 人工交互模式：列项目→选择→确认→清理 |
| `python clean.py <id1> <id2>` | 直接清理指定项目（AI 推荐） |
| `python clean.py --orphans --yes` | 直接清理所有孤儿快照 |
| `python clean.py --db <路径>` | 显式指定 opencode.db（数据库不在默认位置时） |

## 常见场景举例

**场景：项目 CommonLib 改名后 opencode 里还显示 commonLib**
```
python clean.py --list          # 找到 CommonLib 对应的 project id（列表里路径指向已不存在的 E:/Project/CommonLib）
# 询问用户确认
python clean.py 52f5d3d615df8d18522984aaa64a6fbf0f4abf9a
python clean.py --list          # 验证已消失
# 提示用户重启 opencode
```

## 注意事项

- 脚本中文输出已按 UTF-8 重配 stdout，PowerShell 里直接显示即可。
- 若 `python` 不在 PATH，用完整路径 `D:\Python\Python314\python.exe` 或 `py`。
- 删除后若 opencode 桌面版项目列表没变化，是内存缓存未刷新，重启后即消失，不要重复执行脚本。