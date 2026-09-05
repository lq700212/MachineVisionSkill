# AGENTS.md — git自动提交推送 skill 维护规范（改本 skill 前必读）

## 改动流程

1. 改脚本前先读 SKILL.md 对应章节（message 规则在"三"、流程在"四"、验证在"七"），
   保持文档与行为一致；
2. 改完必须同步两处文档：本目录 `CHANGELOG.md`（`[Unreleased]` 或新版本节）、
   skills 根目录 `CHANGELOG.md` 顶部（本次总览 + 建议 commit message，
   见根 `AGENTS.md` 收尾清单）；
3. 版本号：功能新增/行为变化升 minor（如 v1.1.0→v1.2.0），纯修 bug 升 patch；
   同一天多轮未提交的改动可并入同一版本节。

## 改脚本后必跑的验证（无需用户提醒）

1. `python -m py_compile scripts/git_commit_push.py scripts/precommit_check.py`；
2. 合成仓库 `--dry-run`：默认模式与 `--explicit` 空暂存/已暂存三态预览正常，
   正文含 `· 小节` + `  - 要点`（续行合并、纯标题头过滤）；
3. 有条件时在真仓库 `--dry-run` 跑一遍（含 repo-hygiene 联动段）。

## 分工红线（防职责漂移）

- 本 skill 管"提交流程编排"；`precommit_check.py` 管"待提交增量安不安全"；
  各仓库自带的 repo-hygiene 管"仓库规则与全库健康"——只联动调用，
  不把别家硬编码搬进来。
- 通用性：默认行为必须对无 CHANGELOG、无 hygiene 的普通仓库可用；
  项目专属逻辑一律走"自动发现（有则用）+ 降级跳过"，禁止写死路径。
- 编码：脚本 stdout/stderr 强制 UTF-8；中文输出在 GBK 终端显示乱码属显示假象，
  以文件字节与退出码为准。
