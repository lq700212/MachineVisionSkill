# AGENTS.md - 视觉选型测试 skill（开发规范）

本 skill 是 `视觉硬件选型` skill 的专用测试套件。职责单一：跑测试、出结论。
不包含任何被测逻辑的复制——所有被测代码通过 `vt_common.py` 注入 sys.path 后
直接 import 被测 skill 的模块，测的就是运行时真实代码。

## 铁律

1. **bug→用例一一沉淀**：被测 skill 每修一个 bug（或发生一次事故），必须在本套件
   补一个能复现该 bug 的回归用例，再修到通过。用例名带事故语义（如
   `test_tolerance覆盖precision回归`），让后人看得懂为什么有这条。
2. **注入用例不许删**：历史事故类注入（串行参数/口径凑解/编造图片/下架型号误用）
   是防退化的最后防线，重构时只能迁移不能删除。
3. **在线用例必须可离线跳过**：任何依赖官网/网络的用例，用 `vt_common.online()`
   作 skipUnless 条件；断网时输出 SKIP 而非 FAIL。
4. **测试不污染真实数据**：涉及写库/写文件的用例一律用临时目录副本
   （`vt_common.temp_dir()`），禁止指向真实 `config/hardware_database.json` 与
   `images/`；端到端用例输出到临时目录，不碰工作区 `output/`。
5. **失败要可定位**：断言消息写清"期望什么/实际什么/可能原因"，
   让弱模型拿着失败输出就能定位模块。
6. **测试脚本只放本目录**：被测 skill 的 tools/ 里禁止出现测试代码（职责分离）。

## 结构

```
run_all.py            测试runner（unittest discover + 中文汇总 + exit code）
vt_common.py          公共设施：被测skill路径/sys.path注入/联网探测/临时目录
test_selection_core.py  精度链、口径决策表、核验器
test_text_entry.py      --text 从0入口解析与防呆
test_image_fetch.py     官网产品图获取（合成/防串行/诚实降级）
test_ppt_pipeline.py    config→PPT→验收 端到端（重，--fast 跳过）
```

## 已沉淀事故对照（用例 ↔ 历史bug）

| 用例 | 对应事故 |
|------|----------|
| test_precision_priority_over_tolerance | tolerance 无条件覆盖 precision_requirement，项目唯一可行相机被口径漂移挤出局，选型无解（2026-08-30） |
| test_match_model_exact_* / test_inject_* | WWK05 提取串行拿到 WWK03 参数（v1.6.1）；型号名推断WD入库（v1.6.1） |
| test_e2e / test_inject_model_missing | 产品图获取必须诚实降级，禁止编造图片（2026-08-30 新功能约定） |
| test_e2e force=True / test_missing_base_model_lists_variants / test_reuse_existing_local_banner | 复用短路架空 e2e（2026-08-30）：fetch 加"本地已有图直接复用"后，e2e 用例静默走了短路，网络全链路与写库逻辑不再被覆盖——断言全过但测的是别的行为。教训：**给被测代码加速缓存/短路时，必须同步检查既有端到端用例是否被短路绕过**，端到端用例加 force/绕过缓存的开关；短路本身单独补一条用例。跑完套件要扫 stdout 里的"复用/缓存/跳过"字样核对用例实际路径 |
| test_ppt_replace_* | 换图预览固化（2026-08-30）：replace 子命令三条底线——预览件绝不改原方案（字节级断言）、0命中不留半成品、CLI 弱模型入口必须有用例 |
