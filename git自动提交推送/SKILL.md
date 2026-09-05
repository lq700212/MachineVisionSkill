---
name: "git自动提交推送"
description: "一键把本地 Git 工程提交并推送到 GitHub：自动暂存全部改动、自动生成高质量的 commit message（优先读 CHANGELOG.md 最新版本条目，含小节要点细节提炼）、提交前自动做安全与卫生检查（机密变体/禁入文件/编码）、提交后推送，全程可人工执行也可让 AI 代跑。当用户说『提交/推送代码』『把工程上传 github』『git push』『写好 commit 再提交』『发一版』等，或需要把项目发到远程仓库时使用。脚本为主：即使不依赖 AI，人工运行 python 脚本也能完成同样的事；现场运行目录用 --explicit 显式暂存模式。"
---

# Git 一键提交推送（自动写 commit + 提交前安全检查）

> 本技能把「提交前安全检查 → git add → 写 commit → push」抽成**两个可独立运行的 Python 脚本**：
> 人工直接跑脚本能完成上传；AI 代跑时也调用同一套脚本，保证两路行为一致。
> 脚本在本技能目录 `scripts/` 下，无第三方依赖（纯标准库）：
> - `git_commit_push.py` — 主流程：检查→暂存→自动 commit message→推送；
> - `precommit_check.py` — 提交前安全与卫生检查，结论只有 **OK / NG**。

## 一、快速用法（不依赖 AI 也能用）

```powershell
# 推荐：一条命令 = 提交前检查 + 提交 + 推送（检查 NG 自动中止）
python "<本技能目录>\scripts\git_commit_push.py" [仓库路径] --force

# 单独跑"提交前检查"（AI 只看最后一行 RESULT: OK / RESULT: NG）
python "<本技能目录>\scripts\precommit_check.py" [仓库路径]
```

**git_commit_push.py 参数：**

| 参数 | 作用 |
| --- | --- |
| `path`（位置参数） | 仓库路径，默认当前目录 |
| `-m "消息"` | 手动指定 commit message（覆盖自动生成；AI 代跑时先读 CHANGELOG 最新条目自己提炼再传） |
| `--no-push` | 只提交不推送 |
| `--dry-run` | 只预览改动与将执行的命令 |
| `--force` | 跳过 y/N 确认（无人值守） |
| `--explicit` | 显式暂存模式：跳过自动 `git add -A`，只提交已暂存内容；暂存区为空时中止（现场运行目录/含运行时数据仓库必用，防误收） |
| `--skip-check` | 跳过提交前安全检查（确属误报时的逃生门，慎用） |

## 二、提交前安全检查（precommit_check.py，V2 新增固化）

以前由 AI 口头执行的"改动范围确认 + 不该入库文件拦截 + 机密泄露扫描 + 编码自查"
已固化为脚本，**AI 调用后只读结果**：

```
RESULT: OK   → 放心继续提交流程（可能有 WARN 提醒条目，人工过目即可）
RESULT: NG   → 按 [NG-*] 编号明细处理后重跑；确属误报才允许 --skip-check
退出码        → 0=OK；1=NG；2=环境错误
```

检查项：
1. **待提交清单全量列出**（供人工复核范围）；
2. **禁止入库文件名**：运行时数据（Users.json/TestSession.json/Recipes.json 等）、
   日志/临时文件、bin/obj、机密类变体（*.pem/*.key/.pfx/*.snk/.env/*credential*/*secret*…）、
   **商业组件授权文件**（HslLicense.dat/hsl.dat/*.lic/.snk——V1.59 教训：HSL 工业通讯库
   授权码 .dat 文件曾漏检；注意开源协议文本 LICENSE.md 必须放行，只匹配
   "授权语义+数据扩展名"组合）；
3. **机密内容变体扫描**（对将提交的文本内容）：私钥块、api_key/secret/token 明文赋值、
   连接串 pwd=…——命中 ERROR 判 NG；可疑 password 字面量归 WARN 人工判断；
   占位符（your_xxx/<xxx>/${…}）自动豁免防误报；
4. **中文文本 UTF-8 自查**（AgingTestSystem 项目铁律：GBK 落盘必乱码）；
5. **>10MB 大文件提醒**。

规则表在脚本顶部常量区（`FILENAME_DENY` / `FILENAME_SECRET_VARIANTS` /
`CONTENT_SECRET_ERROR`…），新仓库有新红线直接加正则即可。
> ⚠️ 维护约定：发现漏检（如 HslLicense.dat 授权文件）后**立即把变体补进
> `FILENAME_SECRET_VARIANTS` 并用探针文件回归验证**，同时在本文件记一笔——
> 机密规则库是越养越全的，靠每次真实教训喂出来的。

## 三、自动 commit message 规则（脚本内置）

### 3.1 主题行（优先级）

1. **读仓库 `CHANGELOG.md` 最新版本条目**，按"版本头是否自带实质摘要"区分三种格式：
   - **标题即摘要型**：`## V1.0.1（2026-08-15）修复...` → 整行作标题；
   - **混合型**（AgingTestSystem 等，V1.59 教训修复）：
     `## V1.59 — 业务串联完善：…（日期）` 下面跟 `### 改动范围/为什么这么改/验证`
     ——### 只是**段落分组标签不是摘要条目**，判据是版本行剥掉版本号/日期后仍有
     ≥8 个实质字符 → 整行作标题。
     > ⚠️ 历史教训：旧逻辑见 ### 就拼接小节名，V1.59 的 commit 标题被写成
     > 「V1.59 改动范围；为什么这么改；验证」零信息量。已修复并三种格式全测过。
   - **Keep-a-Changelog 型**（HuaJiVision 等）：裸版本头 `## [V4.3.2] - 2026-08-25`
     + 摘要小节 → 标题 = `[V4.3.2] 修复：xxx；功能：yyy…`（超 100 字符截断，
     全部小节清单写入正文不丢信息）。
2. **没有 CHANGELOG** → 回退为文件类型统计摘要（如「修改 3 个文件、新增 2 个文件」）；
3. `-m` 手动指定时完全用用户给的消息。AI 代跑若认为自动标题不够好，
   应主动用 `-m` 给出更准确的概括（先读 CHANGELOG 最新条目自己提炼）。

### 3.2 正文组装（V4.3.2 空话 commit 教训，已固化）

以前正文只有 `对应 CHANGELOG.md 最新版本条目：xxx` 一句空话——主题抄了版本头、
真正的干货（`###` 小节下的 `-` 条目与 `①②③` 续行）全丢了。现在脚本自动提炼：

```
对应 CHANGELOG.md 最新版本条目：[V4.3.3] - 2026-08-26

· 存图浏览可见区虚拟化加载
  - 要点一（来自该小节的 - 条目与 ①②③ 续行）
  - 要点二
· 工程卫生固化
  - ……
  …（完整改动见 CHANGELOG.md [V4.3.3] 小节）   ← 超 32 条总量时才出现
```

抓取规则：`- xxx` 条目行收一条；`①②③… xxx` 枚举行收一条；
缩进续行拼回上一条（长干货常写在续行里）；以 `：`/`:` 结尾的纯标题头丢弃；
markdown 标记（`**`、`` ` ``）已剥除；单条超 140 字符截断加 `…`；
每节最多 8 条、全文最多 32 条。有小节标题但无条目干货时回退为标题清单，
保证不丢信息；**正文绝不只剩"对应 CHANGELOG…"一句**。

## 四、AI 使用步骤（脚本优先，别手写 git 命令）

1. 改代码先更新 `CHANGELOG.md`（新增版本条目）——commit 消息取该条目，
   版本记录与提交历史逐条对应可回溯；CHANGELOG 未更新就先更新再提交；
2. 用户要求提交/推送时，先跑 `precommit_check.py`（或直接跑主脚本，它第一步就会检查）；
3. 结果 OK → 继续提交推送；结果 NG → 把 [NG-*] 明细报给用户/自行处理，**不要 --skip-check 硬闯**
   （除非逐条确认是误报）；
4. 常规调用：`python scripts\git_commit_push.py <repo> --force`（无人值守）；
   需要预览用 `--dry-run`；只提交用 `--no-push`；用户给了文案用 `-m "..."`；
5. **现场运行目录/含运行时数据的仓库（如同时是编译输出目录的）必须用 `--explicit`**：
   先 `git status` + `git diff` 确认范围，逐个 `git add <路径>`（**禁止 `git add -A` 盲加**），
   再跑主脚本 `--explicit --force` 只收已暂存内容；
6. 仓库若自带工程卫生体检（如 HuaJiVision 的 `repo-hygiene/Test-GitignoreHygiene.ps1`），
   主脚本已自动跑一遍（非 Strict：H1-H5 的 FAIL 阻断提交，H6 脏列表仅展示；
   必须非 Strict——Strict 下 H6 见脏即 FAIL，而待提交改动本身就是脏）。
   它管"仓库规则与全库健康"，本技能的 precheck 管"待提交增量安不安全"，互补不替代；
   手动改 `.gitignore`（每改一条复测一次）/新增机密文件时才需单独跑它，交付前手动跑加 `-Strict`；
7. 汇报只讲关键结果：commit 标题 + 是否推送成功，不复述脚本输出。

> ⚠️ 铁律：**不主动提交/推送**——只有用户明确要求时才执行；主脚本内置的 precheck
> 不替代 AI 对"改动是否符合用户预期"的判断（脚本管安全卫生，AI 管业务范围对不对）。

## 五、Windows 编码说明

- 脚本强制 stdout/stderr 用 UTF-8，中文输出不乱码；
- CHANGELOG.md 本身必须是 UTF-8（脚本按 UTF-8 读）；GBK 文档先转码再提交；
- git 提交信息存库为 UTF-8，跨平台正常。

## 六、与工程规范的衔接

- **改代码先更新 `CHANGELOG.md`**（新增 V 版本条目），commit 消息自动取该条目，
  版本记录与提交历史逐条对应可回溯；
- 无 CHANGELOG 的仓库自动退回类型摘要，仍能正常提交推送。

## 七、验证清单（交付前自查）

1. `--dry-run` 正确列出改动并显示生成的 commit 标题；
2. 三种 CHANGELOG 格式的标题生成均正确（混合型=整行 / Keep-a-Changelog=小节拼接 / 纯标题=整行）；
3. 正文含 `· 小节` + `  - 要点` 结构化内容（`①②③` 枚举与缩进续行已合并，`改动范围：`类纯标题头已过滤），
   不只剩"对应 CHANGELOG…"一句；
4. `--explicit` 下暂存区为空时中止并提示逐个 add，已暂存时只收暂存内容（`--dry-run` 可预览）；
5. `precommit_check.py` 对故意放置的 .pem / api_key 测试文件必须报 NG（退出码 1），
   删除后恢复 OK（退出码 0）；
6. `git push` 成功（远程已配好、凭据有效）。

## 八、合并说明（2026-09-05：HuaJiVision 项目 skill 已并入本技能）

- 项目 skill `git-auto-commit-push`（PowerShell `New-CommitMessage.ps1`）已删除，能力全部并入本技能：
  - message 正文细节提炼（`-`/`①②③`/续行合并、纯标题头过滤、140/8/32 截断、溢出尾行）→ `git_commit_push.py` 内置；
  - "禁止手打正文/禁止空话正文" → 3.2 节与脚本行为双固化；
  - "禁止 `git add -A` 盲加" → `--explicit` 模式；
  - 原 `-Subject "主题"` 传参 → `-m "主题"`（AI 先读 CHANGELOG 再起草，效果相同）；
  - 原 `Test-GitignoreHygiene.ps1 -Strict` 前置卫生 → 步骤 6 衔接（各仓库自带时跑，不在本脚本内硬编码路径）。
- 历史文档（README/CHANGELOG 里提到的 `git-auto-commit-push`）是当时事实记录，保持不动；
  只有各仓库 AGENTS.md 这类"活规则"需要把 skill 名改指到本技能。
