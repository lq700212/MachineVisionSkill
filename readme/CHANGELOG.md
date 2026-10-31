# CHANGELOG — readme skill

> 版本规则：流程/脚本/红线变化即记一笔。

## V1.2.0（2026-10-31，盘点脚本只认渲染真身 + --skip-dir 排除目录）

- **img_inventory.py 收集口径升级：跳过代码块与行内代码**。本仓库实战首用
  （重写 MachineVisionSkill 根 README）暴露 3 处误报 DEAD-REF——
  `readme/CHANGELOG.md` 第 54 行介绍脚本功能写的 `` `![](…)` `` 行内代码、
  `readme/SKILL.md` 骨架模板 fence 里的 `docs/images/<a>.png` 占位图：
  全是"文档里谈论图片语法"，不是渲染真身。修法：scan_md 逐行加 fence
  状态机（``` 行切换开关，整块跳过）＋ strip_inline_code（按反引号分段只收
  偶数段）；本仓库复跑 DEAD-REF 18→3→0，RESULT: OK。
- **img_inventory.py 新增 `--skip-dir 目录名`（可重复）**：任何层级命中即整枝
  跳过，用于**本地安装不入库的第三方 skill**（如 pixel2motion——其 README
  自带 15 处上游 docs 死链，图无来源可补、删引用又篡改第三方文档，属外部
  仓库病灶，不该卡死本仓体检）。跳过名单打印 `[INFO]` 行留痕。
- **写作实战**：本仓库根 README 按 V1.1.x 流程重写（摸底→目录表补 readme
  行＋pixel2motion 行→mermaid 架构→目录树→徽章 4 枚），check_readme
  NG=0 WARN=0、img_inventory（--skip-dir pixel2motion）RESULT: OK。

## V1.1.1（2026-10-31，注册修复：主文件名 AGENTS.md → SKILL.md + 盘点目录扩充）

- **为何"readme skill 从未出现在可用列表"（首用现场才发现）**：主指引一直叫
  `AGENTS.md`（V1.0.0 定名沿用），而 opencode 按目录下的 **SKILL.md** 注册技能——
  同目录其余 20 个 skill 全有 SKILL.md，唯 readme 缺失，故触发词再准也匹配不到。
  修复：`git mv`/`Rename-Item` 改名为 `SKILL.md`（frontmatter 本就规范，改名即注册，
  当场热加载成功）；文件头补"必须叫 SKILL.md"警示防回退。
- **skills 仓库白名单补 `!readme/`**：`.gitignore` 第 5 行 `/*` 全忽略＋白名单制，
  readme 建仓时漏加白名单（整个目录从未被跟踪过——改名时 `git mv` 报
  not under version control 实锤）。
- **img_inventory.py EXCLUDE_DIRS 扩 `resources/Resources`（大小写双拼）**：
  GUI 程序资源目录族（.NET/WPF/Android 的 exe 图标等，如 AgingTestSystem
  `Resources/app.png`）不是文档配图目录，常驻误报 ORPHAN；现有集合是
  大小写敏感匹配，Windows 下目录名大小写任意，故双拼都收。
  写作链回归：改后对 AgingTestSystem 重跑，ORPHAN 由 1 张归零，RESULT: OK。

## V1.1.0（2026-10-31，更名 + 默认触发 + 全文去项目绑定）

- **更名 `readme图文并茂` → `readme`**（用户拍板）：原名把触发绑死在"图文
  并茂"这个附加词上；用户要的是"**生成 README 就自动走这个标准**"——目录、
  frontmatter name、两脚本 docstring 全部同步改。
- **默认触发**：description/触发词升级为"任何写/生成/更新/重写 README 任务
  都默认走本流程"；用户明确要"纯文字版"时才可删图墙段降级，事实红线与
  脚本核验照走不降。
- **通用化（规范性内容剥离 CureLine 绑定）**：
  - 信源表 → **等价文件家族**（`AGENTS.md`/`CLAUDE.md`/`CONTRIBUTING.md`/
    `Makefile`/`csproj`/`pyproject`/`package.json`/`go.mod`/`Cargo.toml`
    按项目存在取），不再假定 AGENTS.md 节名；
  - 截图决策树按**项目形态分路**：GUI 桌面（走 WPF 专项纪律）/ Web 前端
    （headless 一行命令 + 演示态种子）/ 纯库·CLI（**不硬凑截图**，用 mermaid
    架构图 + 目录树 + 代码示例代图）；
  - 骨架改**必备 2 段（hero+快速开始）+ 选配 7 段**（界面速览/程序卡片/
    权限表/架构/目录树/文档导航/配置，条件触发），明确"骨架是满配上限，
    缺项比硬凑好看"；
  - 截图纪律拆两段：**通用人心**（任何技术栈：不抢焦点/不进任务栏/离屏拍）
    + **WPF/.NET 专项**（四件套 + RTB 成品口径 + pack URI/换槽两坑）；
    新增 Web 专项坑（演示态种子/宽度统一）。
- **scripts/img_inventory.py**：目录排除列表通用化（`node_modules`/`target`/
  `dist`/`build`/`vendor`/`__pycache__`/`.venv`/`site-packages`/`packages`）；
  docstring 删掉脚本并不支持的 `--docs` 用法行。
- 流程闭环闸：img_inventory **第 2 步开工一次 + 第 7 步收尾复跑一次**。
- V1.0.0 的 CureLine 实战记录保留（史实，规范性内容已全部解绑）。

## V1.0.0（2026-10-31，首版：CureLine V0.0.50 实证沉淀）

- **AGENTS.md 主指引**：7 步流程（事实摸底 → 图片盘点 → 截图决策树 → 骨架 →
  后台静默截图纪律 → 卫生核验 → 收尾）+ 骨架模板（hero 徽章 / 图墙 / 程序卡片 /
  快速开始 / 权限表 / mermaid 架构 / 目录树 / 文档导航 / 配置自愈）。
- **scripts/img_inventory.py**：文档图片引用 vs 磁盘差集盘点
  （DEAD-REF 必修 / ORPHAN 提示 / OK 计数；`![](…)` 与 `<img src>` 双收集，
  相对 md 所在目录解析，外链跳过；退出码 0/1/2）。
- **scripts/check_readme.py**：README 八项卫生核验（UTF-8 / H1 / 徽章行 /
  图片落盘 / 相对链接目标 / mermaid 语法头 / 围栏配对 / 空链接；WARN 级两档：
  缺徽章、缺架构图；退出码 0/1/2）。
- **红线萃取（源于实战）**：
  - 数字一律抄事实源（AGENTS/CHANGELOG），README 不写密码/授权码；
  - 完全后台静默截图四件套：`ShowActivated=false` + `ShowInTaskbar=false` +
    `-20000` 离屏 + **RTB 按 DPI 渲染优先成品**（print 离屏拍黑边被实测否决）；
  - harness pack URI 必具名（`<程序集>;component/…`——斜杠相对 URI 在 harness 404）；
    主题/字典换装按 Source 认槽替换，盲替 `merged[0]` 半坏视觉（实测踩平）；
  - Markdown 表格单元格禁换行；mermaid 只用 GitHub 原生渲染集语法。
- **实战验证**：对 CureLine 仓库首跑即抓到 README 文档导航 2 处真死链
  （"固化程序"→"固化程控"错字致 docs 链 404），修后 checked RESULT: OK——
  脚本有效性当场验证。
