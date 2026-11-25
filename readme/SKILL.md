---
name: readme
description: >
  项目 README 的标准工作流：任何"写 README / 生成 README / 更新 / 重写 README"
  任务都默认走此流程（**无需用户点明"图文并茂"或"配图"**——本流程的标准产出
  本来就是图文并茂形态），语言/形态无关（GUI、CLI、类库、Web、多组件仓库）：
  事实摸底（先数清"有几个端"，一切数字抄文件，禁编造）→ 图片资产盘点脚本
  → 分端截图决策树（桌面 GUI 后台静默 / 手机模拟器真机 / Web headless /
  无界面用架构图）→ 骨架落稿（单端段或多端分节，**有界面的端必须有界面图**）
  → check_readme.py --ends 分端核验全 PASS 收尾。
  触发词：写 README、生成 README、README 文档、重写 README、更新 README、
  README 配图、界面速览、多端项目 README、项目首页/文档首页。
---

# Skill: readme — 项目 README 标准生成流程（图文并茂为默认形态）

> ⚠️ 本文件必须叫 `SKILL.md`（opencode 按目录下的 SKILL.md 注册技能；
> V1.0.0~V1.1.0 误用 AGENTS.md 承载主指引，导致技能从未进可用列表，
> V1.1.1 修正——重命名即注册，见 CHANGELOG）。

> 原则：**AI 只做判断与文案，能脚本化的环节一律脚本**（图片盘点、卫生核验）；
> 事实一律读项目文件抄取，**禁止编造数字**。
> 底层心法：README 是对外门户——**读者是第一次见到它的人**，5 秒内让他知道
> 这是什么、值不值得看、下一步怎么跑。
> 方法学来源：CureLine V0.0.50 README 重写实证（工业上位机双程序仓库）；
> 本文件全部规范与该项目无关，任意软件项目直接套用。

## 0. 适用范围 & 触发

- **默认级触发（用户拍板）**：**任何 "写 README / 生成 README / 更新 README /
  重写 README" 任务都走本流程**——不必等用户追加"图文并茂/配图"要求；
  本流程的标准产出本来就是图文并茂形态。用户明确要求"纯文字版/极简版"时才降级
  （删界面速览等图墙段），但事实红线与脚本核验照走不降。
- 适用项目形态：GUI 桌面程序、CLI 工具、类库、Web 服务/前端、**多端系统
  （桌面 + 手机 + Web + 后端）**、多程序（多组件）monorepo——流程同一套；
  "图"的形态跟着项目走（界面截图 / 浏览器截图 / mermaid 架构图 / 代码示例），
  **没界面的端不硬凑截图**（见第 3 步决策树）。
- **多端红线（V1.3.0 新增）**：一个仓库里有几个"有界面的端"，README 的界面速览
  就要有几组图，并按端分节介绍。**只展示桌面端、手机端一张图都没有 = 交付缺陷**
  （本 skill 升级的真实来源：Sinan 双端项目 README 只有 WPF 截图，手机端完全缺席）。

## 1. 事实摸底（第 1 步，AI 做，禁跳过）

把"README 里每个数字与功能名词"的**出处**读出来。信源按项目主语言找对应
文件——下表同一格列的是**等价文件家族**，读得到的为准：

| README 里要写什么 | 信源（等价家族） |
| --- | --- |
| 一句话定位 / 项目角色 | 现有 README 头段 / 包描述字段（`package.json` description、`pyproject.toml`、`Cargo.toml`）/ 主入口类与 Main 注释 |
| 技术栈 / 平台 / 语言版本 | 工程文件：`*.csproj`、`pyproject.toml`、`package.json`、`go.mod`、`Cargo.toml`、`pom.xml`、`pubspec.yaml`… |
| 构建 / 运行 / 测试命令 | 开发约定文档（`AGENTS.md`/`CLAUDE.md`/`CONTRIBUTING.md`/`Makefile`/`scripts/` 目录）。**原样抄，勿改写** |
| 版本徽章值（技术栈/测试/构建/协议） | `CHANGELOG` 最新版本头 / 既有 CI 徽章 / 锁过数字的维护文档 |
| 功能清单（每组件 3~6 条） | 模块/包目录结构 + CHANGELOG 近期特性条目 |
| 角色 / 账号表 | 源码角色枚举 / 账号初始化代码（**有才写**） |
| 文档导航 | `docs/` 目录 glob 实际文件名（**勿凭记忆写链接，写错路径=404**） |
| 配置说明 | 配置样例文件（`config.sample.*`/`.env.example`/appsettings 样例）文件名与注释头 |
| 端清单（多端项目） | 顶层目录 + 各端工程文件 + `AGENTS.md` 的目录路由表（见 1.1） |

**红线**：
- 测试数、版本号、账号数、性能数字等一切数字——**读文件抄**；写不准的就不写；
- README 面向外部读者：**不写密码/授权码/内网地址/客户名**（出厂初始密码只说
  "由交付人当面给"，细节留内部文档）；
- 摸底可以读内部文档，但对外的行话要翻译（见第 4 步话术纪律）。

### 1.1 先数清"有几个端"（多端项目必做，单端可略读）

**在写任何字之前**，先产出一张端清单（放草稿即可，不必原样进 README）：

| 端 | 目录 | 技术栈 | 有界面 | 截图来源 | 构建命令 |
| --- | --- | --- | --- | --- | --- |
| 桌面端 | `desktop/` | WPF / .NET 10 | 是 | WPF harness 离屏 RTB | `dotnet build …` |
| 手机端 | `mobile/` | Flutter / Android | 是 | AVD 无头模拟器 + adb | `flutter build apk` |
| 后端 | `server/` | Go / Python | 否 | 架构图代替 | `go build …` |

**判定信号（按优先级）**：

1. 顶层目录名：`desktop/ windows/ mobile/ app/ web/ frontend/ server/ backend/ api/ cli/`；
2. 各端工程文件：`*.sln`/`*.csproj`（桌面）、`pubspec.yaml` + `android/`/`ios/`
   （移动端）、`package.json` + 前端框架依赖（Web）、`go.mod`/`pyproject.toml`
   （服务端）；
3. 文档：`AGENTS.md` 的目录路由表、现有 README 的章节结构、`shared/`/`contracts/`
   说明（**共享目录不是端**）；
4. 构建脚本：`Makefile`/`scripts/`/CI 配置里按目录分开的 job。

**分流规则**：

- 判定为 **1 个端** → 走单端骨架（4.1），原流程不变；
- 判定为 **≥2 个端** → 走多端骨架（4.2），**每个有界面的端独立成节 + 独立图墙**；
- 有界面但暂时没有截图 → 按第 3 步决策树补，**不允许直接省略该端**；
- 无界面的端（后端/CLI/类库）不硬凑截图，用架构图、接口示例、目录树代图；
- **端清单与 README 章节必须一一对应**：写完后用第 6 步 `--ends` 核验，漏一端即 NG。

## 2. 图片资产盘点（第 2 步与收尾各跑一次，脚本）

```powershell
python "<skill目录>\scripts\img_inventory.py" <repo根> [--skip-dir 目录名 ...]
```

- 输出三段：`[DEAD-REF]`（文档引用了但磁盘无 → 必修）/ `[ORPHAN]`（磁盘有但
  无任何文档引用 → 与用户确认删或补引用）/ `[OK]` 计数。退出码 0 无死引用，
  1 有死引用，2 环境错误。
- 相对路径按**该 md 所在目录**解析（README 引 `docs/images/x.png`、docs 手册引
  `images/x.png` 两种口径都好使）；外链 http(s) 跳过；**代码块/行内代码里的
  图片语法不算真引用**（只收渲染真身，模板占位与语法说明不误报）。
- `--skip-dir 目录名`（可重复给多个）：任何层级命中即整枝跳过——用于
  **本地安装不入库的第三方 skill**（其文档死链不属本仓库体检范围，
  如 pixel2motion）与**只被设计稿 HTML 引用的品牌资产目录**（如 `branding`；
  脚本只扫 markdown，HTML 里的引用不计入，会常驻 ORPHAN）；跳过名单会打
  `[INFO]` 行留痕。
- 移动端宿主壳资源目录（Android `res/`、iOS `Assets.xcassets`）已内置排除，
  应用程序图标不会刷屏 ORPHAN（V1.3.0 多端实测修复）。
- **开工跑一次**（摸清家底：有哪些图、哪些链接本来就死）+ **收尾再跑一次**
  （写作过程中的新引用/新删除是否两头对齐）。
- 只看最后一行 `RESULT: OK / NG`；有 DEAD-REF 先修完再进下一步。

**多端图片目录规范（V1.3.0）**：

```text
docs/images/
├── desktop/   ← 桌面端截图（原 docs/images/*.png 可整体迁入）
├── mobile/    ← 手机端截图
├── web/       ← Web 端截图
└── shared/    ← 架构图、Logo、跨端共用图
```

- 按端分目录是默认口径：`img_inventory` 的 ORPHAN 检查会直接暴露"拍了手机图但
  README 没引用"；
- 兼容旧仓库：已存在的 `docs/images/01_login.png` 平铺结构不必强行搬家，
  但**新增的移动端/第二端图片必须进 `docs/images/<end>/`**，避免与桌面图混名；
- 同一张图只引用一次；不同端不要共用截图。

## 3. 截图获取（第 3 步，按端分别走决策树）

**先对每个"有界面的端"各走一遍**，不要只处理第一个端就收工。

每个端的通用判断顺序：

1. **本地图片齐全且口径新**（近期拍过、界面未大改）→ 直接引用，进第 4 步；
2. **项目已有截图能力**（截图脚本 / harness / CI 截图）→ 优先用它重拍补拍；
3. 按端形态建能力（3.1~3.3）；
4. **有界面但什么都没有** → 先问用户走哪条：①先建截图能力（推荐，一次投入
   反复重拍）；②自动化驱动截图；③用户手拍交图。**禁止**让 README 长期引用
   与软件现状不符的旧图。

### 3.1 桌面端（WPF / WinForms 类）

- 首选项目自带 harness（如 `tools/ui_smoke`）；没有则按第 5 节纪律新建；
- 成品口径 **RTB（RenderTargetBitmap）优先**，按 DPI 渲染视觉树；
- 产出落 `docs/images/desktop/`，命名 `<序号>_<页面>.png`。

### 3.2 移动端（Flutter / Android / iOS，V1.3.0 新增）

按可用条件从优到劣：

1. **Android 模拟器（首选，可完全后台）**
   - 列设备：`emulator -list-avds`；无 AVD 时提示用户用 Android Studio 建一个；
   - 无头启动：`emulator -avd <名称> -no-window -no-audio -no-boot-anim -gpu swiftshader_indirect`；
   - 等就绪：`adb wait-for-device` + `adb shell getprop sys.boot_completed`（返回 1）；
   - 装包：`adb install -r mobile/build/app/outputs/flutter-apk/app-debug.apk`；
   - 启动：`adb shell am start -n <包名>/<Activity>`（Flutter 默认 `.MainActivity`）；
   - 截图：`adb exec-out screencap -p > docs/images/mobile/01_login.png`（PNG 直落盘，
     不要用模拟器 GUI 的截图按钮）；
   - 需要登录/翻页：`adb shell input tap <x> <y>`、`adb shell input text <内容>`、
     `adb shell input keyevent 4`（返回）；坐标用 `adb shell wm size` 与截图实测；
   - 截完 `adb exec-out screencap` 再取一张核对页面真的切换了。
2. **真机（USB 调试）**：同上，`adb devices` 出现设备即可；注意真机可能带
   真实通知/账号，**截完必须检查状态栏与通知是否含真实信息**（脱敏红线）。
3. **Flutter golden test（无模拟器兜底）**：用 `flutter test` +
   `matchesGoldenFile` 渲染真实 Widget 树成 PNG；图来自真实渲染链路，不是 P 图。
   适合登录页、列表页、详情页等纯 Flutter 页面。
4. **设计稿截图（最后手段）**：只能作为"界面设计"展示，图注必须写
   **"界面设计稿"**，不得放进"实机界面"图墙；README 的当前进度里要写明
   "实机截图待补"。

- **iOS**：只有 macOS 能跑模拟器（`xcrun simctl io booted screenshot <file>`）。
  在 Windows/Linux 上不得用 Android 图冒充 iOS；README 里如实写"iOS 待 macOS 验证"。
- **图片规格**：按手机原生分辨率截图（如 1080×2400），README 里用
  `<img width="240">` 控制显示宽度；**不要把竖图塞进桌面横图的两列表格**。

### 3.3 Web 前端

- 起本地服务 → headless 浏览器逐页拍（Playwright 一行命令：
  `npx playwright screenshot --viewport-size=<W>,<H> --full-page <url> docs/images/web/<page>.png`）；
- 数据先种成演示态，别拍报错页/空态。

### 3.4 纯类库 / CLI / 后端服务

- **没有界面就不硬凑截图**："图"换成 mermaid 架构图/时序图 + 目录树 + 关键代码示例
  （图文并茂的"图"是广义的）；
- 多端系统里这类端照样要有自己的章节，用架构图/接口示例代替图墙。

## 4. 骨架落稿（第 4 步，AI 写）

结构 = **必备段（人人有）+ 多端段（≥2 端必走）+ 选配段（条件触发，按项目取舍）**。
**骨架是满配上限，不是作文模板——读者不 care 的段落直接删，缺项比硬凑好看。**

### 4.1 必备段（所有项目）

````markdown
<div align="center">

# <项目名>

**<一句话定位——第一次见的读者 5 秒看懂"是什么">**

![<徽章1>](https://img.shields.io/badge/<键>-<值>-<色>?logo=<logo>)
<!-- 3~6 枚；值全部抄第 1 步信源；技术栈/测试/构建状态/协议四类最常配 -->

<项目 1~2 句简介；有血统一句值得带上再写，没有就删>

</div>

---

## 快速开始

```powershell
# <步骤注释>
<命令——原样抄第 1 步构建/运行/验证命令>
```
````

### 4.2 多端骨架（≥2 个端必用，V1.3.0 新增）

核心原则：**先讲系统全景，再按端分节；共享能力单独成节，不在各端重复**。

````markdown
## 这套系统由什么组成

| 端 | 面向谁 | 技术栈 | 状态 |
| --- | --- | --- | --- |
| 桌面端 | 办公室排期/导出 | WPF · .NET 10 | 可用 |
| 手机端 | 现场拍照/推进 | Flutter · Android | 可用 |

## 界面速览

### 桌面端

| <页面1> | <页面2> |
| --- | --- |
| ![](docs/images/desktop/01_overview.png) | ![](docs/images/desktop/02_detail.png) |

### 手机端

<p align="center">
  <img src="docs/images/mobile/01_login.png" width="220" alt="登录">
  <img src="docs/images/mobile/02_todo.png" width="220" alt="待办">
  <img src="docs/images/mobile/03_detail.png" width="220" alt="问题详情">
</p>

## 桌面端

<一句话定位：谁在什么场景用>

- **<核心能力>**：<一句话说清>；
- …（3~6 条，只写这一端独有的）

### 桌面端快速开始

```powershell
<该端的构建/运行/测试命令>
```

## 手机端

<一句话定位：谁在什么场景用>

- **<核心能力>**：<一句话说清>；
- …（3~6 条）

### 手机端快速开始

```bash
<该端的构建/运行/测试命令>
```

## 共享能力与数据契约

<两端共用的 DDL/种子/同步协议/账号体系；放这里，不在端小节重复>
````

**多端排版红线**：

- **端小节顺序按产品主次**（主库/主程序在前），不按目录字母序；
- **每个有界面的端必须有独立图墙**，图注写清「<端> · <页面>」；
- 手机竖图**不与桌面横图同表**：用 `<p align="center">` + `<img width="220~280">`，
  或单独 3 列窄表；桌面图用 2 列宽表；
- 端名在全文统一（不要一处"现场端"、一处"移动端"、一处"手机端"混用；
  首次出现可写「手机端（现场端）」）；
- 每端快速开始只写该端命令；共享步骤（子模块初始化、环境变量）放"共享/通用"节；
- 多端项目的徽章按端各配一枚，别只放主端技术栈；
- **功能清单按端归属**：桌面独有的 Excel 无损、手机独有的拍照/离线队列，
  不要混在"核心能力"里让读者以为两端都支持。

### 4.3 选配段（条件触发；下面是全家福，用不到的整节删）

````markdown
## 账号与权限（<N> 级角色）
<!-- 条件：有角色/权限体系才写 -->

| 账号 | 角色 | 权限 |
| --- | --- | --- |

## 架构
<!-- 条件：组件 >1 或层次关系值得画；多端项目基本必写 -->

```mermaid
graph LR
    …
```

- <架构文字要点 2 条；mermaid 只用 GitHub 原生渲染集>

## 目录树

```text
<repo>/
├── …（一层两深度以内；每行一句"这里放什么"）
```

## 文档导航
<!-- 条件：项目有 docs/ 类文档 -->

| 手册 | 链接 |
| --- | --- |
<!-- 链接文字 = 文档实际标题（错别字=404，实锤踩过——逐条对 glob 验） -->

## 配置
<!-- 条件：有配置键体系 -->

<一句话说清"缺配置会怎样（自动回缺省吗）"；指向样例文件"逐键注释见 xxx"——
正文不复制细节>
````

**话术纪律（对外门户）**：
- 内部行话必须翻译成读者语言（例如内部词"自愈播种/热更"对外是"开箱即用免手工
  初始化/改配置免重启"）；
- 命令块必须可复制直接跑，不放"看起来很美"的不可执行命令；
- 声称的行为 = 实际行为，**夸大与超额承诺零容忍**。

**排版红线**：
- 图片一律相对路径（README 引 `docs/images/…`，docs 手册引 `images/…`——
  脚本两种口径都好使）；
- 徽章行必须在顶部 `div align="center"` 里；shields.io 短色值风格统一；
- mermaid 只用 `graph/flowchart` + `subgraph`（GitHub 原生渲染，不引插件语法）；
- 语言跟随项目与目标读者；**表格单元格不换行**（会破渲染）；
- 演示截图必须真实链路驱动（demo/mock 数据可以，**P 图禁**）；
- H1 之后 5 秒内让读者明白"这是什么"，长解读放后段。

## 5. 截图纪律（仅 GUI 截图链路消费；Web/无界面端跳过本节）

**通用人心（任何技术栈都成立）**：截图进程必须**完全后台安静**——不抢焦点、
不进任务栏、不碰用户正在用的屏幕；**界面不在前台也要拍到正确的图**。

### 5.1 GUI 桌面（.NET WPF/WinForms 类）harness 专项

四件套（写截图 harness 的统一 Show 前处理）：

1. `ShowActivated=false`（不抢键盘焦点）；
2. `ShowInTaskbar=false`（任务栏不蹦图标）；
3. `Left/Top=-20000` 完全离屏（压过 XAML CenterOwner/Maximized 等布局行为）；
4. 成品口径 **RTB（RenderTargetBitmap）优先**：按 `VisualTreeHelper.GetDpi` 缩放
   渲染视觉树——无 DWM 阴影黑边、不含任务栏/桌面像素、与窗口位置无关；
   `PrintWindow` 只作兜底（离屏下 print 必拍黑边/全黑，已被实测否决）。

WPF 专项坑（防重蹈）：
- 相对 pack URI（`"/Themes/Dark.xaml"`）在 harness 里相对 Application 根
  （=harness 程序集）404——用 `pack://application:,,,/<程序集>;component/…`
  具名 URI；
- 主题字典换装**只换语义槽**：按 `Source` 认出主题字典在 merged 槽位的位置再
  替换；盲替 `merged[0]` 会把主样式字典换没（半坏视觉）。

### 5.2 移动端专项（V1.3.0 新增）

- **无头模拟器**：`-no-window` 启动，adb 驱动，完全不抢焦点；不要用会弹窗口的
  `flutter run` 手动截图；
- **演示态**：先登录演示账号、进到有数据的页面再截；空态/报错页/加载中不截；
- **脱敏**：模拟器状态栏时间/电量可入镜；**通知、运营商、账号名、真实手机号
  一律不许入镜**；真机截图逐张检查状态栏；
- **尺寸统一**：同一端所有图用同一分辨率；README 用 `width` 属性统一显示宽度；
- **核对页面真的切了**：`adb shell dumpsys activity activities | grep mResumedActivity`
  或再截一张目检，防止 tap 没命中；
- 拍完自己先目检一遍（文字无乱码、无遮挡、无真实数据）再对外。

### 5.3 Web 专项坑

- 拍图前把本地服务数据**种成演示态**（mock 种子 / demo 账号），别拍报错页、
  空数据页、登录前半成品；
- 截图宽度统一（如 1440），别一张 800 一张 1920，排版跳动难看。

## 6. 卫生核验（第 5 步，脚本，全 PASS 才算完）

```powershell
# 单端项目
python "<skill目录>\scripts\check_readme.py" <repo根>

# 多端项目：显式声明端清单（推荐，缺一端即 NG）
python "<skill目录>\scripts\check_readme.py" <repo根> --ends desktop,mobile
```

检查项：

1. UTF-8 可读；
2. H1 在；
3. 徽章行存在性（WARN 级）；
4. 图片落盘；
5. 相对链接目标存在；
6. mermaid 语法头（GitHub 原生渲染集）；
7. ``` 围栏成对；
8. 空链接拦截；
9. **多端分节**（V1.3.0）：`--ends` 里每个端在 README 有对应 H2/H3 小节；
10. **多端图墙**（V1.3.0）：`--ends` 里每个端至少有 1 张该端图片
    （按 `docs/images/<end>/`、文件名前缀、或该端小节内的图片判定）。

不传 `--ends` 时脚本自动探测端：探测到 ≥2 个端会启用分端检查，但降为 WARN
（避免把故意不展示的端误判为 NG）；**AI 一旦确认了端清单，就应显式传 `--ends`
把它锁成 NG**。退出码 0=OK，1=NG；有 NG **逐条修完重跑**，不许带病交付。

## 7. 收尾（第 6~7 步）

1. **复跑两个脚本全 PASS**（img_inventory + check_readme；多端项目带
   `--ends desktop,mobile,…`）——写作过程的改动也要过闸；
2. **逐端目检**：每个有界面的端 ≥2 张图、图是当前版本界面、图注端名一致、
   手机端没有把设计稿标成实机；
3. 项目 `CHANGELOG.md` 记一笔（范围 + 为什么；项目没有 CHANGELOG 则跳过）；
4. **不主动 commit/push**——用户明确要求才提（本机如有自动提交 skill/流程，
   按其安全检查链走）；
5. 临时脚本/临时截图用完即删（不留调试残骸）。
