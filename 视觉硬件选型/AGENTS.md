# AGENTS.md - 本 skill 的开发规范（开发/迭代前必读）

> **定位与使用/开发隔离**：本文件是给**开发和维护本 skill 的 Agent** 看的。
> 运行时调用本 skill 的 Agent 只读 `SKILL.md`（使用说明），不会读到这里——两条路径互不干扰。
> 只要你的任务是改这个 skill 的代码/文档/数据，先把本文件读完再动手。
>
> **单一副本（2026-08-30 起）**：skill 真实文件只有一份，位于
> `C:\Users\Administrator\.config\opencode\skills\`（opencode 直接读它；ZCode 的
> `C:\Users\Administrator\.agents\skills` 是指向它的 NTFS junction，两个工具共用同一份）。
> 改完文件即对两个工具同时生效，**不存在同步步骤**；今后新装 skill 也统一装到
> opencode 目录一份即可。

## ⛔ 开发铁律（全部来自真实事故，违反即重蹈覆辙）

1. **先排查清楚，再动手改**。修 bug 前必须走完整数据链核实来源，禁止"印证式确认"
   （曾犯：数据库 WD=110 错误，我引用该错误值"验证"了自己的推断，被用户以官网参数
   158±3 打脸。引用错误来源做二次确认不是确认）。
2. **参数禁止从型号名推断**。DTCM110 的"110"与工作距离无关（实际 158±3/138±3），
   WWK 系列的"110"恰好就是 WD 110±2——同一个数字在不同系列含义不同。所有参数
   以官网页面原文为准，入库走 fetch 提取，公差存 wd_spec 字段。
3. **写完必实测，两类测试缺一不可**：
   - 回归测试：正常链路跑通（FAIL=0）
   - 注入测试：把历史缺陷手工注入（旧型号残留/串行参数/超长文本/物理不可能WD），
     确认机检/核验能检出，再还原
   - 标准动作：跑专用测试套件 `视觉选型测试`（一条命令全量回归+注入，
     22用例）：python "C:/Users/Administrator/.config/opencode/skills/视觉选型测试/tests/run_all.py"
     ——修任何 bug 后必须在此套件补对应回归用例再修到全绿
4. **字段语义必须写在代码注释+本文档**（曾犯：lens_wd=系统工作距离基准这个语义
   只在代码里，导致"相机工作距离"被质疑时无法快速自证）。
5. **改任何 skill 文件后更新 CHANGELOG.md**（版本号+变更点；版本变动统一记录在该
   文件）。skill 为单一副本（ZCode 经 junction 共用 opencode 目录），改完即生效，无需同步。
6. **提取器必须做"型号归属"校验**（曾犯：WWK05 在系列页导航区出现，全文正则把
   WWK03 的倍率 0.3 提给了它；正确值 0.5）。提取优先级：表格<tr>行 → 卡片容器 →
   全文（全文回退遇多型号页必须拒绝并提示 --html 通道）。
7. **诚实降级优于编造**：通道取不到数据就报错退出（exit 2），绝不猜值填库；
   型号在官网下架/查证URL失效 → verified 回退 false 待人工确认。

## 架构地图（tools/）

```
vision_proposal_generator.py  主流程编排：需求校验→选型→库保鲜(超龄自动官网refresh)→核验→PPT→自动验收→预览
├── parse_user_data.py        用户资料/需求文本参数提取（--files/--text 入口；detection_type测量场景识别）
├── precision_calculator.py   精度链计算：像素精度上限=精度/k；倍率窗口；无解诊断；
│                             is_measurement_scene测量场景单点判定（选型分层与核验共用）
├── camera_selector.py        相机选型（视野+精度双约束，需求侧推导）
├── lens_selector.py          镜头联动匹配（倍率闭区间∩库内镜头）+ 测量场景远心优先分层
│                             （远心层无匹配自动回退普通镜头，标记telecentric_fallback）+ 无匹配根因分类
├── light_selector.py         光源选型（WD≤镜头WD-15 物理约束）
├── validate_selection.py     9项选型核验（FAIL中止），含光源WD<镜头WD、远心回退风险WARNING
├── generate_ppt.py           模板数据替换（触发词规则；WD显示优先wd_spec）
├── check_ppt_quality.py      PPT规则自查7项（历史缺陷全部机检化）
├── export_ppt_images.py      预览三件套（PNG/联系表/index.html；COM→LibreOffice降级）
├── database_updater.py       官网查证扩库：gap/fetch三级通道/add强校验/verify/check-db/refresh
├── fetch_product_image.py    官网产品图自动获取（海康API通道）：防串行→下载原图→合成横幅→写库
└── clean_ppt_shadows.py      阴影清理（历史污染修复工具）
```

数据流：用户资料 → project_config.json（口径拍板）→ 选型（倍率窗口=相机×镜头联动）
→ selection_result.json（validation_passed 必须True）→ 模板PPT替换 → check_ppt_quality
（FAIL=0 才可交付）→ ppt_review 预览。

## 关键语义表（改代码前先对齐认知）

| 概念 | 语义 | 常见误解 |
|------|------|----------|
| precision_requirement | 设备检测精度(mm) | 不是像素精度！像素精度上限=它÷pixel_per_precision |
| lens.working_distance | 镜头物方WD=系统工作距离基准（远心不可调焦） | 不是"可随意设的安装距离" |
| wd_spec | 官网原文公差（如158±3），PPT显示优先于数值 | 数值字段用于计算，spec用于展示 |
| 光源工作距离 | 必须 < 镜头物方WD（光源装镜头与工件之间） | 经验公式值仅是起点，超约束自动cap |
| magnification | 物方放大倍率β | 不能从型号名猜（64H≠0.64x） |
| verified | 官网人工对照过=true | fetch自动提取=false，选型参与但带警告 |
| detection_type / is_measurement_scene | 测量场景判定（单点函数：类型关键词/application/精度≤0.01mm） | 选型远心分层与核验判定必须共用同一函数，两链各写一套必漂移 |
| telecentric_fallback | 测量场景远心无匹配回退普通镜头的标记 | 是权宜方案不是错误：核验WARNING提示透视误差，交用户拍板，不FAIL拦死 |
| 库=官网缓存 | 选中超龄条目主流程自动官网refresh（无变化续期/有变化入库重跑选型） | 官网才是数据源；联网失败WARN降级用库内值，不阻断交付 |

## 运行时工作区约定（开发测试时也要遵守）

- 用户工作区（如 E:\Agent工作空间\视觉方案\）只有数据没有代码：用户资料图片、模板
  `视觉检测方案.pptx`（只读不写）、`project_config.json`（口径字段禁改）、`output\` 交付物
- 交付物在 `output\`：方案PPT（验收通过自动只留最新版）、selection_result.json、
  acceptance_report.txt、ppt_review\ 预览三件套；中间失败版本由脚本自动清理
- 工作区不再有 AGENTS.md（已并入本 skill）：运行时入口=SKILL.md「标准作业流程·最短路径」，
  project_config.json 内有 `_使用指引` 兜底字段指向它

## 标准开发流程

1. 动手前：读完本文件 + 相关脚本现状 + git/备份现状（库改前自动 .bak）
2. 改代码：遵守现有风格；新逻辑必须有根因注释（写给下次排查的人）
3. 测试：
   - 回归：`python vision_proposal_generator.py --config <工作区config> --output <临时目录> --auto` → FAIL=0
   - 注入：按第3条铁律构造缺陷样本验证检出
   - 数据改动：`database_updater.py check-db` + 选型重跑核对数值
4. 更新 CHANGELOG.md（版本号+要点），同步本文件如有新教训
   （skill 单一副本，改完即对 ZCode/opencode 同时生效，无同步步骤）

## 数据治理（hardware_database.json）

- 来源强制：verification_url 必填且必须**可回访**（专用详情页会失效，失效即 refresh 重取）
- 保鲜：check-db 审计180天未复核；refresh 三级通道 diff→apply→verify 闭环
- 新型号入库：fetch（自动提取+串行防护）→ 人工对照**详情页原文**逐项核对 → add → verify
- 下架/失效型号：verified 回退 false，history 记录，不悄悄删除

## 历史事故档案（每次迭代前扫一眼）

| 事故 | 根因 | 已固化的防线 |
|------|------|-------------|
| 库内DTCM系列WD=110（实际158±3/138±3） | 入库时从型号名推断 | fetch提取+README禁令+wd_spec公差 |
| 我引用错误库值"印证"自己的推断 | 没有走官网核实数据链 | 铁律1：先排查再动手 |
| WWK05提取出0.3x（正确0.5x） | 卡片页全文正则串行 | extract_card_params+串行风险拒绝 |
| config链漏选型核验 | 两链不同步 | 两链共用核验代码路径对齐 |
| 弱模型死循环调参 | 无解输出无决策指引 | 无解诊断+口径自动复核+铁律输出 |
| 光源WD公式可算出>镜头WD | 公式没看镜头WD | cap约束+核验FAIL |
| PPT的WD断行/类型矛盾/残留 | 模板替换边界 | check_ppt_quality 7项机检 |
