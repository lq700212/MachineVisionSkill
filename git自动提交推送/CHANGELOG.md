# 更新日志

`git自动提交推送` skill 的所有版本变动统一记录在此。格式参考 Keep a Changelog。

## [Unreleased]

（暂无未发布改动）

## [v1.2.0] - 2026-09-05

### 新增：提交前自动联动仓库自带 repo-hygiene 体检

- **改动**：`scripts/git_commit_push.py` 新增 `run_repo_hygiene`（提交前自动发现
  `<repo>/.opencode/skills/repo-hygiene/Test-GitignoreHygiene.ps1` 并跑一遍；
  无脚本/非 Windows/无 powershell 时降级跳过；`--skip-check` 同时跳过本联动）；
  SKILL.md 四节第6步改"主脚本已自动联动"。
- **门禁语义**：必须用**非 Strict**——Strict 下 H6 见脏即 FAIL，而待提交改动本身
  就是脏，硬用 Strict 会挡住每一次正常提交；非 Strict 下只有 H1-H5 硬伤 exit 1
  才阻断，H6 脏列表仅 WARN 展示。
- **背景**：HuaJiVision 要求把 repo-hygiene 融进提交流程（提交前一起查）；
  评估后未做搬迁式合并（hygiene 全是该项目硬编码、脚本寻根依赖原路径、有独立触发场景），
  用联动实现"提交时自动一起查"，本体保留"平时单独查"。
- **验证**：`py_compile` 通过；HuaJiVision 真仓库 `--dry-run --explicit` 实测
  H1-H5 全 PASS、H6 仅 WARN、结论 OK 后正常出 message 预览。

## [v1.1.0] - 2026-09-05

### 合并：吸收 HuaJiVision 项目 skill `git-auto-commit-push`（该项目版已删除）

- **改动**：`scripts/git_commit_push.py` 新增 `extract_latest_sections`（正文细节提炼）与
  `--explicit` 显式暂存模式；读取改 UTF-8-SIG，含 U+FFFD 视为损坏回退；
  SKILL.md 新增"正文组装"规则（3.2节）、现场目录步骤、验证项与合并说明（八节）。
- **正文规则**：`-` 条目 + `①②③` 枚举 + 缩进续行合并；`：`/`:` 结尾纯标题头丢弃；
  单条≤140 字、每节≤8 条、总量≤32 条，超限加"完整改动见 CHANGELOG"尾行；
  正文绝不只剩"对应 CHANGELOG…"一句（V4.3.2 空话 commit 教训）。
- **验证**：`py_compile` 通过；合成仓库 `--dry-run` 三场景
  （结构化正文/显式空暂存中止/已暂存预览）全对。

## [v1.0.0] - 2026-09-04（基线）

- 双脚本架构：`git_commit_push.py`（检查→暂存→自动 message→推送）+
  `precommit_check.py`（文件名禁入/机密内容/UTF-8/大文件，OK/NG + 退出码）。
- CHANGELOG 三格式标题自适应（标题即摘要型/混合型/Keep-a-Changelog 型，V1.59 教训）。
- 参数：`path`/`-m`/`--no-push`/`--dry-run`/`--force`/`--skip-check`。
