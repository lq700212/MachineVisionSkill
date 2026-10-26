# MachineVisionSkill

机器视觉方向的 AI Skill 集合，兼容 ZCode / OpenCode 的 skills 机制。每个 skill 目录自包含（SKILL.md 使用说明 + 脚本 + 资产 + CHANGELOG 版本史），可独立安装使用。

## Skill 一览

「DSH 调用名」= SKILL.md frontmatter 里的 `name`，也是 DeepSeek Harness 里 `/` 手势和
`skill` 工具使用的名字。DSH 加载器硬校验 `^[a-z0-9]+(-[a-z0-9]+)*$`，中文名会被**静默丢弃**，
所以目录名可以中文、调用名必须 ASCII（改名对应关系见下表，2026-10-22 统一整改）。

| Skill 目录 | DSH 调用名 | 说明 | 使用文档 |
|-------|------|------|----------|
| [视觉硬件选型](视觉硬件选型/) | `vision-hardware-selection` | 机器视觉选型专家：相机/镜头/光源自动选型计算、方案 PPT 生成、官网产品图自动获取 | [SKILL.md](视觉硬件选型/SKILL.md) |
| [视觉选型测试](视觉选型测试/) | `vision-selection-test` | 视觉硬件选型专用测试套件：回归 + 注入用例，开发迭代后一键全量验证 | [SKILL.md](视觉选型测试/SKILL.md) |
| [git自动提交推送](git自动提交推送/) | `git-auto-commit-push` | 本地工程一键 commit + push：自动读 CHANGELOG 生成 message（含要点提炼），提交前安全检查（可联动仓库卫生体检），现场目录用显式暂存 | [SKILL.md](git自动提交推送/SKILL.md) |
| [winforms-ui-debug](winforms-ui-debug/) | `winforms-ui-debug` | 跨项目 WinForms 界面像素级调试：harness 指哪打哪直启目标窗体，反射探查 + 截图 + 像素扫描，附矩形枚举/置顶截图脚本 | [SKILL.md](winforms-ui-debug/SKILL.md) |
| [上位机通讯封装](上位机通讯封装/) | `hmi-comm-wrapper` | 上位机设备通讯范式：PLC/相机/仪表/Modbus 连接管理、心跳重连、UI 解耦 | [SKILL.md](上位机通讯封装/SKILL.md) |
| [上位机报价](上位机报价/) | `hmi-quotation` | 上位机项目报价全流程：IO表摸底→参考程序体检→市场调研→两本账人力→报价阶梯→核验 | [SKILL.md](上位机报价/SKILL.md) |
| [opencode-cache-cleaner](opencode-cache-cleaner/) | `opencode-cache-cleaner` | 清理 opencode 残留项目记录与孤儿快照：列出→选择→备份→删除→验证 | [SKILL.md](opencode-cache-cleaner/SKILL.md) |
| [盖章专员](盖章专员/) | `seal-stamp-agent` | PDF 合同自动盖章：自动匹配现有印章的大小与位置 | [SKILL.md](盖章专员/SKILL.md) |
| [培训文档生成](培训文档生成/) | `training-doc-generator` | 工业上位机三份制培训文档：自动截图 → 操作员/技术工艺/内部版三份生成 | [SKILL.md](培训文档生成/SKILL.md) |
| [软件卸载清理](软件卸载清理/) | `software-uninstall-cleaner` | 通用软件彻底卸载与残留清理：进程→卸载→服务→目录/注册表/快捷方式 | [SKILL.md](软件卸载清理/SKILL.md) |
| [viewturbo-checkin](viewturbo-checkin/) | `viewturbo-checkin` | ViewTurbo 每日签到领流量 | [SKILL.md](viewturbo-checkin/SKILL.md) |
| [dashi-ppt](dashi-ppt/) | `dashi-ppt` | 预置视觉主题的 HTML 演示生成，可导出 PPTX / PDF | [SKILL.md](dashi-ppt/SKILL.md) |
| [image-to-editable-ppt](image-to-editable-ppt/) | `image-to-editable-ppt` | 把图片/扫描版 PPT、PDF 重建为对象级可编辑 .pptx | [SKILL.md](image-to-editable-ppt/SKILL.md) |
| [PPT智能合并](PPT智能合并/) | `ppt-merge` | 复刻模板母版到结果文件，基于结果母版建新页并复制内容形状 | [SKILL.md](PPT智能合并/SKILL.md) |
| [docx中文转英文](docx中文转英文/) | `docx-cn-to-en` | 中文 .docx 批量翻译成英文 .docx，保留字体/加粗/列宽/拓扑图 | [SKILL.md](docx中文转英文/SKILL.md) |
| [solidworks-automation](solidworks-automation/) | `solidworks-automation` | SolidWorks CAD 自动化：Python COM 建模/装配/工程图/钣金/焊件/仿真 | [SKILL.md](solidworks-automation/SKILL.md) |
| [pdf-analysis](pdf-analysis/) | `pdf-analysis` | PDF 三步法：摸底→关键词定位→分页精读，结论带页码引用 | [SKILL.md](pdf-analysis/SKILL.md) |

> 各 skill 的版本与变化记录见其目录内的 CHANGELOG.md。

## 安装

```bash
git clone https://github.com/lq700212/MachineVisionSkill.git
```

把需要的 skill 目录链接到客户端 skills 目录即可被识别（Windows 目录联接示例）：

```cmd
mklink /J "C:\Users\Administrator\.config\opencode\skills\视觉硬件选型" "D:\path\to\MachineVisionSkill\视觉硬件选型"
```

ZCode 用户也可链接到 `.agents\skills\`；直接复制目录同样可用。

### 挂到 DeepSeek Harness（DSH）

DSH 的 skill 加载器扫描这些根目录（按 rank 递增，前者优先）：

| Rank | 来源 | 路径 |
|---|---|---|
| 100 | project-dsh | `<项目根>/.dsh/skills` |
| 200 | project-agents | `<项目根>/.agents/skills` |
| 300 | custom | `customSkillDirs`（配置项） |
| 400 | user-dsh | `~/.dsh/skills` |
| 500 | user-agents | `~/.agents/skills` |
| 600 | bundled | 随 DSH 安装的内置 skill |

把本仓库整体挂到 user-agents 根即可，**零拷贝**：

```cmd
mklink /J "C:\Users\Administrator\.agents\skills" "C:\Users\Administrator\.config\opencode\skills"
```

要点：

- **用 junction（`mklink /J`）不用 symlink**：symlink 在 Windows 上需要开发者模式或管理员权限，
  且 git 会把 symlink 存成"链接文本"导致白名单失效（2026-08 历史教训，已改 junction）
- **目录名不影响 DSH**：DSH 只认 SKILL.md frontmatter 的 `name`，目录名可保持中文
- **改了 frontmatter 即时生效**：DSH 监听 skill 根目录，改完 `name`/`description`
  下一轮就进会话目录，**不用重启 DSH**
- **frontmatter 必须有 `name` + `description`**，缺任一或 `name` 不是 kebab-case ASCII 会被跳过

## 版本管理约定

- **每个 skill 独立版本线**：版本与变化记录在各 skill 目录的 `CHANGELOG.md`（格式参考 Keep a Changelog），README 不标版本
- **根目录 `CHANGELOG.md` 是每次改动的总览入口**：改完 skill 后在顶部追加本次记录（改了哪些 skill + 各改了什么 + 验证 + commit message 建议），详细历史仍在各 skill 目录的 `CHANGELOG.md`，两者都要更（见根 `AGENTS.md` 收尾清单）
- commit message 以 skill 名开头，如 `视觉硬件选型: 新增三件套产品图替换`
- 需要发版语义时可用路径式 tag（monorepo 惯例）：`视觉硬件选型/v1.1.0`

## 仓库范围

本仓库按白名单跟踪 skill 目录（见 `.gitignore`）：当前只跟踪 `视觉硬件选型`、`视觉选型测试`、`git自动提交推送`、`winforms-ui-debug`、`上位机通讯封装`、`上位机报价`、`opencode-cache-cleaner`、`盖章专员*`、`viewturbo-checkin`、`培训文档生成`、`软件卸载清理`。新开发的 skill 需要入库时，在 `.gitignore` 加一行 `!目录名/` 并同步更新上表。

> 上表其余 skill（`dashi-ppt`/`image-to-editable-ppt`/`PPT智能合并`/`docx中文转英文`/
> `solidworks-automation`/`pdf-analysis`）是**本地安装、不入库**的第三方/自有 skill，
> 保留在目录里供 DSH 直接引用。
