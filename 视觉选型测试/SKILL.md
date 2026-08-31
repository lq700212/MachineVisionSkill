---
name: 视觉选型测试
description: "视觉硬件选型 skill 的专用测试套件：回归测试+注入测试一键全量验证。当用户要求测试/验证视觉硬件选型skill、或刚完成该skill的开发迭代（改过选型/生成PPT/数据库/图片获取等任何脚本）后必须调用本skill跑验证，全绿才算迭代完成。"
---

# 视觉选型测试

被测对象：`视觉硬件选型` skill（默认 `C:\Users\Administrator\.config\opencode\skills\视觉硬件选型`，
可用环境变量 `VISION_SKILL_DIR` 覆盖）。

## 一条命令全量验证

```bash
python "C:\Users\Administrator\.config\opencode\skills\视觉选型测试\tests\run_all.py"
```

| 参数 | 说明 |
|------|------|
| （无参数） | 全量：离线+在线+重用例（PPT端到端约1~2分钟） |
| `--fast` | 跳过重用例（PPT端到端），只跑核心+注入 |

## 结论解读

- `结论: ✓ 全部通过` → 迭代完成，可交付
- `结论: ✗ 存在失败` → 看失败用例名定位模块，**修复后必须重跑全量**；
  处置不了的原样报告用户，禁止改被测脚本硬凑通过
- `跳过` = 在线用例探测到官网不可达（自动跳过不算失败）；重用例在 `--fast` 下跳过

## 用例构成（回归+注入两类，缺一不可）

| 文件 | 覆盖 | 类型 |
|------|------|------|
| test_selection_core.py | 精度链计算、口径决策表优先级（precision_requirement vs tolerance）、无解缺口报告 | 回归+注入 |
| test_text_entry.py | --text 从0入口解析、缺参数防呆（exit指引不卡死） | 回归+注入 |
| test_image_fetch.py | 官网产品图获取：横幅合成、型号防串行、诚实降级（型号不存在/未接入品牌/系列名错） | 回归+注入 |
| test_ppt_pipeline.py | config→选型→核验→PPT→验收 FAIL=0 全链路端到端 | 回归 |

## 测试纪律（详见 AGENTS.md）

1. 被测 skill 每修一个 bug，必须在这里**补一个对应回归用例**（bug→用例一一沉淀）
2. 注入用例对应历史事故（串行参数/凑口径/编造图片），禁止删除
3. 在线用例必须能离线自动跳过，不允许因断网误报 FAIL
