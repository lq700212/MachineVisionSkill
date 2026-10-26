# 视觉选型测试 - 变更记录

## Unreleased

### 元数据：frontmatter `name` 改 ASCII slug（DSH 接入，2026-10-22）

- 仅改 SKILL.md frontmatter 的 `name`：`视觉选型测试` → `vision-selection-test`（1 行）；目录名/正文/测试用例零改动，未升版
- 原因：DSH 加载器硬校验 `SKILL_NAME = /^[a-z0-9]+(-[a-z0-9]+)*$/`，中文名被静默丢弃（不可调用）
- 影响：DSH 内本 skill 调用名改为 `vision-selection-test`；目录名不变，`SKILL.md` 与 `AGENTS.md`
  里的脚本路径引用（`.../skills/视觉选型测试/tests/run_all.py`）不受影响

## v1.0.0（初始基线）

- 本文件为 2026-10-22 补建：此前 `视觉选型测试` skill 未单独维护 CHANGELOG，
  历史改动见根目录 `CHANGELOG.md` 与 `视觉硬件选型/CHANGELOG.md` 中的相关条目
