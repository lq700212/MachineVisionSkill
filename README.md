<div align="center">

# MachineVisionSkill

**AI 代理 skills 集合——覆盖工业上位机（视觉选型 / 报价 / 通讯 / 培训文档 / UI 调试）与办公自动化（盖章 / PPT / docx / PDF / git 提交），兼容 OpenCode / DSH 的 skills 机制。**

![Skills](https://img.shields.io/badge/skills-12-orange)
![Platform](https://img.shields.io/badge/platform-Windows-blue?logo=windows)
![Scripts](https://img.shields.io/badge/scripts-Python%20%7C%20PowerShell-informational)
![Client](https://img.shields.io/badge/OpenCode%2FDSH-%E5%85%BC%E5%AE%B9-success)

每个 skill 目录自包含：`SKILL.md`（使用说明）＋ 脚本 + 资产 ＋ `CHANGELOG.md`（版本史），可独立安装使用。
名字叫 MachineVisionSkill 是因为起点是机器视觉选型——如今已生长为一整条工业上位机工具带，仓库沿用此名。

</div>

---

## 快速开始

```cmd
git clone https://github.com/lq700212/MachineVisionSkill.git
```

把需要的 skill 目录链接（或直接复制）到客户端 skills 根即可被识别，Windows 目录联接示例：

```cmd
mklink /J "C:\Users\Administrator\.config\opencode\skills\视觉硬件选型" "D:\path\to\MachineVisionSkill\视觉硬件选型"
```

直接复制目录同样可用。

### 挂到 DeepSeek Harness（DSH）：整仓零拷贝

DSH 的 skill 加载器扫描这些根目录（按 rank 递增，前者优先生效）：

| Rank | 来源 | 路径 |
|---|---|---|
| 100 | project-dsh | `<项目根>/.dsh/skills` |
| 200 | project-agents | `<项目根>/.agents/skills` |
| 300 | custom | `customSkillDirs`（配置项） |
| 400 | user-dsh | `~/.dsh/skills` |
| 500 | user-agents | `~/.agents/skills` |
| 600 | bundled | 随 DSH 安装的内置 skill |

把本仓库整体挂到 user-agents 根，`mklink /J` 一条命令全量接入：

```cmd
mklink /J "C:\Users\Administrator\.agents\skills" "C:\Users\Administrator\.config\opencode\skills"
```

接入要点（2026-08 起实测沉淀）：

- **用 junction（`mklink /J`）不用 symlink**：symlink 需要 Windows 开发者模式或管理员权限，且 git 会把 symlink 存成"链接文本"导致仓库白名单失效——已改 junction；
- **目录名不影响 DSH**：DSH 只认 `SKILL.md` frontmatter 的 `name` 字段，目录名可以保持中文；
- **改了 frontmatter 即时生效**：DSH 监听 skill 根目录，改完 `name`/`description` 下一轮就进会话目录，**不用重启**；
- **frontmatter 必须有 `name` + `description`**，缺任一项、或 `name` 不是 kebab-case ASCII（`^[a-z0-9]+(-[a-z0-9]+)*$`）的 skill 会被**静默丢弃**——中文名 skill 一律配一个 ASCII 调用名（见下表）。

## Skill 一览（14 个入库 skill）

| Skill 目录 | DSH 调用名 | 说明 | 使用文档 |
|-------|------|------|----------|
| [视觉硬件选型](视觉硬件选型/) | `vision-hardware-selection` | 机器视觉选型专家：相机/镜头/光源自动选型计算、方案 PPT 生成、官网产品图自动获取 | [SKILL.md](视觉硬件选型/SKILL.md) |
| [视觉选型测试](视觉选型测试/) | `vision-selection-test` | 视觉硬件选型专用测试套件：回归 + 注入用例，开发迭代后一键全量验证 | [SKILL.md](视觉选型测试/SKILL.md) |
| [git自动提交推送](git自动提交推送/) | `git-auto-commit-push` | 本地工程一键 commit + push：自动读 CHANGELOG 生成 message（含要点提炼），提交前安全检查（可联动仓库卫生体检），现场目录用显式暂存 | [SKILL.md](git自动提交推送/SKILL.md) |
| [winforms-ui-debug](winforms-ui-debug/) | `winforms-ui-debug` | 跨项目 WinForms 界面像素级调试：harness 指哪打哪直启目标窗体，反射探查 + 截图 + 像素扫描，附矩形枚举/置顶截图脚本 | [SKILL.md](winforms-ui-debug/SKILL.md) |
| [上位机通讯封装](上位机通讯封装/) | `hmi-comm-wrapper` | 上位机设备通讯范式：PLC/相机/仪表/Modbus 连接管理、心跳重连、UI 解耦 | [SKILL.md](上位机通讯封装/SKILL.md) |
| [上位机报价](上位机报价/) | `hmi-quotation` | 上位机项目报价全流程：IO表摸底→参考程序体检→市场调研→两本账人力→报价阶梯→核验 | [SKILL.md](上位机报价/SKILL.md) |
| [opencode-cache-cleaner](opencode-cache-cleaner/) | `opencode-cache-cleaner` | 清理 opencode 残留项目记录与孤儿快照：列出→选择→备份→删除→验证 | [SKILL.md](opencode-cache-cleaner/SKILL.md) |
| [盖章专员](盖章专员/) | `seal-stamp-agent` | PDF 合同自动盖章：自动匹配现有印章的大小与位置；支持文本版/扫描件 PDF、图片（拍照件）、Excel 工作簿四类输入 | [SKILL.md](盖章专员/SKILL.md) |
| [培训文档生成](培训文档生成/) | `training-doc-generator` | 工业上位机三份制培训文档：自动截图 → 操作员/客户技术工艺/内部版三份生成 | [SKILL.md](培训文档生成/SKILL.md) |
| [软件卸载清理](软件卸载清理/) | `software-uninstall-cleaner` | 通用软件彻底卸载与残留清理：进程→卸载→服务→目录/注册表/快捷方式 | [SKILL.md](软件卸载清理/SKILL.md) |
| [readme](readme/) | `readme` | 项目 README 标准生成流程：事实摸底→图片盘点→截图决策树→骨架落稿→八项卫生核验，图文并茂为默认形态 | [SKILL.md](readme/SKILL.md) |
| [viewturbo-checkin](viewturbo-checkin/) | `viewturbo-checkin` | ViewTurbo 每日签到领流量（真实账号文件永不入库，只提交 example 模板） | [SKILL.md](viewturbo-checkin/SKILL.md) |
| [scanner-config](scanner-config/) | `scanner-config` | 扫码枪 Eport-E10 串口联网模块网络配置与排障：改 IP/8899 端口、连接超时/169.254.x.x 诊断、恢复出厂重建，附 ScannerTool.ps1 | [SKILL.md](scanner-config/SKILL.md) |
| [ui-simplify](ui-simplify/) | `ui-simplify` | 上位机界面简化与目检标准：决策字段上界面/语境进 ToolTip/结果进提示条，界面改动后的截图目检收尾 | [SKILL.md](ui-simplify/SKILL.md) |

> 各 skill 的版本与变化记录见其目录内的 `CHANGELOG.md`。

### 本地安装、不入库（7 个）

以下 skill 随本机 opencode 直接加载、不在 GitHub 仓库跟踪范围内（clone 本仓库看不到它们的目录），仅供参考：

| 调用名 | 说明 |
|------|------|
| `dashi-ppt` | 预置视觉主题的 HTML 演示生成，可导出 PPTX / PDF |
| `image-to-editable-ppt` | 把图片/扫描版 PPT、PDF 重建为对象级可编辑 .pptx |
| `ppt-merge` | 复刻模板母版到结果文件，基于结果母版建新页并复制内容形状 |
| `docx-cn-to-en` | 中文 .docx 批量翻译成英文 .docx，保留字体/加粗/列宽/拓扑图 |
| `solidworks-automation` | SolidWorks CAD 自动化：Python COM 建模/装配/工程图/钣金/焊件/仿真 |
| `pdf-analysis` | PDF 三步法：摸底→关键词定位→分页精读，结论带页码引用 |
| `pixel2motion` | 位图 Logo 转极简 SVG 并生成品牌动效（HTML 呈现） |

## 架构

```mermaid
graph LR
    subgraph G1["客户端 loader"]
        OC["OpenCode"]
        DSH["DSH（校验 name 为 kebab-case ASCII）"]
    end
    subgraph G2["skill 路径根（按 rank 扫描：project 优先于 user）"]
        PR["项目级 / .agents/skills"]
        UR["用户级 ~/.agents/skills —— junction 指向本仓库"]
    end
    subgraph G3["本仓库（唯一真身）"]
        SK["12 个入库 skill 目录：SKILL.md + 脚本 + CHANGELOG"]
    end
    OC --> PR
    DSH --> UR
    PR -- "mklink /J 或拷贝单目录" --> SK
    UR -- "零拷贝整仓引用" --> SK
```

- **唯一实体归一**：全部 SKILL.md 只有一份真身（本仓库），其余位置一律 junction 指回——改一处即热更新到所有客户端；
- **脚本为主、AI 为辅**：每个 skill 的可执行环节都沉淀成脚本（图片盘点、卫生核验、选型计算、盖章编排…），弱模型照脚本输出的 SOP 抄执行，即得与强模型同款结果。

## 目录树

```text
MachineVisionSkill/
├── 视觉硬件选型/            # 相机·镜头·光源选型 + 方案 PPT + 官网产品图
├── 视觉选型测试/            # 上一条的回归/注入测试套件
├── 上位机报价/              # 报价六步法 + IO/代码体检 + 核验脚本
├── 上位机通讯封装/          # 设备通讯范式（纯文档沉淀）
├── 培训文档生成/            # 三份制培训文档 + 截图防卡住工具
├── 盖章专员/                # 盖章编排脚本 + 测试夹具
├── 软件卸载清理/            # 8 阶段卸载 PowerShell（-DryRun 可预览）
├── git自动提交推送/         # commit + push 编排脚本
├── viewturbo-checkin/       # 签到脚本（模板入库、真账号忽略）
├── opencode-cache-cleaner/  # opencode 残留记录清理
├── winforms-ui-debug/       # UI 调试 harness 与取证脚本
├── readme/                  # 本 skill：README 流程 + 两个核验脚本
├── dashi-ppt/ 等 7 个目录    # 本地安装不入库（见上表），随 opencode 直接加载
├── README.md                # 本文件
├── CHANGELOG.md             # 全仓库变更总览（时间倒序，每条含 commit message 建议）
└── AGENTS.md                # 改 skill 前必读的铁律与收尾清单
```

## 版本管理约定

- **每个 skill 独立版本线**：版本与变化记录在各 skill 目录的 `CHANGELOG.md`（格式参考 Keep a Changelog），README 不标版本；
- **根目录 `CHANGELOG.md` 是每次改动的总览入口**：改完 skill 后在顶部追加本次记录（改了哪些 skill + 各改了什么 + 验证 + commit message 建议），详细历史仍在各 skill 目录的 `CHANGELOG.md`，两者都要更（见根 `AGENTS.md` 收尾清单）；
- commit message 以 skill 名开头，如 `视觉硬件选型: 新增三件套产品图替换`；
- 需要发版语义时可用路径式 tag（monorepo 惯例）：`视觉硬件选型/v1.1.0`。

## 仓库范围

本仓库按白名单跟踪 skill 目录（见 `.gitignore`）：当前只跟踪 `视觉硬件选型`、`视觉选型测试`、`git自动提交推送`、`winforms-ui-debug`、`上位机通讯封装`、`上位机报价`、`opencode-cache-cleaner`、`盖章专员*`、`viewturbo-checkin`、`培训文档生成`、`软件卸载清理`、`readme`。新开发的 skill 需要入库时，在 `.gitignore` 加一行 `!目录名/` 并同步更新上表与根 `AGENTS.md` 放行清单。

> 上表其余 skill（`dashi-ppt`/`image-to-editable-ppt`/`PPT智能合并`/`docx中文转英文`/`solidworks-automation`/`pdf-analysis`/`pixel2motion`）是**本地安装、不入库**的第三方/自有 skill，保留在目录里供 opencode / DSH 直接引用。
