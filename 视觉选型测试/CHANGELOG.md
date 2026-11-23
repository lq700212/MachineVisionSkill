# 视觉选型测试 - 变更记录

## [v1.1.3]（2026-11-23）
### 新增：PPT 尺寸标注回归 + 画法模块契约（被测 skill v1.15.1~v1.15.3）
- **背景**：客户两次退回示意图——第一次标注端点与实体脱节（写死坐标，220mm 只有竖线
  没刻度），第二次工作距离从相机顶面起算（物理语义错，贴错实体）。修复分别落在
  C8 机检与 `tools/ppt_diagram.py` 模块，本次把两类缺陷全部用例化。
- **新增 15 条**（`test_ppt_quality_contract.py`，全量 **218 → 233**）：
  - `TestDimensionAnnotation`（C8，4 条）：端点悬空 WARN / 缺刻度横线 WARN /
    对齐放行 / 普通数据标注（如硬件页 WD 320mm）不误报；
  - `TestPptDiagramModule`（模块契约，7 条）：模块存在于 skill / shape 边界自动读取 /
    光源底面 / `Length` 按英寸处理 / 生成即满足 C8 / 端点传反报错 / `None` 报错；
  - `TestDimensionAnnotation` 追加 WD 语义 4 条：`add_wd_dim` 起点=镜头底（非相机顶）/
    终点=光源底 / 生成即过 C8 / 禁止 `top_edge` 覆盖。
- **验证**：全量 **233/233 通过**，失败 0、错误 0、跳过 0（18.4s）。

## [v1.1.2]（2026-11-22）
### 新增：精度口径语义回归（被测 skill v1.15.0，2026-11-22）
- **背景**：被测 skill 修正精度口径语义——"测量精度 X"直接÷亚像素因子（不再按整机公差
  分摊）、"±X"带宽翻倍、`precision_requirement` 绝对优先于 `tolerance`、默认分配 1/10→3/10。
- **新增 7 条**：
  - `test_selection_core.py`：测量精度不分配（0.5mm→166.7μm/px）、precision_requirement
    优先于已声明 model、默认 30% 分配（0.5mm→50μm，等效公差÷10）、核验报告显示 30%、
    tolerance-only 回填 0.075mm；
  - `test_text_entry.py`："测量精度0.5mm"自动标 `measurement_accuracy`、"±0.5mm"自动标
    `bilateral`（带宽 1.0mm）、模糊"精度0.5mm"不设 basis 保留人工确认；
  - `test_workflow_contract.py`：`precision_basis=measurement_accuracy` 端到端 exit 0。
- **验证**：全量 **218/218 通过**，失败 0、错误 0、跳过 0（29.9s，退出码 0）。

## Unreleased（v1.1.1）

### 新增：行业规范回归 + 跨 shell 编码稳定（2026-11-21）

- **背景**：被测 skill v1.14.0 对照工控选型规范补齐硬约束（频闪三态/接口带宽/
  快门类型/景深/MTF/衍射），需要一一沉淀回归；同时发现 Windows cp936 控制台
  下被测脚本 stdout 为 GBK，用例按 UTF-8 解码导致 12 条中文断言假失败。
- **新增 `test_industry_compliance.py`（8 条）**：光学估算函数（景深/MTF/艾里斑）、
  接口带宽判定、快门类型与运动场景、频闪三态、选型链与核验链精度口径一致。
- **扩充**：`test_data_integrity.py` 补 `mod`/`wd_range`/`wd_mag_table`/
  `external_candidates` 完整性；`test_selection_core.py` 补精度预算模型
  （system_budget/direct_measurement）与核验口径用例。
- **`run_all.py`**：`core` 层纳入新模块；启动时 `PYTHONIOENCODING=utf-8`
  注入子进程，任何 shell/代码页下结果一致（根因见文件内注释）。
- **验证**：全量 **211/211 通过、0 失败、0 错误、0 跳过**（17.7s，退出码 0）。

## Unreleased（v1.1.0）

### 新增：六层分区测试体系（2026-11-20）

- **背景**：全量只有"一把跑"，改一行代码也要等端到端；文档/数据完整性
  没有独立防线；检查器误杀正确型号（追光者 `FL-R-` 与旧型号触发词重叠）
  无人发现。
- **分层 runner**：`--layer smoke|data|doc|core|ppt|workflow`，支持逗号多层、
  `--list`、`--failfast`；`--fast` 兼容旧用法（跳过端到端重层）。
- **新增 5 个测试文件**：
  - `test_smoke.py`（L0，秒级）：文件/依赖/JSON/frontmatter/无临时脚本
  - `test_data_integrity.py`（L0）：硬件库 schema、verified 必须有官网链接、
    假型号黑名单、光源角度/数值合法、未核验条目必须有 note
  - `test_doc_contract.py`（L0）：文档引用的脚本/CLI 参数/模板字段与代码一致、
    红线条款存在、退出码三态写在最短路径
  - `test_ppt_quality_contract.py`（L1）：当前型号白名单放行、旧型号/历史假型号
    拦截、待选型残留拦截、无硬件页 exit 2
  - `test_workflow_contract.py`（L2）：无模板 SELECTION_ONLY、缺字段 exit 2、
    口径硬阻断/确认放行、产物 schema、重复运行只留 1 个 PPT、`--no_verify` 警告
- **被测 skill 同步修复**：`check_ppt_quality.check_stale_models` 增加选中型号
  白名单（此前 `追光者 FL-R-10045-W` 被误判为旧型号残留，验收会 FAIL）；
  `is_hardware_slide` 改为"标题精确 + 标注框/参数词"分级判定（目录页与
  选型计算页不再被误当硬件展示页）。
- **验证**：全量 144/144 通过（0失败 0跳过，26.7s）。

## 元数据：frontmatter `name` 改 ASCII slug（DSH 接入，2026-10-22）

- 仅改 SKILL.md frontmatter 的 `name`：`视觉选型测试` → `vision-selection-test`（1 行）；目录名/正文/测试用例零改动，未升版
- 原因：DSH 加载器硬校验 `SKILL_NAME = /^[a-z0-9]+(-[a-z0-9]+)*$/`，中文名被静默丢弃（不可调用）
- 影响：DSH 内本 skill 调用名改为 `vision-selection-test`；目录名不变，`SKILL.md` 与 `AGENTS.md`
  里的脚本路径引用（`.../skills/视觉选型测试/tests/run_all.py`）不受影响

## v1.0.0（初始基线）

- 本文件为 2026-10-22 补建：此前 `视觉选型测试` skill 未单独维护 CHANGELOG，
  历史改动见根目录 `CHANGELOG.md` 与 `视觉硬件选型/CHANGELOG.md` 中的相关条目
