# CHANGELOG

## v1.1.0 — 2026-11-28

**弱模型加固：核验从“结构完整”升级到“内容不空洞”。**

- `verify_report.py` 新增 6 组内容级检查（FAIL 即打回）：
  - 结论速览禁止“需进一步 / 待确认 / 视情况”等空话，必须有明确可行性判断。
  - 未知项验证方法必须具体；责任方 / 截止不得写“待定 / 无”。
  - 风险对策不得空泛（如“加强管理”）；触发信号不得少于 6 字。
  - 行动表负责人 / 截止 / 产出不得写“待定 / 无”；列表项不得少于 8 字。
  - 未知项 / 风险 / 行动表不得有空单元格。
  - 全文“待定 / 待确认 / 视情况 / 需进一步”合计不得超过 4 处。
- `verify_report.py` 收紧两处：图片缺说明由 WARN 升为 FAIL；`numbers` 为空由静默跳过改为 FAIL。
- 新增 `templates/example_report.md`：完整合格样例（15 PASS），弱模型照它写密度和句式。
- `SKILL.md` 新增“执行卡”（8 步 + 三条禁令）和“模型能力与分工”（判断由人给，弱模型只填空）。
- `crop_annotate.py` 新增未裁剪警告：未配置 crop，或 crop 面积占原图 >95% 时提示目检。
- `new_report.py` 输出提示改为先读样例、用 `--strict` 核验。

**验证结果：**

- 弱模型空洞样本：14 PASS / **21 FAIL**（结论空话、责任方待定、对策空泛、行动未落实）。
- RFID 正样本：14 PASS / 0 WARN / 0 FAIL。
- 合格样例：15 PASS / 0 WARN / 0 FAIL。
- 空骨架：11 PASS / 1 WARN / **25 FAIL**（预期，骨架不能直接交）。

## v1.0.0 — 2026-11-28

- 首个版本，沉淀自 RFID 过账项目内部技术评估。
- 脚本：
  - `init_project.py`：初始化目录与 project.json
  - `extract_images.py`：从 opencode 会话库提取用户上传图片
  - `crop_annotate.py`：批量裁剪、缩放、右侧标签标注
  - `make_charts.py`：架构图 / 工作量对比 / 甘特图 / 风险矩阵 / 场景图
  - `new_report.py`：按模板生成文档骨架
  - `verify_report.py`：编码、章节、图片、占位符、表格、数字一致性核验
- 模板：`project.example.json`、`report_template.md`（12 节通用结构）
- 适用：工业上位机、机器视觉、嵌入式、数据采集、网络改造、旧系统迁移、软件集成。
