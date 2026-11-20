---
name: vision-selection-test
description: "视觉硬件选型 skill 的专用分层测试套件：冒烟/数据/文档/核心/PPT/工作流六层，支持按改动选层快跑。当用户要求测试或验证视觉硬件选型 skill、修改过该 skill 的任何脚本或数据库、或需要确认旧功能/工作流没被改坏时，必须调用本 skill。全绿才算迭代完成。"
---

# 视觉选型测试

被测对象：`视觉硬件选型` skill（默认 `C:\Users\Administrator\.config\opencode\skills\视觉硬件选型`，
可用环境变量 `VISION_SKILL_DIR` 覆盖）。

## 一条命令全量验证

```bash
python "C:\Users\Administrator\.config\opencode\skills\视觉选型测试\tests\run_all.py"
```

## 分层（改完代码先跑对应层，交付前必须全量）

| 层 | 命令 | 耗时 | 覆盖 |
|----|------|------|------|
| smoke | `--layer smoke` | ~3s | 文件齐全、依赖可导入、JSON 可解析、无临时脚本混入 |
| data | `--layer data` | ~2s | 硬件库 schema、verified 必须有官网链接、无假型号回流、角度/数值合法 |
| doc | `--layer doc` | ~3s | SKILL.md/README 引用的脚本与参数真实存在、模板字段真被代码消费、红线在案 |
| core | `--layer core` | ~40s | 选型算法/精度链/口径/光源角度品牌/文本解析/图片获取 |
| ppt | `--layer ppt` | ~10s | check_ppt_quality 判定边界（旧型号误杀/假型号漏放） |
| workflow | `--layer workflow` | ~2min | 端到端退出码 0/1/2、产物 schema、幂等、验收隔离 |

其他参数：

| 参数 | 说明 |
|------|------|
| （无参数） | 全量六层 |
| `--fast` | 跳过端到端重用例（workflow 层），只跑 smoke+data+doc+core+ppt |
| `--list` | 只列出用例清单，不运行 |
| `--failfast` | 首个失败即停（定位问题时用） |

## 按改动选层（调试速查）

| 你改了什么 | 最少要跑 |
|-----------|---------|
| 任何 `.py`（不确定影响面） | `--layer smoke` |
| 相机/镜头选型、精度链 | `--layer core` |
| `light_selector` / 光源库 / 品牌角度 | `--layer data,core` |
| `hardware_database.json`（扩库/fetch/refresh） | `--layer data` |
| `generate_ppt` 替换规则 | `--layer ppt,workflow` |
| `check_ppt_quality` | `--layer ppt` |
| 主流程 / CLI / 验收 / 退出码 | `--layer workflow` |
| `SKILL.md` / `README.md` / `config_template.json` | `--layer doc` |
| 图片获取 / 横幅合成 | `--layer core` |
| **交付前（无论改了什么）** | **全量 `run_all.py`** |

## 结论解读

- `结论: ✓ 全部通过` → 该层通过；若只跑了部分层，脚本会提示交付前跑全量
- `结论: ✗ 存在失败` → 看失败用例名定位模块，**修复后必须重跑全量**；
  处置不了的原样报告用户，禁止改被测脚本硬凑通过
- `跳过` = 在线用例探测到官网不可达（自动跳过不算失败）；`--fast` 会主动跳过 workflow 层

## 用例构成

| 文件 | 层 | 覆盖 |
|------|----|------|
| `test_smoke.py` | smoke | 交付结构、模块导入、JSON 资产、frontmatter slug |
| `test_data_integrity.py` | data | 硬件库必填字段、verified/URL 对应、假型号黑名单、光源角度数值 |
| `test_doc_contract.py` | doc | 文档引用的脚本/CLI 参数/模板字段与代码一致、红线条款存在 |
| `test_selection_core.py` | core | 精度链、口径决策、远心降级、飞拍、光源防幻觉/角度/品牌 |
| `test_text_entry.py` | core | `--text` 解析、像素精度/设备精度判别、非交互防卡死 |
| `test_channel3.py` | core | 浏览器接管通道（参数顺序/timeout/降级） |
| `test_image_fetch.py` | core | 官网产品图获取、型号防串行、诚实降级 |
| `test_ppt_quality_contract.py` | ppt | 当前型号白名单放行、旧型号/假型号拦截、硬件页识别（目录/计算页不误判）、无硬件页 exit 2 |
| `test_ppt_pipeline.py` | workflow | config→选型→核验→PPT→验收 FAIL=0、验收隔离 |
| `test_workflow_contract.py` | workflow | 无模板 SELECTION_ONLY、缺字段 exit 2、口径硬阻断、幂等、产物 schema |

## 测试纪律

1. 被测 skill 每修一个 bug，必须在这里**补一个对应回归用例**（bug→用例一一沉淀）
2. 注入用例对应历史事故（串行参数/凑口径/编造光源/误杀正确型号），禁止删除
3. 在线用例必须能离线自动跳过，不允许因断网误报 FAIL
4. 新增测试文件后，必须登记到 `run_all.py` 的 `LAYERS` 与上表；否则 `--layer` 会漏跑
