# Skills 仓库变更记录

> 用于 git 提交时快速确认**本次改动了哪些 skill、各改了什么**。
> 记录按时间倒序排列（新版本在上）。各 skill 的详细历史见其目录下 `CHANGELOG.md`。

## 2026-09-02（本次·视觉选型）

### 改动范围

本次改动 **2 个 skill：`视觉硬件选型`、`视觉选型测试`**。

### 视觉硬件选型

**v1.8.1**：修复"用户指定像素精度后弱模型思考死循环"bug。
- 根因：脚本无像素级口径入口——--text 正则把"像素精度：0.01mm/pixel"误抓成
  设备精度再÷3 → 无解；config 无 pixel_precision 字段；无解诊断只有"口径过松"
  单向提示，缺"口径过严"反向指引 → 弱模型无路可走只能调参死循环
- 修复：parse_user_data 新增像素精度专用提取（设备精度正则加负向后行断言防误抓）；
  _validate_params 支持 `pixel_precision` 字段（×亚像素因子换算等效设备精度，
  下游链零改动，口径冲突时像素级优先并警告）；无解诊断新增反向口径复核
  （<5μm/pixel 异常严格时明确指引改填 pixel_precision，禁止调参凑解）；
  config_template 决策表/SKILL.md 口径与铁律同步更新
- 验证：视觉选型测试套件新增 5 用例；另修复 2 处 CLI 用例的子进程编码问题
  （测试自身问题，详见视觉选型测试节），全量 **42/42 全绿**

### 视觉选型测试

- test_text_entry.py 新增 5 回归用例：像素精度文本解析（带/不带 /pixel 后缀）不被
  误抓成设备精度、设备精度不被像素通道劫持、config 像素级口径等效换算、
  口径冲突取舍
- 修复 test_image_fetch.py 两处 CLI 用例的环境性报错（测试用例自身问题）：
  `subprocess.run(text=True)` 未指定编码，子进程输出含 UTF-8 字符（±等）时被
  系统默认 GBK 解码，reader 线程抛 UnicodeDecodeError 致 `r.stdout=None`；
  补 `encoding='utf-8', errors='replace'`（与 test_ppt_pipeline 既有写法对齐）。
  修复后全量 **42/42 全绿**

### 建议 commit message

```
视觉硬件选型 v1.8.1：修复像素精度口径缺失导致的弱模型死循环

- 新增 pixel_precision 像素级口径入口（--text 解析 + config 字段）
- 设备精度正则加负向后行断言，防止误抓"像素精度"前缀
- 无解诊断新增反向口径复核（口径过严时指引改填 pixel_precision）
- 测试套件新增 5 回归用例 + 修复 2 处 CLI 用例子进程编码问题，全量 42/42 全绿
```

## 2026-09-02（盖章专员）

### 改动范围

本次仅改动 **1 个 skill：`盖章专员`**。

### 盖章专员

**v1.2.0**：新增 **Excel 工作簿输入支持**（xlsx/xls/xlsm/xlsb）

- 盖章前先调用本机 Office Excel COM 执行「另存为 PDF」（与人工另存为 PDF 等价，
  保留打印设置/分页），转换成文本版 PDF 后**走原有盖章管线**：定位 / 盖章 / 压平
  与 PDF 输入零差异，不新增任何定位逻辑
- 输出：`原Excel名_已盖章.pdf`（默认与 Excel 同目录）；转换失败时打印
  "手动用 Office 另存为 PDF 后重跑"兜底指引，不静默
- 依赖：`pywin32`（win32com）加入可选依赖（仅 Excel 输入需要，装不上不影响 PDF/图片/扫描件）
- 文档：SKILL.md 四类输入说明 + Excel 用法与决策表、AGENTS.md 架构/语义/事故档案、CHANGELOG v1.2.0
- 验证：`E:\Agent工作空间\盖章\` 两份报价单 xlsx 全流程盖章 PASS（章落点偏差 <3pts、
  压平防编辑、文字可搜）；回归 `tests/run_test4_scan.py` 24/24 PASS；`--dry-run`/`--role` 均正常

### 建议 commit message

```
盖章专员 v1.2.0：支持 Excel 工作簿输入（自动转 PDF 后走原盖章管线）

- Excel(xlsx/xls/xlsm/xlsb) 输入先在步骤0调本机 Excel COM 另存为 PDF，之后
  定位/盖章/压平与 PDF 输入完全共用，不新写定位逻辑；输出 原名_已盖章.pdf
- 转换失败给"手动另存为 PDF 后重跑"兜底指引；pywin32 登记可选依赖
- 验收：两份报价单 xlsx 全流程盖章，章落点偏差<3pts、压平防编辑、文字可搜；
  回归 tests/run_test4_scan.py 24/24 PASS
```

---

### 历史（本次之前）

- 2026-09-02 `盖章专员` v1.1.1：扫描件关键词定位三连修 + 骑压精对齐到命中关键词
- 2026-09-01 `盖章专员` v1.1.0：三类输入统一支持（文本版PDF/扫描件PDF/图片）
- 2026-08-31 `盖章专员` v1.0.0：首个正式版本（智能定位+防编辑压平）

> 提示：各 skill 的完整历史条目请直接看对应 skill 目录下的 `CHANGELOG.md`，
> 本文件只做「改动了哪个 skill、改了什么」的总览。