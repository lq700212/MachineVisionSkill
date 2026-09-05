# 更新日志

`winforms-ui-debug` skill 的所有版本变动统一记录在此。格式参考 Keep a Changelog。

## [Unreleased]

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
