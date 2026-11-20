# 视觉选型测试 - 变更记录

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
