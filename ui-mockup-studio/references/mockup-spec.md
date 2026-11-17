# 设计稿规范速查（mockup-spec）

> 写页面前把本文当**字典**用，不要背。所有片段都能直接粘进模板，粘完刷新就生效。
> 全套自动化由容器里的 data-* 驱动：**你只写 DOM，树/总览/跳转图/右栏说明全靠 JS 自动生成。**

---

## 一、文件骨架（改这里才能换全局行为）

```html
<html lang="zh-CN"
      data-variant="a"      <!-- 方案 a..e -->
      data-scheme="dark"    <!-- dark | light -->
      data-motion="on"      <!-- on | off（动效总闸） -->
      data-state="default"  <!-- 默认/空/加载/错误 -->
      data-stack="winforms" <!-- winforms | wpf（规范视图哪套映射高亮） -->
      data-view="stage">    <!-- stage | overview | flow | spec -->
```

- 这 6 个属性是**唯一全局开关**，由顶栏按钮 / URL 参数写回；页面 DOM 不感知方案。
- 页面/弹窗**不得**出现 `#hex`、`px` 圆角、`rgba()` 阴影——一律 `var(--token)`。
  唯一的例外：页面宽高（`data-w/h`、`style="width:220px"`）是**布局尺寸**，允许写死。
- 方案差异走 **9 基因 Token**：色相（`--primary/--primary2/--accent`）、圆角
  （`--radius/--btnradius`）、密度（`--gap/--pad/--fs`）、字体（`--font`）、
  壳层构图（`--shell: sidebar|tabs|dock|cmdbar|iconrail`）、动效性格
  （`--dur-page/--dur-dlg/--ease-page/--ease-dlg`）。全部定义在
  `html[data-variant=x]` 层，切方案自动生效，页面零改动。

---

## 二、data-* 全表（共 17 个，全是"声明"，不是脚本）

### 2.1 页面（`<section class="page">`）

| 属性 | 必填 | 作用 | 示例 |
| --- | --- | --- | --- |
| `data-page` | ✅ | 唯一 id，`data-go` 的目标；不能与弹窗重名 | `main` / `report` |
| `data-title` | ✅ | 左栏、总览、跳转图、舞台标题 | `数据报表` |
| `data-group` | ✅ | 左栏分组 + 跳转图分列 | `数据与报表` |
| `data-w` `data-h` | ✅ | 设计尺寸，舞台按此 1:1 渲染 | `1440` `900` |
| `data-states` | 建议 | 声明有哪些状态，逗号分隔；第一个必须是 `default` | `default,empty,loading` |
| `data-galaxy` | ✅ | 参考的 galaxy 分类（右栏可追溯） | `Cards,Forms` |
| `data-desc` | ✅ | 一句话说明（≤60 字，W1/W7 会查） | `按 SN 查记录，可导出。` |
| `data-points` | 建议 | 设计要点，`\|` 分隔（单条 ≤40 字，W7 会查） | `筛选一行放完\|KPI 不堆图表` |

### 2.2 弹窗（`<div class="dlg-modal">`）

| 属性 | 必填 | 作用 |
| --- | --- | --- |
| `data-dialog` | ✅ | 唯一 id，`data-open` 的目标 |
| `data-title` | ✅ | 弹窗标题（右栏、总览、跳转图节点名） |
| `data-w` `data-h` | ✅ | 弹窗盒子尺寸（`data-w` 与内层 `--dw` 保持一致） |
| `data-parent` | ✅ | 背景页 id；决定跳转图挂载列与总览上下文（C16 会查） |

### 2.3 交互

| 属性 | 挂在哪 | 作用 |
| --- | --- | --- |
| `data-go="pageId"` | 任意可点元素 | 切到目标页面（C10 查目标存在） |

### 2.4 门面页布局分叉（`data-layout`，有限放开）

同一 DOM 内给门面页做有限构图分叉（铁律 2 的唯一例外）：

```html
<main class="app-main">
  <!-- 默认布局：所有方案共用 -->
  <div class="tile-grid">…磁贴阵列…</div>
  <!-- 方案 C 专属构图：分栏杂志流，只有切到 C 才显示 -->
  <div data-layout="c" style="display:flex;gap:var(--gap)">…容器重排…</div>
</main>
```

- `[data-layout]` 默认全隐藏；每套方案需一条显示规则
  （模板已内置：`html[data-variant="c"] [data-layout="c"]{display:flex !important}`）。
- **限制**：只用于门面页（主界面等 ≤3 页）；每页 ≤3 套布局；块内只做容器重排、
  不重写控件；常规子页/弹窗禁止分叉（DOM 只写一次）。
- check C26 认可"≥3 种 `--shell`"或"存在 data-layout 分叉"两种构图差异信号。
| `data-open="dlgId"` | 任意可点元素 | 打开目标弹窗（C11 查目标存在）；换弹窗也用它 |
| `data-close` | 弹窗内任意元素 | 关闭当前弹窗（遮罩/Esc 也关） |
| `data-for="state"` | `.state-block` | 该块属于哪个状态 |
| `data-display` | `.state-block` | 正常显示时的 display 值：`contents` / `flex` / `block` |

> `data-jump-type` / `data-jump-to` 是**右栏自动生成**的只读属性，不要手写。

---

## 三、类名速查（模板已提供，别自己发明）

### 3.1 布局与外壳

| 类 | 用途 |
| --- | --- |
| `.app` `.app-bar` `.app-logo` `.app-title` `.app-status` `.app-right` | 应用外壳（顶栏） |
| `.app-body` `.app-nav` `.nav-i`（`.active`）`.n` | 侧栏导航；项数 ≤ 7 |
| `.app-main` `.app-foot` | 主内容区 / 底栏状态条 |
| `.card` `.card-h` | 卡片容器与卡片头 |
| `.row` `.sp` | 横向排布 / 弹性占位（把后面的推到右边） |
| `.hr` | 分隔线 |
| `.tile-grid` `.cam-tile` `.cam-h` `.cam-img` `.cam-foot` | 相机磁贴（4 宫格，唯一炫点示范） |
| `.logbox` `.log-h` `.log-body` | 日志区（固定高度，≤ 5 行） |
| `.kpis` `.kpi` `.k-l` `.k-v` | KPI 四宫格；`.kpi.ok/.warn/.ng` 变色 |

### 3.2 文本与状态

| 类 | 用途 |
| --- | --- |
| `.muted` `.tiny` `.mono` `.footnote` | 次要文字 / 小字 / 等宽数字 / 弹窗脚注 |
| `.st` + `.ok` / `.warn` / `.ng` / `.info` | 状态胶囊，内部 `<i class="dot"></i>` 出圆点 |
| `.stline` + `<i class="dot"></i>` | 无底色状态行（`progress/ok` 语义）；`.plain` 转灰 |
| `.plno` | 料号展示胶囊 |
| `.crumb` | 面包屑（子页面用） |

颜色语义固定：`ok` 绿 / `warn` 橙 / `ng` 红 / `info` 蓝。**禁止**用 `ok` 表示"警告"。

### 3.3 按钮（一个页面最多 1 个 `.primary`）

| 类 | 用途 |
| --- | --- |
| `.btn` | 基础按钮（默认 = 次操作描边） |
| `.btn.primary` | 主操作，每屏**只能一个** |
| `.btn.ghost` | 幽灵按钮（返回/取消/低频） |
| `.btn.sm` | 小号（顶栏、行内） |
| `.icon-btn` | 纯图标按钮；**必须带 `title`**（W8 会查）；行内"更多"用 `.rowmore` |
| `.disabled` | 置灰不可用（保留占位，不要隐藏——隐藏会让用户以为功能丢了） |

文案 ≤ 4 字："导出 Excel" 可以，"将当前结果导出为 Excel" 不行。

### 3.4 表单

| 类 | 用途 |
| --- | --- |
| `.formrow` | 一行"标签 + 控件 + 可选按钮"，标签列宽固定 |
| `.tin` | 输入框外观（设计稿里是 div）；`.tin.sel` 出下拉箭头 |
| `.tin .ph` | 占位文字（灰） |
| `.switch`（`.on`） | 开关；一屏 ≤ 3 个（硬上限 5，W6 会查） |
| `.chk` | 勾选框 |
| `.skel` | 骨架屏条（加载态用） |
| `.spinner` | 加载环 |

### 3.5 表格

| 类 | 用途 |
| --- | --- |
| `.tbl` | 表格，行高紧凑 |
| `.tbl th` | 表头（≤ 6 字，超了 ToolTip 给全称） |
| `.tbl .num` | 数字列：右对齐 + 等宽字体（专业感的一半） |
| `.tbl .mono` | 时间/SN 等等宽列 |
| `.tbl .rowmore` | 行操作"⋯"，默认低对比，悬停提亮 |

**表格行操作只留 1 个"⋯"**，编辑/删除/复制都进它的菜单（或进详情弹窗）。

### 3.6 弹窗

| 类 | 用途 |
| --- | --- |
| `.dlg-modal` | 弹窗外层（遮罩 + 定位），`display:none` 起步 |
| `.dlg` | 弹窗盒子；`style="--dw:560px"` 控宽 |
| `.dlg-title` `.dlg-body` `.dlg-foot` | 标题 / 内容 / 底栏 |
| `.modal-layer` | 模板内置遮罩层，别自己加 |

> ⚠️ `.dlg` 类名专用于弹窗盒子。表达"这个元素是弹窗"一律用 `.is-dlg`，
> 不要给其他元素加 `.dlg`，否则会吃到弹窗样式（血泪 bug）。

---

## 四、标准页面片段

### 4.1 主界面（常驻窗口：顶栏 + 侧栏 + 内容 + 底栏）

```html
<section class="page" data-page="main" data-title="主界面" data-group="主界面"
         data-w="1440" data-h="900" data-states="default"
         data-galaxy="Cards,Forms,Tooltips"
         data-desc="唯一常驻窗口：状态、导航、检测磁贴、运行日志。"
         data-points="顶栏只放连接状态与设置|磁贴 2×2 自适应|日志只在新消息时贴底">
  <div class="app">
    <header class="app-bar">
      <div class="app-logo">◆</div>
      <div class="app-title">视觉检测系统<span>Vision Suite</span></div>
      <div class="app-status">
        <span class="st ok"><i class="dot"></i>PLC 在线</span>
        <span class="st ok"><i class="dot"></i>相机 4/4</span>
      </div>
      <div class="app-right">
        <span class="plno">NP-6125-H1</span>
        <button class="icon-btn" title="系统设置">⚙</button>
      </div>
    </header>
    <div class="app-body">
      <nav class="app-nav">
        <a class="nav-i active"><span>●</span>生产运行<span class="n">4</span></a>
        <a class="nav-i" data-go="report"><span>▦</span>数据报表</a>
        <a class="nav-i" data-go="comm"><span>⇄</span>设备通讯</a>
        <a class="nav-i" style="margin-top:auto"><span>⚙</span>系统设置</a>
      </nav>
      <main class="app-main"> <!-- 内容 --> </main>
    </div>
    <footer class="app-foot">
      <span>运行中 · 已连续 4h 12m</span><span class="sp"></span>
      <span class="mono">v4.4.375</span>
    </footer>
  </div>
</section>
```

**减法要点**：顶栏可点元素 ≤ 4；与侧栏重复的入口删掉；低频配置（相机/脚本/照片目录）
不进顶栏，收进系统设置。

### 4.2 表格页（筛选一行 + KPI + 明细）

```html
<section class="page" data-page="report" data-title="数据报表" data-group="数据与报表"
         data-w="1440" data-h="900" data-states="default,empty,loading"
         data-galaxy="Cards,Forms,Notifications"
         data-desc="按 SN / 料号 / 日期查记录，看 KPI 与明细，可导出 Excel。"
         data-points="筛选一行放完，只有查询是主操作|KPI 只给计数与占比|空态不挪表头">
  <div class="app">
    <header class="app-bar">
      <div class="app-logo">▦</div>
      <div class="app-title">数据报表<span>Vision Report</span></div>
      <div class="app-right">
        <button class="btn ghost sm" data-go="main">← 返回</button>
        <button class="btn ghost sm" data-open="dlg-photo-root">照片目录</button>
        <button class="btn primary sm">导出 Excel</button>
      </div>
    </header>
    <main class="app-main">
      <div class="card" style="padding:12px 14px">
        <div class="row" style="gap:10px;flex-wrap:wrap">
          <div class="tin" style="width:220px"><span class="ph">SN / 产品条码</span></div>
          <div class="tin sel" style="width:150px">全部料号</div>
          <div class="tin" style="width:200px">2026-11-16 ~ 11-16</div>
          <span class="sp"></span>
          <button class="btn primary sm">查询</button>
          <button class="btn ghost sm">重置</button>
        </div>
      </div>
      <div class="kpis">
        <div class="kpi"><div class="k-l">今日总数</div><div class="k-v">1,287</div></div>
        <div class="kpi ok"><div class="k-l">OK</div><div class="k-v">1,284</div></div>
        <div class="kpi ng"><div class="k-l">NG</div><div class="k-v">3</div></div>
        <div class="kpi"><div class="k-l">良率</div><div class="k-v">99.77%</div></div>
      </div>
      <div class="card" style="flex:1;min-height:0;display:flex;flex-direction:column">
        <div class="card-h"><span>检测明细</span><span class="sp"></span><span class="tiny muted">共 1,287 条</span></div>
        <div class="state-block" data-for="default" data-display="contents">
          <table class="tbl">
            <thead><tr><th>时间</th><th>SN</th><th>点位</th><th class="num">测量值</th><th>判定</th><th style="width:34px"></th></tr></thead>
            <tbody>
              <tr>
                <td class="mono">13:42:08</td><td class="mono">2408160001</td><td>外径</td>
                <td class="num">12.503 mm</td><td><span class="st ok">OK</span></td>
                <td><button class="icon-btn rowmore" data-open="dlg-confirm" title="更多操作">⋯</button></td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- 空态与加载态见第五节 -->
      </div>
    </main>
  </div>
</section>
```

**减法要点**：筛选控件 ≤ 4 个（日期范围合并成一个输入）；不堆图表；行操作只有"⋯"。

### 4.3 配置页（左设备树 + 右参数，参数能合并就合并）

```html
<section class="page" data-page="comm" data-title="设备通讯" data-group="设备"
         data-w="1440" data-h="900" data-states="default"
         data-galaxy="Forms,Inputs,Tooltips"
         data-desc="PLC / 读码器 / 串口的连接参数。"
         data-points="切设备不刷新整页|同源参数合并一行|低频项收进高级">
  <div class="app">
    <header class="app-bar">
      <div class="app-logo">⇄</div>
      <div class="app-title">设备通讯<span>Device I/O</span></div>
      <div class="app-right">
        <button class="btn ghost sm" data-go="main">← 返回</button>
        <button class="btn primary sm">保存</button>
      </div>
    </header>
    <div class="app-body">
      <nav class="app-nav">
        <a class="nav-i active"><span>●</span>PLC</a>
        <a class="nav-i"><span>▮</span>读码器</a>
        <a class="nav-i"><span>⌁</span>串口仪表</a>
      </nav>
      <main class="app-main">
        <div class="card" style="max-width:760px">
          <div class="card-h"><span>PLC 连接</span><span class="sp"></span><span class="st ok"><i class="dot"></i>已连接</span></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 22px">
            <div class="formrow"><label>品牌</label><div class="tin sel">西门子 S7-1200</div></div>
            <div class="formrow"><label>IP : 端口</label><div class="tin mono">192.168.1.10 : 102</div></div>
            <div class="formrow" style="grid-column:1/-1"><label>心跳</label><div class="tin mono">DB1.DBW100 · 500ms</div></div>
          </div>
          <div class="hr"></div>
          <div class="row">
            <span class="tiny muted">已启用 · 停跳 30s 判离线</span>
            <span class="switch on"></span>
            <span class="sp"></span>
            <button class="btn ghost sm">高级参数…</button>
            <button class="btn ghost sm">测试连接</button>
          </div>
        </div>
      </main>
    </div>
  </div>
</section>
```

**减法要点**：IP 与端口合并、心跳地址与周期合并、机架/槽位进"高级参数…"；
底部按钮不随滚动消失；开关 ≤ 1 个。

---

## 五、多状态（空/加载/错误）

```html
<!-- 放在同一个 .card 里，三块互斥，data-for 对应 data-states 里声明的名字 -->
<div class="state-block" data-for="default" data-display="contents">
  <!-- 正常的表格/内容 -->
</div>

<div class="state-block" data-for="empty" data-display="flex" style="flex:1">
  <div style="margin:auto;text-align:center">
    <div style="font-size:26px;opacity:.35">▤</div>
    <div style="margin-top:8px;font-size:12px">没有符合条件的记录</div>
    <div class="tiny muted" style="margin-top:4px">换个日期或清空筛选再查</div>
    <button class="btn ghost sm" style="margin-top:12px">清空筛选</button>
  </div>
</div>

<div class="state-block" data-for="loading" data-display="flex" style="flex:1;align-items:center;justify-content:center;gap:10px">
  <span class="spinner"></span><span class="tiny muted">正在查询…</span>
</div>

<div class="state-block" data-for="error" data-display="flex" style="flex:1">
  <div style="margin:auto;text-align:center">
    <div class="st ng" style="display:inline-flex"><i class="dot"></i>连接失败</div>
    <div class="tiny muted" style="margin-top:8px">MES 无响应，请检查网络后重试</div>
    <button class="btn ghost sm" style="margin-top:12px">重试</button>
  </div>
</div>
```

规则：

- `data-display="contents"` 用于**表格/多块内容**（自身不占盒，子元素直接进父布局）；
  `flex` 用于**居中空态**；`block` 用于普通段落。
- 空态文案 ≤ 20 字 + 1 个动作，不要写三段。
- **空态/加载态不得改变表头位置**——所以状态块要和表格在同一个容器里。

---

## 六、弹窗片段

### 6.1 简单表单弹窗

```html
<div class="dlg-modal" data-dialog="dlg-photo-root" data-title="报表照片根目录"
     data-w="560" data-h="210" data-parent="report" style="display:none">
  <div class="dlg" style="--dw:560px">
    <div class="dlg-title">报表照片根目录</div>
    <div class="dlg-body">
      <div class="formrow" style="margin-bottom:10px">
        <label>覆盖根目录</label>
        <div class="tin"><span class="ph">留空 = 跟随存图目录</span></div>
        <button class="btn ghost sm">浏览…</button>
      </div>
      <div style="padding-left:96px"><span class="stline"><i class="dot"></i>已覆盖 · 仅报表生效</span></div>
    </div>
    <div class="dlg-foot">
      <span class="footnote">改路径只走覆盖根目录</span><span class="sp"></span>
      <button class="btn ghost sm" data-close>取消</button>
      <button class="btn primary sm" data-close>保存</button>
    </div>
  </div>
</div>
```

**减法要点**：没有"清空"按钮（用户自己删字）；底部只有取消/保存两个；
脚注一句话说清边界；`data-parent` 指向真正会打开它的页面。

### 6.2 多状态弹窗（默认 → 展开）

```html
<!-- 状态 1：默认 -->
<div class="dlg-modal" data-dialog="dlg-photo-root" data-title="报表照片根目录"
     data-w="560" data-h="210" data-parent="report" style="display:none"> ... </div>

<!-- 状态 2：展开清单（同一个功能的第二步，用 data-open 互切） -->
<div class="dlg-modal" data-dialog="dlg-photo-list" data-title="报表照片根目录 · 清单"
     data-w="640" data-h="420" data-parent="report" style="display:none">
  <div class="dlg" style="--dw:640px">
    <div class="dlg-title">报表照片根目录 · 清单</div>
    <div class="dlg-body" style="max-height:320px;overflow:auto">
      <table class="tbl"> ... </table>
    </div>
    <div class="dlg-foot">
      <span class="footnote">清单只读</span><span class="sp"></span>
      <button class="btn ghost sm" data-open="dlg-photo-root">返回</button>
      <button class="btn ghost sm" data-close>关闭</button>
    </div>
  </div>
</div>
```

**两个都是独立的 `data-dialog`，不要用 JS 在同一弹窗里切内部状态。**

### 6.3 危险操作确认

```html
<div class="dlg-modal" data-dialog="dlg-confirm" data-title="删除记录"
     data-w="440" data-h="190" data-parent="report" style="display:none">
  <div class="dlg" style="--dw:440px">
    <div class="dlg-title">删除 3 条记录？</div>
    <div class="dlg-body"><div class="tiny muted">删除后不可恢复，关联照片不会被删除。</div></div>
    <div class="dlg-foot">
      <span class="sp"></span>
      <button class="btn ghost sm" data-close>取消</button>
      <button class="btn primary sm" style="--primary:var(--ng)" data-close>删除</button>
    </div>
  </div>
</div>
```

危险按钮用 `var(--ng)` 红，标题写清数量与后果（"删除 3 条记录？"而不是"确认操作"）。

---

## 七、完整度清单（交付前逐条打勾）

### 7.1 页面

- [ ] 步骤 1 摸底列出的**每个**页面都有 `data-page`（不多不少）
- [ ] 主界面有侧栏/顶栏**全部入口**，且每个入口都是 `data-go` 指向真页
- [ ] 每个子页面有"← 返回"且 `data-go="main"`
- [ ] 每页 `data-states` 声明的状态都有 `.state-block`（W3 查）
- [ ] 每页有 `data-desc`（≤60 字）与 `data-points`（单条 ≤40 字）
- [ ] 每页有 `data-galaxy`，值来自步骤 2 的实际选型
- [ ] **每页最多 1 个 `.btn.primary`**（3 秒测试：视线能落到它）
- [ ] 页面级按钮 ≤ 10（硬上限 12，W5 查）、开关 ≤ 3（硬上限 5，W6 查）
- [ ] 顶栏可点 ≤ 4、侧栏项 ≤ 7、筛选控件 ≤ 4、页签首屏字段 ≤ 8
- [ ] 表格行操作只有 1 个"⋯"；数字列 `.num`；表头 ≤ 6 字
- [ ] 图标按钮都有 `title`（W8 查）

### 7.2 弹窗

- [ ] 步骤 1 列出的**每个**弹窗都有 `data-dialog`（导航里的新增/编辑/删除/设置都要算）
- [ ] 每个弹窗 `data-parent` 指向真正会打开它的页面（C16 查）
- [ ] 所有"新增/编辑/删除/详情/设置"入口都是 `data-open`
- [ ] 危险操作有二次确认；确认按钮红色 + 写清后果
- [ ] 多步弹窗拆成多个 `data-dialog`，用 `data-open` 互切
- [ ] 弹窗底部 ≤ 2 个按钮（取消 + 保存），表单弹窗不出现"清空"
- [ ] 弹窗宽度 360~720；超 720 改整页或抽屉

### 7.3 全局

- [ ] **9 基因红线**：主色跨 ≥3 色相家族、两套主色不同色相（C23）；任意两套
      10 个基因 Token ≥5 项不同（C24）；`--font` ≥2 种（C25）；`--shell` ≥3 种
      或存在 data-layout 分叉（C26）
- [ ] 出厂 Token 已按本次基因卡重校准，未原样交付模板内置值
- [ ] 明暗主题各截一张图，浅色下没有写死深色（尤其弹窗、KPI、表格斑马纹）
- [ ] 每页只有一个循环炫点（主界面扫描光带）；表单/表格/正文无渐变无光晕
- [ ] 关掉动效（顶栏"动效"）后信息仍完整可读
- [ ] `check_mockup.py` 0 FAIL（33 项）
- [ ] 截图看过：舞台 / 总览 / 跳转图 / 规范两栈 / 弹窗 / **5 套方案逐套各一张**

---

## 八、预算自检（30 秒数一遍）

打开任意页面，数这四个数，超了就回去合并：

```
按钮（不含表格行内）   ≤ 10，硬上限 12
开关                   ≤ 3，硬上限 5
首屏字段（一个页签）   ≤ 8
一行筛选控件           ≤ 4
```

再问三句：

1. **主操作是哪一个？** 指不出来 → 主色按钮太多，降级成 ghost。
2. **哪两个操作总是一起用？** → 合并（保存并测试）。
3. **哪个开关只影响本页？** → 改成页内模式选择（下拉/分段）。

---

## 九、常见破相与修法

| 症状 | 根因 | 修法 |
| --- | --- | --- |
| 切到浅色后某块还是黑的 | 写了 `#1a2331` 或 `rgba(0,0,0,.5)` | 换成 `var(--panel)` / `var(--border)` |
| 状态块的表格挤在一起 | `.state-block` 缺 `data-display="contents"` | 补上；默认 `block` 会破坏布局 |
| 弹窗里某个按钮样式怪 | 元素误用了 `.dlg` 类 | 改用 `.is-dlg` 或删掉类 |
| 总览缩略图太小/糊 | 页面 `data-w/h` 写错或没写 | 统一 1440×900 |
| 跳转图连线穿过节点 | 跨列长跳转太多 | 把目标页 `data-group` 调到相邻列 |
| 弹窗打开后背景页不对 | `data-parent` 写错（指到了 main） | 改成真正触发它的页面 id |
| 页面在 1366 屏溢出 | 内容宽度写死超过 1320 | 用 `flex` / `min-width:0` / 百分比 |
| 表格数字不齐 | 漏了 `.num` | 数字列加 `class="num"`（右对齐 + 等宽） |
| 空态出现时表头跳动 | 空态块放在表格外层 | 与表格同容器，块 `flex:1` |

---

## 十、URL 直达（截图 / 评审 / 回归都用它）

```
file:///.../ui_design_mockups.html?page=report&variant=c&scheme=light&stack=wpf
```

| 参数 | 取值 | 说明 |
| --- | --- | --- |
| `page` | 页面 id | 直接落到某页 |
| `dialog` | 弹窗 id | 直接打开某弹窗（会自动切到 `data-parent`） |
| `view` | `stage` `overview` `flow` `spec` | 四个视图 |
| `variant` | `a` `b` `c` `d` `e` | 五套方案 |
| `scheme` | `dark` `light` | 明暗 |
| `state` | `default` `empty` `loading` `error` | 页面状态 |
| `stack` | `winforms` `wpf` | 目标技术栈（规范视图高亮） |

参数会被写回 URL（`replaceState`），所以**用户手点出来的画面可以直接复制链接发给别人**。
