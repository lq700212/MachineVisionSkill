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

1. **一切视觉语言来自 galaxy**。按钮圆角/渐变/阴影/开关/加载动画，先去
   `E:\Project\galaxy`（或缓存路径）里找同款，再映射成目标技术栈。
   **禁止凭空自创风格**，禁止"我记得某个 Bootstrap 样子"。
2. **页面 DOM 只写一次，方案 = Token 切换**。5 套方案绝不允许复制 5 份页面 DOM
   （会失控、跳转图重复、改一处要改五处）。换方案只换 `html[data-variant]`。
3. **禁止写死色值/圆角/间距**。页面里只能出现 `var(--primary)` `var(--radius)` 这类
   Token；写死一个 `#3e8bff`，那套方案切过去就破相。

**交互完整**

4. **每个用户会点的业务按钮都必须声明跳转**：切页 `data-go="页面id"`、
   开弹窗 `data-open="弹窗id"`。漏一个，跳转关系图和右栏"交互与跳转"就少一条，
   用户点下去没反应 = 交付不合格。
5. **弹窗多状态用多个 `data-dialog` 表达**（默认态/展开态/确认态各一个），
   不要把复杂状态机塞进弹窗内部 JS。
6. **单文件离线可用**：禁止外链 CDN / 外链字体 / 外链图片（现场电脑常常没网）。

**减法（用户明确要求，默认执行）**

7. **界面只放"要用户做的决定"**：字段键名/寄存器号/格式约束 → ToolTip；
   全局口径 → 顶部一行提示条；**永远不建"说明书列/说明卡"**。
8. **遵守信息预算**（详见 `simplify-playbook` 第二节）：一屏主操作 1 个、
   按钮 ≤ 10（硬上限 12）、顶栏可点 ≤ 4、侧栏 ≤ 7、开关 ≤ 3（硬上限 5）、
   一个页签首屏字段 ≤ 8、一行筛选 ≤ 4 个控件、表格行操作 ≤ 1 个"⋯"、
   页面说明 ≤ 60 字、单条要点 ≤ 40 字。**超预算必须在右栏写一句为什么**。
9. **一屏只允许 1 个循环炫点**（模板示范：相机磁贴扫描光带 4.2s / 主色 13% / 四块错峰）。
   表单、表格、正文**禁止炫**。关掉动效后信息必须仍然完整可读。

**双栈落地**

10. **规范视图必须同时内置 WinForms 与 WPF 两套映射卡**，`data-stack` 只决定哪张高亮
    为目标栈。映射值必须从 `getComputedStyle` 实时取 Token，**禁止写死**——
    否则切方案时两套代码不跟着变，评审时无法指着说"这套在我们项目里就是这几个常量"。
11. **落地映射必须遵守两栈各自的坑位清单**（WinForms 见 `simplify-playbook` 第八节，
    WPF 见第七节，CSS → 控件映射见 `galaxy-map.md`）。

**交付验收**

12. **交付前 `check_mockup.py` 必须 0 FAIL**（25 项），并至少截图目检：舞台、总览、
    跳转图、规范（两栈）、一个弹窗（含展开态）、一套非默认方案（浅色）。
    只看代码不截图 = 没验收。
13. **文件必须严格 UTF-8**。禁止用 PowerShell `Out-File`/`Add-Content` 写含中文的 HTML；
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
│   └── check_mockup.py           交付前 25 项核验（结构/跳转/编码/离线/两栈/减法预算）
├── templates/
│   └── mockup_base.html          工作台模板（5 方案 Token + 4 视图 + 3 示例页 + 3 弹窗 + 双栈映射）
└── references/
    ├── design-playbook.md        设计方法与"干净整洁"的硬指标（写页面前必读）
    ├── simplify-playbook.md      简化现有界面的完整标准（原 ui-simplify 并入）
    ├── mockup-spec.md            data-* 速查 + 页面/弹窗代码片段 + 完整度清单 + 预算自检
    └── galaxy-map.md             galaxy 分类地图 + 检索词 + WinForms/WPF 两套映射代码
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

### 步骤 2：galaxy 选型（决定这套设计"像不像专业作品"）

先看分类概览，再按控件类型检索 2~4 个参考组件：

```powershell
$G = "C:\Users\Administrator\.config\opencode\skills\ui-mockup-studio\scripts\galaxy_search.py"
python $G --list-categories
python $G --category Cards --q glass card --limit 6
python $G --category Buttons --q gradient rounded --limit 6
python $G --category Toggle-switches --q toggle --limit 4
python $G --show "Cards/0xnihilism_cold-tiger-22.html"   # 直接看源码
```

**选型的产出不是代码，而是"视觉语言决策"**，至少定下：

| 决策项 | 例子 |
| --- | --- |
| 主色 + 辅色 | 工业蓝 `#3e8bff` + 青 `#22d3ee` |
| 圆角尺度 | 卡片 10px / 按钮 8px（紧凑工业） |
| 密度 | 紧凑（表格行高 28）/ 舒适（行高 36） |
| 阴影策略 | 仅浮层有阴影，平面不用（工业风） |
| 强调手法 | 渐变胶囊 / 发光边 / 细边框 + 大留白 |
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

### 步骤 3：定 4-5 套方案（必须有区分度，不是换个颜色）

每套方案一句话定位 + 适用客户，例如：

- **A 深夜中控**：工业蓝 + 紧凑小圆角 → 车间大屏/操作台（默认推荐）
- **B 极简留白**：黑白灰 + 大留白 + 细边框 → 给外企/客户演示
- **C 渐变活力**：紫青渐变 + 胶囊按钮 → 汇报 PPT、年轻化产品
- **D 高密度灰蓝**：小字号 + 6px 圆角 + 密集表格 → 数据录入/工程师
- **E 暗夜霓虹**：近黑 + 霓虹青发光 → 展厅、Demo 演示

红线：**每套方案必须在"密度 / 圆角 / 主色 / 留白"四个维度里至少变三个**。
只换主色的两套方案不算两套，直接删掉。

方案与明暗**正交**：每套方案有默认明暗（A/E 深、B/C/D 浅），但用户可任意切换，
共 10 种组合。页面 DOM 不复制。

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
  子页面必须有"← 返回"，并且要 `data-go="main"`。
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
- **写每页前先过一遍预算表**（铁律 8）。按钮多一个，先想能不能并进上一个。

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

**第一道：脚本 25 项**

```powershell
python "C:\Users\Administrator\.config\opencode\skills\ui-mockup-studio\scripts\check_mockup.py" `
  "Docs\ui_design_mockups.html" --min-pages 8 --min-dialogs 5 --min-variants 5
```

`--min-pages/--min-dialogs` 按步骤 1 的清单给真实数量（防止"漏画了三个弹窗"还全绿）。
任何 FAIL 必须修到 0；WARN 人工过目（W5/W6/W7 是减法预算，最后应修到 PASS）。

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

---

## 8. 延伸阅读（按需读，不要一次全读）

- `references/design-playbook.md` —— **写页面前必读**：干净整洁的 8 条硬指标、
  信息层级、留白节奏、动效参数、常见破相清单、5 套方案的设计原理。
- `references/simplify-playbook.md` —— **简化现有界面必读**：三层模型、信息预算表、
  合并五判定、十条手法、易上手 3 秒/三步/闭眼测试、炫点配额、WPF + WinForms 坑位、
  目检纪律、执行流程。
- `references/mockup-spec.md` —— data-* 速查表、标准页面/表格页/表单页/弹窗/多状态弹窗
  的代码片段、交付完整度清单、预算自检。
- `references/galaxy-map.md` —— galaxy 11 个分类的用途、检索词表、组件文件结构、
  **CSS → WinForms（GDI+/SunnyUI）与 CSS → WPF（XAML）两套完整映射与代码片段**。

---

## 9. 版本

- V1.1.0（2026-11-16）：并入原 `ui-simplify` skill（删除其目录），新增模式 A/B/C 判定、
  信息预算与炫点配额铁律、步骤 2.5 信息架构减法、步骤 3.5 目标技术栈、
  galaxy → WinForms / galaxy → WPF 双栈映射（模板 spec 视图 + `galaxy-map.md`），
  核验扩到 25 项（C17/C18 两栈、W5-W8 减法预算）。
- V1.0.0（2026-11-16）首版：galaxy 解析/检索、工作台模板（5 方案 × 明暗、4 视图、
  URL 直达）、生成与 19 项核验脚本、三份参考手册。
  模板内置 3 示例页（主界面/数据报表/通讯设置）+ 3 弹窗（照片根目录默认态/展开态/确认删除），
  可直接当"填写范例"复制。
