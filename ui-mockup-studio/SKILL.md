---
name: ui-mockup-studio
description: >
  UI 设计稿工作台 + 界面简化标准（WinForms / WPF 双栈）。基于 uiverse galaxy 组件库，
  一次产出 4-5 套干净整洁的界面设计方案，输出为单文件 HTML（可离线打开），面面俱到覆盖
  主界面 / 全部子页面 / 全部弹窗 / 多状态（默认/空/加载/错误），按钮可点、弹窗可开、
  页面可跳转，并自动生成页面跳转关系图与切换动效；规范视图内置 galaxy → WinForms 与
  galaxy → WPF 两套落地映射（从当前方案 Token 实时生成代码）。
  当用户说"做 UI 设计稿 / 出界面设计方案 / 画原型 / 出 mockup / 界面美化方案 /
  做几版 UI 给我选 / 重新设计界面 / 设计系统 / 出高保真效果图 / 页面跳转关系 / 弹窗设计"，
  或"设计软件图标 / 出 logo / 设计 app icon / 应用图标出几版 / 图标转项目资源"，
  或"界面太复杂 / 简化页面 / 看着乱 / 降低学习成本 / 能合并就合并 / 按钮太多 /
  配置项太多 / 简单好上手"，或要新建/优化配置窗、表单页、设置页，以及界面改动完成后的
  截图目检收尾时使用。适用于任何项目的 UI 设计、美化与简化任务。
---

# Skill: ui-mockup-studio —— 设计稿工作台 + 界面简化标准

> 本 skill 只解决一件事：把界面**想清楚 → 出几版稿 → 落成代码**。
> 三种用法共用同一套标准（信息预算 + 炫点配额 + 双栈映射）：
>
> - **模式 A 出设计稿**：产出可点击、可切换、可演示跳转与动效的**单文件 HTML 工作台**，
>   含 4-5 套视觉方案 × 明暗主题 × 全部页面与弹窗。用户拿去评审、选型、给客户看。
> - **模式 B 简化现有界面**：按 `references/simplify-playbook.md` 直接改代码，改完截图目检。
> - **模式 C 简化 + 换视觉**：先做信息架构减法（定页面/弹窗/字段），再出设计稿，
>   最后按选中方案落代码。**顺序不能反**——先出稿再减法 = 五套稿一起返工。

---

## 0. 先判定走哪种模式（30 秒）

| 用户说的话 | 模式 | 先做什么 | 产出 |
| --- | --- | --- | --- |
| "做几版 UI 给我选 / 出设计稿 / 重新设计 / 给客户看" | A | 摸底 → 减法 → galaxy 选型 → 出稿 | `Docs/ui_design_mockups.html` |
| "界面太复杂 / 简化 / 看着乱 / 降低学习成本 / 配置项太多" | B | 读 `simplify-playbook` → 改代码 | 改完的窗体 + 截图目检 |
| 既要重做视觉，又嫌现在复杂 | C | 先减法定信息架构 → 再出稿 → 再落码 | 设计稿 + 落地代码 |
| "这个按钮/颜色/对齐不对" | 直接修 | 截图定位 → 改 → 再截图 | 修复 + 目检 |

拿不准就问一句"你是要出几版稿选一下，还是直接把现在这版改简单？"——不要两种一起瞎干。

---

## 1. 铁律（违反即返工）

**视觉来源**

1. **一切视觉语言来自 galaxy + 风格基因池**。按钮圆角/渐变/阴影/开关/加载动画，先去
   `E:\Project\galaxy`（或缓存路径）里找同款，再映射成目标技术栈。方案的"跳跃"必须
   可追溯：要么来自 galaxy 组件的气质，要么来自基因池原型（`design-playbook.md` 第五节）
   ——**禁止拍脑袋自创**，禁止"我记得某个 Bootstrap 样子"。
2. **页面 DOM 只写一次，方案 = Token 切换 + 基因切换**。5 套方案绝不允许复制 5 份页面
   DOM（会失控、跳转图重复、改一处要改五处）。换方案只换 `html[data-variant]`。
   唯一例外：**门面页（主界面等 ≤3 页）可用 `data-layout` 做有限构图分叉**——
   每页 ≤3 套布局，块内只做容器重排、不重写控件；常规子页/弹窗 DOM 仍然只写一次。
3. **禁止写死色值/圆角/间距**。页面里只能出现 `var(--primary)` `var(--radius)` 这类
   Token；写死一个 `#3e8bff`，那套方案切过去就破相。
4. **卡片式页面必须交付「卡片规范」整章**（模板已在规范视图内置）：
   解剖（真实 DOM）+ 参数表（实时读 Token）+ 状态矩阵（默认/悬停/选中/告警/焦点/禁用）
   + **按职责的变体库（至少 6 种）**。卡片只有一句 `.card{...}` = 没设计。
   变体按职责选、不按喜好选：容器 / 指标 / 列表 / 告警 / 顶线 / 内嵌 / 瓦片 / 折叠 / 玻璃，
   同一页面最多同时出现 3 种卡片语言（容器与指标同族算一种，告警算一种，内嵌分区不算独立语言）。

**交互完整**

5. **每个用户会点的业务按钮都必须声明跳转**：切页 `data-go="页面id"`、
   开弹窗 `data-open="弹窗id"`。漏一个，跳转关系图和右栏"交互与跳转"就少一条，
   用户点下去没反应 = 交付不合格。
6. **弹窗多状态用多个 `data-dialog` 表达**（默认态/展开态/确认态各一个），
   不要把复杂状态机塞进弹窗内部 JS。
7. **单文件离线可用**：禁止外链 CDN / 外链字体 / 外链图片（现场电脑常常没网）。

**减法（用户明确要求，默认执行）**

8. **界面只放"要用户做的决定"**：字段键名/寄存器号/格式约束 → ToolTip；
   全局口径 → 顶部一行提示条；**永远不建"说明书列/说明卡"**。
9. **遵守信息预算**（详见 `simplify-playbook` 第二节）：一屏主操作 1 个、
   按钮 ≤ 10（硬上限 12）、顶栏可点 ≤ 4、侧栏 ≤ 7、开关 ≤ 3（硬上限 5）、
   一个页签首屏字段 ≤ 8、一行筛选 ≤ 4 个控件、表格行操作 ≤ 1 个"⋯"、
   页面说明 ≤ 60 字、单条要点 ≤ 40 字。**超预算必须在右栏写一句为什么**。
10. **一屏只允许 1 个循环炫点**（模板示范：相机磁贴扫描光带 4.2s / 主色 13% / 四块错峰）。
    表单、表格、正文**禁止炫**。关掉动效后信息必须仍然完整可读。

**双栈落地**

11. **规范视图必须同时内置 WinForms 与 WPF 两套映射卡**，`data-stack` 只决定哪张高亮
    为目标栈。映射值必须从 `getComputedStyle` 实时取 Token，**禁止写死**——
    否则切方案时两套代码不跟着变，评审时无法指着说"这套在我们项目里就是这几个常量"。
12. **落地映射必须遵守两栈各自的坑位清单**（WinForms 见 `simplify-playbook` 第八节，
    WPF 见第七节，CSS → 控件映射见 `galaxy-map.md`）。

**交付验收**

13. **交付前 `check_mockup.py` 必须 0 FAIL**（33 项：结构/跳转/编码/离线/两栈/卡片/
    文字色 + **方案差异度 C23~C26**），并至少截图目检：舞台、总览、跳转图、规范（两栈）、
    一个弹窗（含展开态）、**5 套方案逐套切一遍**（每套都要像不同的作品）。
    只看代码不截图 = 没验收。
14. **文件必须严格 UTF-8**。禁止用 PowerShell `Out-File`/`Add-Content` 写含中文的 HTML；
    用 write / edit 工具。终端中文乱码是 GBK 显示假象，判定内容请用 read 工具。

---

## 2. 目录与脚本

```
~/.config/opencode/skills/ui-mockup-studio/
├── SKILL.md                      本文件（模式判定 + 工作流 + 红线）
├── config.json                   galaxy 路径缓存（自动生成，不要手改）
├── scripts/
│   ├── resolve_galaxy.py         定位 galaxy；找不到就 git clone 到 D:\galaxy；写缓存
│   ├── galaxy_search.py          按 tags 检索组件 / 看源码 / 随机抽样 / 列分类
│   ├── new_mockup.py             从模板生成设计稿到项目 Docs（支持 --stack）
│   ├── check_mockup.py           交付前 33 项核验（结构/跳转/编码/离线/两栈/卡片体系/文字色继承/减法预算/方案差异度 C23~C26）
│   └── svg2res.py                图标 SVG → 项目资源：preview 生成选款预览页 / convert 出 PNG 阶梯 512~16 + 多帧 ICO
├── templates/
│   └── mockup_base.html          工作台模板（5 方案 9 基因 Token + 5 种壳构图 + 4 视图 + 3 示例页 + 3 弹窗 + 双栈映射）
└── references/
    ├── design-playbook.md        设计方法与"干净整洁"的硬指标（写页面前必读）
    ├── simplify-playbook.md      简化现有界面的完整标准（原 ui-simplify 并入）
    ├── mockup-spec.md            data-* 速查 + 页面/弹窗代码片段 + 完整度清单 + 预算自检
    ├── galaxy-map.md             galaxy 分类地图 + 检索词 + WinForms/WPF 两套映射代码
    └── logo-playbook.md          软件图标设计手册（口径/几何红线/小尺寸纪律/转资源接入）
```

脚本一律用 `python` 运行（Windows 上 `python` 已是 3.x）。路径含中文时，
脚本内部全部用 `io.open(..., encoding="utf-8")`，不受终端代码页影响。

---

## 3. 工作流（模式 A / C 走这条；模式 B 直接跳第 7 节）

### 步骤 0：解析 galaxy（每次任务开头跑一次，命中缓存 <1 秒）

```powershell
python "C:\Users\Administrator\.config\opencode\skills\ui-mockup-studio\scripts\resolve_galaxy.py"
```

行为：`--path` 显式指定 → `config.json` 缓存 → 常见路径候选 → D:/E: 两层受限扫描
→ 全都没有则 `git clone --depth 1` 到 `D:\galaxy`（直连失败自动换 gh-proxy / ghfast 镜像）。
成功后把绝对路径写回 `config.json`，下次直接命中。

- 输出 `ok:true` 才继续；`ok:false` 时把错误原文给用户，让他手动 clone 后跑
  `--path D:\galaxy`。
- 想强制重新查找：`--refresh`；只想查不克隆：`--no-clone`。

### 步骤 1：摸底要设计什么（最容易被跳过、也最致命的一步）

**已有项目**：先读代码/文档，列出**全部**界面单元，不要只画主界面。

- WinForms：`SubForm/*.cs`、`MainForm.cs` 里的弹窗调用、`ShowDialog()`、
  `new mFormXxx(...).Show()`；grep 找 `data-open` 的等价物。
- WPF：`*.xaml` 窗体 + `Window`/`UserControl` + `ShowDialog`；`*.cs` 里 new 的窗口。
- Web：路由表 / 菜单配置 / modal 组件。
- 每个界面记下四件事：**叫什么、从哪进、有什么状态（空/加载/错误/无权限/禁用）、
  有哪些操作会跳走或开弹窗**。

产出（草稿，不用给用户看）：页面清单 + 弹窗清单 + 跳转关系 + 状态清单。

**新项目/新功能**：让用户确认功能清单；拿不到就用"主界面 + 3~6 个子页 + 3~5 个弹窗"
的最小闭环起步，并在交付说明里标注假设。

### 步骤 2：风格基因选型（决定 5 套方案"像不像 5 个不同的作品"）

**先抽基因，再按基因做 galaxy 定向检索**——两个动作都必须做：

**2a. 从基因池抽 5 个互不相同的风格原型**。基因池 14 个原型及各自的基因标签见
`references/design-playbook.md` 第五节（工业仪表 / 杂志留白 / 瑞士网格 / 终端极客 /
新拟态软糖 / 蓝图工程 / 暖色亲和 / 渐变流体 / 粗野 brutalism / 暗金奢华 / 霓虹暗夜 /
玻璃拟态 / 孟菲斯撞色 / 极简数字风）。按项目气质挑，但**禁止每次都拿默认 A-E 五件套**
——上轮项目用过的组合这轮就换。拿不准时用 `galaxy_search.py --random` 抽样找感觉。

**2b. 为每个抽中的原型各做一次 galaxy 定向检索**（每个原型 1~2 次即可），
检索词跟着原型换风格（brutalism / neumorphism / glassmorphism / terminal / swiss /
memphis…，见 `galaxy-map.md` 1.2 节），不要全套稿都搜 "glass card"：

```powershell
$G = "C:\Users\Administrator\.config\opencode\skills\ui-mockup-studio\scripts\galaxy_search.py"
python $G --list-categories
python $G --category Cards --q glass blur --limit 6          # 玻璃拟态原型
python $G --category Buttons --q gradient rounded --limit 6  # 渐变流体原型
python $G --category Toggle-switches --q toggle --limit 4
python $G --show "Cards/0xnihilism_cold-tiger-22.html"       # 直接看源码
```

**每个原型的检索产出一张"基因卡"**（不是代码），至少定下 7 项：

| 基因 | 例子 |
| --- | --- |
| 色相家族（主色+辅色） | 翠绿 `#059669` + 深青 `#0d9488`（终端极客） |
| 圆角形态 | 3px 硬边 / 99px 胶囊 / 12px 软圆角 |
| 密度留白 | 极紧 `gap 9` / 舒适 `gap 22` |
| 质感手法 | 描边+高光 / 无描边+大投影 / 发光边 / 全平面硬边 |
| 字体气质 | 雅黑 / 等线 / 等宽混排 |
| 壳层构图 | `sidebar / tabs / dock / cmdbar / iconrail`（模板内置 5 种） |
| 参考组件（写进 data-galaxy） | `Cards,Forms,Toggle-switches` |

不要求把 galaxy 的 CSS 原样搬进设计稿——**搬的是比例、圆角、留白、渐变方向、交互反馈**。
CSS → 控件的两套映射代码见 `references/galaxy-map.md`。

### 步骤 2.5：信息架构减法（**先减法再出稿**，这是减法不返工的唯一时机）

按 `references/simplify-playbook.md` 对步骤 1 的清单过一遍：

1. **砍**：与侧栏/顶栏重复的入口、随版本失准的说明、只用一次的低频页。
2. **并**：同一动作链的按钮（保存并测试）、同源参数（IP : 端口、心跳地址 · 周期）、
   同域页面（相机配置 + 通讯设置 → 设备通讯）。
3. **藏**：低频参数进"高级参数…"，危险操作进行内"⋯"，低频页进系统设置。
4. **删开关**：互斥两态改单选/分段；有合理默认值的不让用户选。
5. **算预算**：对照预算表数按钮/开关/字段/说明字数，超了就回到 1-4 再砍。

产出：**定稿的页面清单 + 每页字段清单**。这时的页面数通常比步骤 1 少 1~2 个、
每页按钮少 1/3——这才是应该出 5 版的量。减法的判断依据不是"好看"，而是
**"这个控件删掉后用户还能不能完成任务"**。

### 步骤 3：定 4-5 套方案（9 基因拉开，不是换个颜色）

把步骤 2 的 5 张基因卡落成 5 套方案，每套一句话定位 + 适用客户。模板内置 A-E 五组
出厂 Token（A 深夜中控·侧栏后台 / B 杂志留白·顶栏Tab / C 日落活力·底部Dock /
D 终端密度·命令条 / E 暗夜霓虹·图标窄栏）——**它们只是兜底示例，禁止原样交付**：
生成骨架后先把每组 Token 按本次基因卡重校准（主色 / 圆角 / 字体 / 壳形态至少各
重新取值一次），再写页面。

**9 基因红线（check 脚本 C23~C26 自动核验，不是靠人工自觉）**：

- 每套方案的 9 个基因：**色相家族 / 明暗默认 / 圆角形态 / 密度留白 / 质感手法 /
  字体气质 / 强调手法 / 壳层构图 / 动效性格**（`--dur-*`/`--ease-*`）。
- **任意两套方案，10 个基因 Token（primary/primary2/accent/radius/btnradius/
  gap/pad/fs/font/shell）至少 5 项不同**（C24）。
- 主色两两色相距离 ≥ 30°、跨 ≥ 3 个色相家族、至少 1 套暖色或中性色（C23）；
  `--font` 至少 2 种（C25）；`--shell` 至少 3 种形态或存在 data-layout 分叉（C26）。
- 只换主色的两套方案不算两套，直接删掉。

方案与明暗**正交**：每套方案有默认明暗，但用户可任意切换。页面 DOM 不复制
（门面页 data-layout 分叉除外，见铁律 2）。

### 步骤 3.5：定目标技术栈（决定规范视图哪套映射高亮）

| 信号 | 目标栈 |
| --- | --- |
| 项目是 `.csproj` + `*.Designer.cs` + `System.Windows.Forms` | `winforms` |
| 项目是 `*.xaml` + `System.Windows` + `Application.Resource` | `wpf` |
| 用户在 HJVision / CureLine 等已知 WinForms 仓 | `winforms` |
| 拿不准 | 问一句，或默认 `winforms`（本项目群以 WinForms 为主） |

生成时传 `--stack wpf`，或生成后在顶栏点栈名切换；URL 也可 `?stack=wpf`。
**两套映射卡始终都在页面上**（可对照），`data-stack` 只决定哪张标"目标栈"并高亮。

### 步骤 4：生成骨架到项目 Docs

```powershell
cd <项目根>
python "C:\Users\Administrator\.config\opencode\skills\ui-mockup-studio\scripts\new_mockup.py" `
  --project "视觉检测系统" --out "Docs\ui_design_mockups.html" --stack winforms
```

- 目录规则：已有 `Docs` → 用；只有 `docs` → 用；都没有 → 新建 `Docs`。
- 默认文件名 `ui_design_mockups.html`；一个项目多轮设计时带主题后缀
  （如 `ui_design_mockups_报表改造.html`）。
- **默认拒绝覆盖**（防冲掉人工改稿），确需重写加 `--force`。

生成后立刻在浏览器打开一次，确认骨架能跑（舞台/总览/跳转图/规范四视图可切）。

### 步骤 5：写页面（核心工作量，逐页写）

每页一个 `<section class="page" data-page="id" ...>`。必需元数据：

```html
<section class="page" data-page="report" data-title="数据报表" data-group="数据与报表"
         data-w="1440" data-h="900" data-states="default,empty,loading"
         data-galaxy="Cards,Forms,Notifications"
         data-desc="一句话说明这页干什么、给谁用。"
         data-points="要点1|要点2|要点3">
```

写法要点：

- **分辨率统一 1440×900**（工业软件基准）。页面多留余量，不要在 1366 上溢出。
- **页面结构固定四段**：`.app-bar`（标题+状态+全局操作）→ `.app-nav`（侧栏，可选）
  → `.app-main`（内容）→ `.app-foot`（运行状态，可选）。
  DOM 结构全稿一套；切方案时壳层构图由各方案的 variant CSS 重排（模板内置 5 种
  `--shell` 形态），**写页面时不要写死 nav 的方向/宽度/对齐**，让 Token 和 variant
  规则去控制。子页面必须有"← 返回"，并且要 `data-go="main"`。
- **多状态**：`data-states="default,empty,loading"`，页面内用
  `<div class="state-block" data-for="empty" data-display="flex">` 承载。
  `data-display` 声明正常显示时的 display 值（`contents` / `flex` / `block`），
  不写会变成 `block`，可能破布局。
- **每个业务按钮都要有去处**：`data-go` 或 `data-open`。确实没实现的次要按钮，
  加 `.disabled` 或保留无跳转（说明里标注"占位"），不要假装能点。
- **状态用 `.st.ok/.warn/.ng/.info` 胶囊**，不要用整行红底。
- **表格用 `.tbl`，数字列 `class="num"` 右对齐等宽字体**——这是"专业感"的一半。
- **列表/表格区必须能容纳超出内容**：设计稿里给 6~10 行；真实项目在说明里写
  "超过 N 行滚动/分页"。
- **写每页前先过一遍预算表**（铁律 9）。按钮多一个，先想能不能并进上一个。

### 步骤 6：写弹窗（含多状态）

```html
<div class="dlg-modal" data-dialog="dlg-photo-root" data-title="报表照片根目录"
     data-w="560" data-h="210" data-parent="report" style="display:none">
  <div class="dlg" style="--dw:560px"> ... </div>
</div>
```

- `data-parent` 必填（指向背景页），否则跳转图里弹窗无处挂、总览缩略图也缺上下文。
- 内部任意元素加 `data-close` 即关闭；点遮罩、按 Esc 也关。
- **多状态 = 多个 `data-dialog`**：默认态一个、展开/第二步一个，彼此用
  `data-open` 互切（模板里"报表照片根目录 → 展开清单"就是范例）。
- 弹窗宽度 360~720px；超过 720 改用整页或抽屉。
- 危险操作（删除/覆盖/停机）必须有二次确认弹窗，按钮用 `var(--ng)` 红。
- 表单弹窗底部固定"取消 / 保存"，不要只放一个"确定"。
- 弹窗里**同样受预算约束**：底部按钮 ≤ 2 个，没有"清空"这种半吊子按钮
  （清空 = 用户自己删字）。

### 步骤 7：核验（两道，缺一不可）

**第一道：脚本 33 项**

```powershell
python "C:\Users\Administrator\.config\opencode\skills\ui-mockup-studio\scripts\check_mockup.py" `
  "Docs\ui_design_mockups.html" --min-pages 8 --min-dialogs 5 --min-variants 5
```

`--min-pages/--min-dialogs` 按步骤 1 的清单给真实数量（防止"漏画了三个弹窗"还全绿）。
任何 FAIL 必须修到 0；WARN 人工过目（W5/W6/W7 是减法预算，最后应修到 PASS）。

卡片体系三项（C19 三段结构 / C20 卡片规范章节 / C21 职责变体数）只在
**卡片 ≥ 6 张**的稿件上触发；纯表单页不受约束。变体要求可用
`--min-card-variants 4` 放宽（默认 6）。核验模板自身用 `--allow-placeholders`。

C22 查"内容区有没有自己声明文字色"：工作台外壳 body 的文字色是写死的浅色，
`.page` / `.sp-grid` 若不写 `color:var(--fg)`，浅色方案整片变白底浅字（脚本能抓，但眼睛
在深色下看不出来，务必别靠目检）。

C23~C26 查**方案差异度**（反同质化闸门）：C23 主色色相家族 / C24 基因对差计数 /
C25 字体差异 / C26 壳层构图。任何一项 FAIL 都要回到步骤 3 重校准 Token，不许绕过
——同质化的 5 套方案对用户没有选择价值，宁可 4 套差异拉满，不要 5 套一个模子。

**第二道：截图目检**（脚本查不出"难看"）

Edge headless 截图（必须带 `--user-data-dir`，否则不落盘）：

```powershell
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$u = "file:///" + ((Resolve-Path "Docs\ui_design_mockups.html").Path -replace '\\','/')
& $edge --headless=new --disable-gpu --hide-scrollbars `
  --user-data-dir="$env:TEMP\edge_mockup_ud" --window-size=1600,1000 `
  --screenshot="$env:TEMP\s1.png" "$u`?page=main"
```

URL 参数直达（模板内置）：`?page=` `?view=stage|overview|flow|spec`
`?variant=a..e` `?scheme=dark|light` `?state=` `?dialog=` `?stack=winforms|wpf`。

**必看 7 张**：舞台默认页、总览、跳转图、规范（两个栈各一张）、一个弹窗（含展开态）、
一套非默认方案（浅色）。看什么：元素有没有被裁、文字有没有溢出、缩略图是否完整、
连线是否穿过节点、浅色下有没有写死深色、弹窗有没有被撑变形、**主操作是否唯一**。

### 步骤 7.5：品牌图标生成（App Icon / Logo）

设计稿交付时**顺带问一句要不要出软件图标**；用户单独说"设计图标 / 出 logo / app icon"
也直接走本步。细则见 `references/logo-playbook.md`，骨架流程：

1. **设计 4-6 款 SVG**（128 viewBox，手算几何）：底板渐变圆角方取**选中方案的 Token
   色系**（图标与界面同源，一眼认亲）、白色符号保证小尺寸对比、透底一律 evenodd 挖洞
   （禁止叠"近似底色"圆，渐变底上必露馅）；**方案语义写在每款 SVG 的头注释里**
   （预览页自动引用，不重复维护）；
2. **预览选款**：`svg2res.py preview` 生成预览页（浅/深底 × 48/32/20 阶梯）→
   **必须截图目检后才给用户选**——手算几何的翻车只有眼睛能抓（首刷实锤：直线弦光圈
   画出雪花 ❄ 感、瘦花瓣画出风车感，均在预览截图里返工）；
3. **转项目资源并换全**：`svg2res.py convert` 出 PNG 512~16 阶梯 + 7 帧 ICO（16~256）；
   **换图标 = 换全三面**（① exe 内嵌 ApplicationIcon / ② 运行窗口 Window.Icon——需
   Resource Include 否则运行时加载失败 / ③ 界面品牌位同步换掉通用占位符）——逐项清单
   与验证方法见 `references/logo-playbook.md` 第 4 节，缺面 = 用户还得提醒"任务栏图标
   怎么还是旧的"（2026-11-22 AIris 换标定版清单）。

红线：图标渐变色只来自该套方案 Token 色（禁写死方案外色值）；小尺寸纪律
（128 viewBox 口径：主线条 stroke ≥ 6、中心孔 ≥ 13、元素留白 ≥ 5、20px 仍可辨识）。

### 步骤 8：收尾

- 交付说明里写清：文件路径、方案清单（每套一句话）、页面/弹窗数量、**假设与未覆盖项**、
  目标栈、怎么打开（双击即可，无需服务器）。
- 清理临时截图/临时目录（`%TEMP%` 下的 png、edge user-data-dir）。
- 如果是给具体项目做的设计稿，把"选中的方案 + 落地注意点"记进项目文档/CHANGELOG
  （用户明确要求时才改项目 CHANGELOG）。

---

## 4. 模式 B：简化现有界面（不走设计稿）

完整标准在 `references/simplify-playbook.md`（原 `ui-simplify` skill 完整并入）。
**默认执行，不等用户提醒**。用户说"太复杂/简化/看着乱/能合并就合并/简单好上手/
配置项太多/按钮太多/降低学习成本"，就是全套走一遍。

执行流程（5 步）：

1. **调研**：读窗 XAML/cs + VM + 关联测试断言；列出现有字段/文案/分组清单；
   标出**外部契约**（键名、报文字段、寄存器语义）——这些不能动。
2. **方案**：按三层模型列**去向表**（界面留什么 / ToolTip 收什么 / 删什么 / 合并什么 /
   折叠什么）；对照预算表算超标项。
3. **实施**：改界面（+必要的 VM 文案/属性清理）；遵守 WPF/WinForms 坑位清单。
4. **验证**：构建 0 警告 + 全量测试 → 截图目检五件事 → 有测试锁文案的同步更新。
5. **沉淀**：改动记 CHANGELOG；项目 AGENTS/README 的 UI 语义段同步。

**语义零变化**：简化只动"文字与排布"——字段集合、ini/配置键名、校验规则、
落盘口径、门禁权限一律不动。契约名称进 ToolTip 保留可查，绝不为省事删功能。

改完必须截图目检（构建过 ≠ 好看）：① 输入框左缘一条线 ② 行间不贴死不叠压
③ 标签与框间距统一 ④ 无真空区/失衡列 ⑤ 多分辨率各看一遍（1366×768 与 1920×1080）。

---

## 5. 常用命令速查

```powershell
$S = "C:\Users\Administrator\.config\opencode\skills\ui-mockup-studio\scripts"

# 1) 定位/克隆 galaxy
python "$S\resolve_galaxy.py"
python "$S\resolve_galaxy.py" --refresh          # 忽略缓存重新找
python "$S\resolve_galaxy.py" --path D:\galaxy   # 手动指定

# 2) 检索组件
python "$S\galaxy_search.py" --list-categories
python "$S\galaxy_search.py" --category Cards --q glass --limit 8
python "$S\galaxy_search.py" --q neon glow --any --limit 8
python "$S\galaxy_search.py" --category Buttons --random 10
python "$S\galaxy_search.py" --show "Buttons/xxx.html"

# 3) 生成设计稿（--stack winforms|wpf）
python "$S\new_mockup.py" --root . --project "项目名" --out "Docs\ui_design_mockups.html" --stack winforms

# 4) 核验
python "$S\check_mockup.py" "Docs\ui_design_mockups.html" --min-pages 8 --min-dialogs 5

# 5) 图标方案预览 + 转项目资源（细则见 references/logo-playbook.md）
python "$S\svg2res.py" preview "Docs\branding" --out preview.html --title "XX 图标方案"
python "$S\svg2res.py" convert "Docs\branding\logo-x.svg" "Docs\branding\icons\logo-x"
python "$S\svg2res.py" convert-dir "Docs\branding" "Docs\branding\icons"
```

---

## 6. 工作台四个视图（用户怎么看你的稿）

| 视图 | 作用 | 什么时候引导用户看 |
| --- | --- | --- |
| 舞台 `stage` | 单页 1:1 演示，可缩放，可点按钮跳转/开弹窗，带入场动效 | 主推荐：逐页讲设计 |
| 总览 `overview` | 全部页面 + 弹窗缩略图同屏（按真实比例） | 证明"面面俱到"，快速比对 |
| 跳转图 `flow` | 按分组分列 + 自动连线；弹窗挂在父页同列下方 | 讲信息架构与操作路径 |
| 规范 `spec` | 当前方案 Token 表 + 按钮/状态/输入/表格/动效样本 + **WinForms/WPF 两套映射卡** | 讲设计系统，交接给开发 |

顶栏还能切：**方案 A-E**、**深色/浅色**、**动效开/关**、**目标栈 WinForms/WPF**、**导出 PDF**
（打印逐页展开）。右栏自动列出当前页的"说明 / 设计要点 / 交互与跳转 / galaxy 参考分类"。

---

## 7. 新增页面/弹窗的最小操作（模板已把自动化做完了）

1. 复制一个 `<section class="page">` 粘到舞台里，改 `data-page`（唯一）、`data-title`、
   `data-group`（决定左栏分组与流程列）、`data-w/h`、`data-desc`、`data-points`、
   `data-galaxy`。
2. 写页面内容（用模板里的 `.card/.tbl/.formrow/.btn/.st/.kpi` 等现成部件）。
3. 弹窗同理复制 `<div class="dlg-modal">`，改 `data-dialog` / `data-parent`。
4. 保存 → 刷新 → 左栏、总览、跳转图、右栏**自动收录**，不需要改任何 JS。

### 7.5 真实渲染五坑（2026-11-16/17 AgingTestSystem 交付实踩）

1. **纵向 flex 容器里的全局 `.tin{flex:1}` 会拉出大片空白**：左栏/右栏是
   `flex-direction:column` 时，带 `flex:1` 的文本框会把剩余高度全吃掉，页面看着像
   "栏被劈成两半"。修法：**加作用域覆盖，不改全局**——
   `.policy-side .tin{flex:0 0 auto;width:100%}`。判据：截图里出现"一块巨大空卡片"，
   先查该容器内所有 `flex:1` 子项。
2. **`grid-auto-rows` 默认按内容高，铺不满卡片**：点位盘/72 宫格这类"应该填满"的网格，
   只写 `grid-template-columns` 会底部留白。三件套：
   `flex:1;min-height:0;grid-auto-rows:minmax(34px,1fr)` + 子项 `height:auto`。
   反过来，如果网格是嵌在 `.card` 里，选择器要写 `.card > .iogrid` 限定层级，
   别误伤页面别处的同名网格。
3. **跳转图弹窗排在页面列表末尾 → 长距离绕线糊成一团**：弹窗必须**紧跟父页插入**
   （每个页面后接自己的弹窗），不要统一追加到末尾。跨列边用直角总线：
   `M sx sy H gx1 V laneY H gx2 V ty H tx`（`sx`=源右缘、`tx`=目标左缘、
   `gx`=列间空隙 ±22、laneY 分道），并给 `stroke-linejoin:round`；
   斜线直连会让横向几乎重合的边互相压住。
4. **文案必须按项目真实业务模型写，别照抄通用模板**：本项目授权是"永久/30 天码、
   无试用、无启动闸"，通用模板那句"试用中 · 剩余 12 天"会被评审当场揪出。
   同理：负压 0 的语义（阈值 0＝保护失效）、弹窗一句话上限（≤16 字）、
   默认值来源（项目策略 A 档 vs 出厂值）都要对着项目文档核对一遍再落稿。
   这类错不是排版问题，是**业务事实错误**，比错位更严重。
5. **内容区靠继承 body 的文字色 → 浅色方案白字白底**（2026-11-17 实锤）：
   工作台外壳是固定中性深色，`body{color:#dbe4f0}` 写死给外壳用；页面 `.page`、
   规范区 `.sp-grid`、弹窗 `.dlg` 若没自己声明 `color:var(--fg)`，切浅色方案时
   标题/大数字/正文全变成 `#dbe4f0`（近白）——**深色方案下完全看不出来**，
   因为 `#dbe4f0` 与 `--fg:#e8eff9` 只差一点点。判据：浅色截图里文字发虚/发灰就
   用 `getComputedStyle(el).color` 打一遍，落在 `rgb(219,228,240)` 就是继承到外壳色。
   模板三处已修（`.page` / `.sp-grid` / `.dlg`），`check_mockup.py` C22 会拦。

### 7.6 卡片体系（卡片式页面的唯一写法）

模板已在 `spec` 视图内置「卡片规范 Card System」整章（解剖 + 参数 + 状态矩阵 + 8 格语言库），
**不要重写这套结构，按职责挑变体填内容**。

**三段结构（地基，不许退回单层壳）**

```html
<div class="card col">                       <!-- .col = flex 列，卡脚才能贴底 -->
  <div class="card-h"><span class="ci">▤</span><b>标题</b><span class="sp"></span><span class="mono tiny">状态</span></div>
  <div class="card-b">卡身直接写内容，不再多包一层</div>
  <div class="card-f"><span>汇总 / 动作只放这里</span></div>
</div>
```

- 卡头 `.card-h`、卡脚 `.card-f` 在 flex 列里都是 `flex:0 0 auto`，**内容再多也不许被压扁**。
- 卡脚用负 margin 通栏贴底；`.card.col > .card-f{margin-top:auto}` 保证一排卡底边齐。
- 分区卡（列表/表格/网格）用 `.card.pad0` + **`.card-h.band`**（通栏带底卡头）。
  **别把类名起成 `.bar`** —— 项目里 `.bar` 通常是进度条（`height:6px`），
  同名会被它压成一条缝（AgingTestSystem 实锤：卡头 clientH 只剩 16px，标题被裁）。
- 列表行 `.rows .r` 的水平内边距必须等于 `--card-pad`（与 `.card-h.band`、`.card-f` 同一口径），
  行高统一 30px。写成 `padding:8px 2px` 这类小值，行文字会比卡头缩进一截——一眼就是错位。

**8 种职责变体（按职责选，不按喜好选）**

| 变体 | 类名 | 用在哪 | 禁用场景 |
| --- | --- | --- | --- |
| 容器卡 | `.card` / `.card.col` | 页面主分区，同页 2~4 张 | 再往上套一层卡 |
| 指标卡 | `.card.hero`（大数字）/ `.kpi`（小指标块） | 回答"现在最要紧的那个数" | 一屏多张 hero |
| 列表卡 | `.card.pad0` + `.card-h.band` + `.rows` | 最近 N 条 / 设备清单 | 超过 10 行（该上表格） |
| 告警卡 | `.card.rail.ng` | 故障/越限，左缘 3px 红条 | 整卡铺红底 |
| 顶线焦点卡 | `.card.top` | 当前工位 / 正在编辑的那张 | 一屏多于一张 |
| 内嵌分区 | `.card.inset` | 卡内分组 / 只读区 | 再描一圈边 |
| 工位瓦片 | `.tiles` + `.tile`（业务可换 `.wcell`） | 密集小格，一格一个对象 | 放长文本 |
| 折叠组 | `.card.fold` | 设置页分组（组头常驻） | 页面主分区 |
| 玻璃浮层 | `.card.glass` | 压在内容上的抽屉/浮层 | 普通分块（模糊拖慢老工控机） |

**规则不随方案变，气质才随方案变**：只覆盖质感 Token（`--card-hi` 顶缘高光 /
`--card-lift` 投影 / `--card-line` 描边 / `--radius` 圆角），卡片规则一条不动。
浅色方案的 `--card-line` 必须比深色深（白卡漂在白底上看不出边）。

**状态六态（规范视图必须画全）**：默认（描边+顶缘高光）/ 悬停（上移 1px + 边框提亮）/
选中（主色边 + 3px 光晕）/ 告警（左缘 3px 红条）/ 焦点（顶线 3px 渐变）/ 禁用（整体 55%）。
选中与状态要能同时读出来：选中是"我在看它"，不是状态。

---

## 8. 延伸阅读（按需读，不要一次全读）

- `references/design-playbook.md` —— **写页面前必读**：卡片设计原则（三段结构、8 种职责变体、
  六态）、干净整洁的 8 条硬指标、信息层级、留白节奏、动效参数、常见破相清单、5 套方案的设计原理。
- `references/simplify-playbook.md` —— **简化现有界面必读**：三层模型、信息预算表、
  合并五判定、十条手法、易上手 3 秒/三步/闭眼测试、炫点配额、WPF + WinForms 坑位、
  目检纪律、执行流程。
- `references/mockup-spec.md` —— data-* 速查表、标准页面/表格页/表单页/弹窗/多状态弹窗
  的代码片段、交付完整度清单、预算自检。
- `references/galaxy-map.md` —— galaxy 11 个分类的用途、检索词表、组件文件结构、
  **CSS → WinForms（GDI+/SunnyUI）与 CSS → WPF（XAML）两套完整映射与代码片段**。

---

## 9. 版本

- V1.4.0（2026-11-22）：**新增品牌图标生成环节**（步骤 7.5 + `references/logo-playbook.md`）
  与一键转资源脚本 `scripts/svg2res.py`：`preview` 扫 SVG 目录自动生成选款预览页
  （语义取自 SVG 头注释，浅/深底 × 48/32/20 阶梯）；`convert` Edge headless 渲 512 高清
  （必须带 --user-data-dir，透明底）+ PIL 缩 PNG 阶梯 512~16 + 打包 7 帧 ICO。
  首刷 AIris 六款实战回刷：直线弦光圈雪花感/瘦花瓣风车感返工教训、evenodd 挖洞透底板、
  小尺寸纪律（stroke≥6/中心孔≥13/20px 可辨识）沉淀进 playbook。
- V1.3.0（2026-11-18）：**方案差异度大改**（反同质化）。差异轴从"密度/圆角/主色/留白"
  四维扩为 **9 基因**（色相/明暗/圆角/密度/质感/字体/强调/壳构图/动效性格）：
  模板新增 `--font`（B 等线、D 等宽混排）与 `--dur-*`/`--ease-*` 动效性格 Token，
  内置 5 方案重校准为跨色相家族（蓝/中性墨黑/暖橙粉/翠绿/霓虹品红，b=d 同主色事故修复）
  + **5 种壳层构图**（sidebar/tabs/dock/cmdbar/iconrail，variant CSS 重排同一 DOM）；
  新增门面页 `data-layout` 有限构图分叉机制（≤3 页、每页 ≤3 套布局、纯 CSS 切换）；
  工作流新增步骤 2a 基因池抽原型（14 原型池）+ 每原型独立 galaxy 检索产出基因卡，
  出厂 Token 禁止原样交付（每次重校准）；核验 29 → **33 项**（C23 主色色相家族 /
  C24 基因对差 ≥5/10 / C25 字体差异 WARN / C26 壳构图差异），深色 `--grid` 写死青色修复。
- V1.2.0（2026-11-17）：卡片体系重构（AgingTestSystem 设计稿实做回刷）。
  模板 `.card` 升级为**三段结构**（`.card-h` / 卡身 / `.card-f`）＋ 卡片 Token
  （`--card-r/-pad/-gap/-line/-hi/-lift`，五方案气质差异只覆盖这几个）；
  新增按职责的 8 种变体（容器/指标/列表/告警/顶线/内嵌/瓦片/折叠/玻璃）与
  `.card-h.band` 通栏卡头；规范视图新增「卡片规范」整章（解剖 + 参数 + 六态矩阵 +
  语言库）；列表行 `.rows .r` 统一 30px 行高、水平内边距 = `--card-pad`
  （与卡头/卡脚同一左缘）；核验扩到 29 项（C19 三段结构 / C20 卡片章节 / C21 职责变体数 / C22 内容区文字色）。
- V1.1.0（2026-11-16）：并入原 `ui-simplify` skill（删除其目录），新增模式 A/B/C 判定、
  信息预算与炫点配额铁律、步骤 2.5 信息架构减法、步骤 3.5 目标技术栈、
  galaxy → WinForms / galaxy → WPF 双栈映射（模板 spec 视图 + `galaxy-map.md`），
  核验扩到 25 项（C17/C18 两栈、W5-W8 减法预算）。
- V1.0.0（2026-11-16）首版：galaxy 解析/检索、工作台模板（5 方案 × 明暗、4 视图、
  URL 直达）、生成与 19 项核验脚本、三份参考手册。
  模板内置 3 示例页（主界面/数据报表/通讯设置）+ 3 弹窗（照片根目录默认态/展开态/确认删除），
  可直接当"填写范例"复制。
