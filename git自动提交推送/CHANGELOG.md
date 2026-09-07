# 更新日志

`git自动提交推送` skill 的所有版本变动统一记录在此。格式参考 Keep a Changelog。

## [Unreleased]

### 新增：提交前回检 CHANGELOG（SKILL.md 四节第 5 条）

- **改动**：仅 SKILL.md 文档补强，脚本零改动。AI 使用步骤新增第 5 条
  （V4.4.17 教训）：`--dry-run` 打出的标题正文当审稿单，逐项核对最新源码/diff
  （方法名/类名/色值/数量/机制描述）；过期措辞先改 CHANGELOG、重跑 dry-run
  确认更新后再提交。旧 5〜7 条顺延为 6〜8 条，八节引用同步。
- **背景**：HuaJiVision V4.4.17 提交时 SG28 实现已从"两处三元"改成独立方法，
  CHANGELOG 验证描述没同步就提交了，事后又补改一次。CHANGELOG 是 commit
  message 的唯一信源，信源错了提交就错了——必须先改对再提交。

### 新增：分支识别前置铁律（SKILL.md 四节第 0 条）

- **改动**：仅 SKILL.md 文档补强，脚本零改动。AI 使用步骤新增第 0 条
  （V4.4.8 血泪铁律）：任何提交/推送/撤回判断之前必做
  `git branch --show-current` + `git status -sb`，之后一切"是否已推送/
  领先几个/要不要 force"的参照系只能是当前分支的对应远程（`git log @{u}..HEAD`），
  禁止拿 main 或其它分支当参照。
- **背景**：HuaJiVision 实测事故——在 Pro_Lin 分支上用 `origin/main..HEAD`
  判断"V4.4.8 未推送"，实际早已推到 origin/Pro_Lin，参照系一错结论全错。
  同时固化：推送目标=当前分支 upstream（不问不猜）；撤回已推送提交覆盖前
  先 fetch 确认远程 HEAD，只允许 `--force-with-lease`，禁用裸 `--force`。

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
