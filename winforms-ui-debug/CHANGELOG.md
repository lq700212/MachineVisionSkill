# 更新日志

`winforms-ui-debug` skill 的所有版本变动统一记录在此。格式参考 Keep a Changelog。

## [Unreleased]

- 新增 SKILL.md 血泪第 43 条（AgingTestSystem V1.81.2 两轮实锤）：自绘画布开 DoubleBuffered 逼文字走离屏慢路径（25行×2处≈110ms/帧、滚快拖影）＋ PrintWindow 在滚动后丢 GDI 文字；修法关双缓冲直画屏幕 DC＋OnPaint 按裁剪区自填底＋长文本预截断；取证改离屏 OnPaint 重放计数＋置顶真屏 CopyFromScreen。
- 新增 SKILL.md §十连线判交一条（V1.81.4 跨项目通用）：连线类图元判交用控制点包围盒不用两端点（贝塞尔中段穿屏、两端屏外时两端点判交会整条裁掉），箭头仍只在端点可见时画，配"两端出屏＋中段穿屏"正反断言。
- 新增 SKILL.md 血泪第 39〜42 条（AgingTestSystem V1.63.2/V1.71 实测）：UITabControl 必须走 AddPage（手写 TabPage 包裹漏 Show 致空白页）/ Designer 声明/实例化配对扫描（多行替换吞 new 致 NRE）/ Sunny 自绘控件类型判定三兄弟（UIButton/UITextBox/UIComboBox 非原生子类）/ UIForm 标题禁区两种姿势（绝对布局下移 35px、Dock 布局加 Padding）。
- 新增 SKILL.md 血泪第 35b 条（DarkGlyph 扩展到 ToolStripItem + 老资源先像素普查再定策略，HuaJiVision V4.4.17）：菜单项独立原图本；Designer 的 ImageTransparentColor 声明可能是残留，实测为准；§十清单第 5 条同步。
- 新增 SKILL.md 血泪第 35c 条（下拉菜单换肤走 ToolStripManager 全局接管，HuaJiVision V4.4.17）：逐个设下拉 Renderer 粘不住读回默认；浅色还接管前原值+ForeColor=Empty；Empty 读回的是继承默认值，断言用读回值；§十清单第 6 条同步。

- 新增 SKILL.md §十"深色模式换肤专项"（HuaJiVision V4.4.13→V4.4.16 四轮沉淀）：新界面一步到位 10 条 + 落点对照表（色板/三 Tag/探针 I14〜I17·SG22〜SG25）；frontmatter 触发词补"深色模式/换肤/主题"。
- 新增 SKILL.md 血泪第 32〜38 条（换肤快照先整树后刷色 / 禁用组标题系统灰字 / ToolStripItem 不在 Controls / 字形按钮暗底白字三件套 / 预乘 Alpha 断言容差 250 / Sunny 组框认 FillColor / 探针必配反向验证）；章节重排（新§十深色，原§十〜十三顺延为§十一〜十四；§四注记的§十一引用现有所指正确）。
- 新增 SKILL.md 血泪第 29 条（Sunny UIForm 客户区顶部 35px 自绘标题禁区，HuaJiVision V4.4.8 实测）：Y<35 控件 Add 时被强制搬到 Y=35；修法首行从 Y≥40 起排；验证 new 完即打印 Bounds + 截图确认组框标题。
- 新增 SKILL.md 血泪第 28 条（TableLayoutPanel 固定列高 DPI 余量 + 单行输入框余量 + 假绿探针三连坑，HuaJiVision V4.4.7 实测）：固定列各加 12px + AutoEllipsis 保险；授权码输入框窗加宽 40；反射模拟改 1.5x 字体实测 + 余量阈值 + 反向验证。
- 删除 SKILL.md §十三附录 B（来源与版本）：与本文件 v1.0.0 节重复，改为一句指向
  CHANGELOG；附录 A 项目档案完整保留（开工查表用）。

## [v1.0.0] - 2026-09-05

### 新增：四项目 skill 合并为全局唯一版本

- **来源**：
  ① `AgingTestSystem/.opencode/skills/winforms-ui-debug`（§一〜§四、血泪 1〜12、
  高 DPI 专项、验证收尾方法论底稿）；
  ② `CommandCenter/.opencode/skills/winforms-ui-debug`（Maximized 禁缩放专项、
  点击双击判定、ComboBox 选中高亮）；
  ③ `HJVision/.opencode/skills/winforms-ui-debug`（CheckBox 膨胀、ElementHost、
  无边框标准做法、V4.7.3 系列 12 条）；
  ④ `kaleidoscope/.opencode/skill/ui-layout-debug`（矩形枚举与真实截图 §十 +
  `scripts/` 四脚本原型）。
- **合并时修掉的旧坑**：
  三份 winforms-ui-debug 的构建命令/bin/窗体引用全写 AgingTestSystem
  （CommandCenter/HJVision 两份从未适配，frontmatter 还写着"AgingTestSystem 专属"），
  已正名为通用模板 + 附录 A 项目档案；
  HJVision 两条"验证模态 ShowDialog"（keybd 物理按键法 + Timer 线程池法）合并为一条；
  Kaleidoscope 脚本业务默认值（进程名/exe 路径/示例坐标）全部参数化；
  `Get-ControlTree.py` 的 taskkill 全同名清理改为精确清理（与 `Get-WindowShot.py` 对齐）；
  PrintWindow 与 CopyFromScreen 的矛盾写法收敛为条件选用表（§十末尾）。
- **四处源 skill 已删除**，后续沉淀统一回写到本 skill。
- **验证**：Python 双脚本 `py_compile` 通过；PS 双脚本带 BOM 断言 + 解析无报错；
  三态参数校验（缺 `--exe`/缺 `--process`/`--help`）行为正确。
