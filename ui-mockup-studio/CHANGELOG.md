# 更新日志

`ui-mockup-studio` skill 的所有版本变动统一记录在此。格式参考 Keep a Changelog。

## [1.1.0] - 2026-11-16

### 新增

- **双栈落地映射**：`galaxy → WinForms（GDI+/SunnyUI）` 与 `galaxy → WPF（XAML）` 两套。
  模板 `spec` 视图内置两张映射卡，值全部从当前方案的 `getComputedStyle` 实时取 Token——
  切方案/切明暗时两套代码同步变，评审时可直接指着说"这套在我们项目里就是这几个常量"。
  `html[data-stack]` 只决定哪张标"目标栈"并高亮，两套始终都在页面上可对照。
- **`--stack winforms|wpf`**：`new_mockup.py` 生成时直接定目标栈；顶栏可切换；URL 支持 `?stack=`。
- **信息预算（减法硬指标）**：一屏主操作 1 个、按钮 ≤10（硬限 12）、顶栏可点 ≤4、侧栏 ≤7、
  开关 ≤3（硬限 5）、页签首屏字段 ≤8、一行筛选 ≤4、表格行操作 ≤1 个"⋯"、
  页面说明 ≤60 字、单条要点 ≤40 字。超预算必须在右栏写一句为什么。
- **炫点配额**：一屏只允许 1 个循环炫点 C 位（模板示范=相机磁贴扫描光带 4.2s / 主色 13% /
  四块错峰）；表单、表格、正文禁止炫；关掉动效后信息必须仍完整可读。
- **参数与时机**：SKILL.md 新增模式 A/B/C 判定表、步骤 2.5 信息架构减法（先减法再出稿）、
  步骤 3.5 定目标技术栈。
- **`references/simplify-playbook.md`**：原 `ui-simplify` skill 完整并入，并补
  信息预算表、合并五判定、易上手 3 秒/三步/闭眼测试、炫点配额、WinForms 坑位 10 条、
  两栈衔接口径（先减法定架构 → 再出 5 版稿，顺序不能反）。
- **`references/mockup-spec.md`**：data-* 全表（17 个）、类名速查、标准页面/表格页/配置页/
  多状态/三种弹窗可直接粘的片段、完整度清单、预算自检、破相修法、URL 直达表。
- **`references/galaxy-map.md`**：11 分类用途 + 中英检索词表 + CSS → WPF / CSS → WinForms
  两套属性对照、可直接复制的 XAML 样式与 C# 自绘控件（圆角按钮/卡片/开关/动效）、
  两栈落地坑位与选择速查。
- **`check_mockup.py` 扩到 25 项**：C17 `data-stack` 合法、C18 两套映射卡都在、
  W5 页面按钮预算、W6 开关预算、W7 说明字数预算、W8 图标按钮必须有 `title`。

### 变更

- 模板示例按减法改造，自身就是示范：主界面顶栏只留料号+设置（1 入口）、侧栏 7→5 项
  （设备通讯合并）、日志 5→3 行、报表筛选 4→3 输入、通讯参数 6→3
  （IP:端口、心跳地址·周期合并）、弹窗删"清空"按钮、行操作收进"⋯"。
- 顶栏技术栈按钮改纯文本（无 emoji 字体环境会显示成方块）。
- 模板与文档示例中的项目名脱敏为通用"视觉检测系统 / Vision Suite"。

### 删除

- 全局 skill `ui-simplify` 目录整体删除（内容已并入本 skill，引用改指
  `references/simplify-playbook.md`）。

## [1.0.0] - 2026-11-16

### 新增

- SKILL.md 首版：galaxy 解析/检索 → 5 套方案 → 出稿 → 核验 → 收尾的完整工作流，
  含 8 条铁律（galaxy 来源 / DOM 只写一次 / 禁止写死 Token / 跳转必须声明 /
  多状态弹窗 / 单文件离线 / 0 FAIL + 截图 / UTF-8）。
- `scripts/resolve_galaxy.py`：定位 galaxy（`--path` → 缓存 → 常见路径 → D:/E: 扫描 →
  `git clone --depth 1`，直连失败自动换 gh-proxy / ghfast 镜像），路径写回 `config.json`。
- `scripts/galaxy_search.py`：11 分类列目录、按 tags 检索、`--show` 看源码、`--random` 抽样。
- `scripts/new_mockup.py`：从模板生成到项目 `Docs/`（自动建目录、默认拒绝覆盖、`--force`）。
- `scripts/check_mockup.py`：19 项核验（结构 / 跳转目标 / 编码 / 离线 / 占位符 / 多状态对应）。
- `templates/mockup_base.html`：工作台模板——5 套方案 × 明暗（DOM 只写一次）、4 视图
  （舞台/总览/跳转图/规范）、3 示例页 + 3 弹窗（含展开态与确认态）、URL 直达、
  自动左栏树/总览/跳转连线/右栏说明。
- `references/design-playbook.md`：干净整洁的 8 条硬指标、信息层级、留白节奏、
  动效参数、常见破相清单、5 套方案的设计原理。
