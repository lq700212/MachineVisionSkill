# 更新日志

`opencode-cache-cleaner` skill 的所有版本变动统一记录在此。格式参考 Keep a Changelog。

## [v1.0.0] - 2026-09-05（基线入库）

- 现有 `SKILL.md` + `clean.py` 首次纳入本仓库 git 追踪（白名单放行），内容零改动。
- 功能要点：列出 opencode SQLite（`opencode.db`）全部项目 → 用户选择 →
  备份待删记录到 `%TEMP%\opencode-cleaner-backups\` → 删除 project /
  project_directory 记录与 `snapshot/<project_id>/` 快照 → 重跑 `--list` 验证 →
  提示重启 opencode 生效；`global` 项目不可删；支持孤儿快照清理与 `--db` 显式指定。
