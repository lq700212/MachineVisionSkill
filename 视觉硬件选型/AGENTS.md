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
8. **生成器上线/改名必须同提交改"主入口"文档**（曾犯：2D 12 页生成器已交付，
   SKILL.md「最短路径」仍指向模板替换，弱模型照文档走必交付 13 页旧版式）。
   任何新生成器、新入口、新默认路径上线时，同一次改动内必须更新：
   SKILL.md 顶部「30 秒执行卡」+「最短路径」表格 + CHANGELOG。
   **只改脚本不改文档 = 交付错版本**，且弱模型不会自己发现矛盾。
9. **弱模型链路必须"一条命令闭环"**：凡是需要"先跑 A 再跑 B"的两步操作，
   B 必须能自动补 A（如 selection 缺失自动选型、--text 自动落 config）。
   曾犯：`--text` 只出模板版不落 config，弱模型无法接 12 页生成器；
   2D 生成器要求先手动选型，两步之间无强制，弱模型只跑第一条就断链。

## 架构地图（tools/）

```
vision_proposal_generator.py  主流程编排：需求校验→选型→库保鲜(超龄自动官网refresh)→核验→PPT→自动验收→预览
├── parse_user_data.py        用户资料/需求文本参数提取（--files/--text 入口；detection_type测量场景识别）
├── precision_calculator.py   精度链计算：像素精度上限=精度/k；倍率窗口；无解诊断；
│                             is_measurement_scene测量场景单点判定（选型分层与核验共用）；
│                             is_moving_scene/shutter_kind/接口带宽/景深/MTF/艾里斑估算
├── camera_selector.py        相机选型（视野+精度双约束，需求侧推导；接收预算像素当量上限）
├── lens_selector.py          镜头联动匹配（倍率闭区间∩库内镜头）+ 测量场景远心优先分层
│                             （远心层无匹配自动回退普通镜头，标记telecentric_fallback）+ 无匹配根因分类
├── light_selector.py         光源选型（WD≤镜头WD-15 物理约束；strobe 三态）
├── validate_selection.py     13类选型核验（FAIL中止），含光源WD、远心回退、景深/MTF/衍射、
│                             接口带宽、快门类型、飞拍频闪三态
├── generate_ppt.py           模板数据替换（触发词规则；WD显示优先wd_spec）
├── ppt_layout.py             **PPT 骨架与版式唯一入口**：Deck 构件库 + STANDARD_PAGES/SECTIONS
│                             + run_quality_check/export_preview/discover_template（2D/3D 共用）
├── two_d_ppt.py              2D 客户版 12 页生成器（骨架生成 + 母版硬件页替换；
│                             自动补选型；scene/precision_chain 可配置）
├── three_d_ppt.py            3D 客户版 12 页生成器（骨架生成；自动补选型；
│                             点云图三级回退：实拍 → 内置缺省 → 占位）
├── check_ppt_quality.py      PPT规则自查8项（C1~C8，历史缺陷全部机检化）
├── export_ppt_images.py      预览三件套（PNG/联系表/index.html；COM→LibreOffice降级）
├── database_updater.py       官网查证扩库：gap/fetch三级通道/add强校验/verify/check-db/refresh
├── fetch_product_image.py    官网产品图自动获取（海康API通道）：防串行→下载原图→合成横幅→写库
├── three_d_selector.py       3D视觉引导选型（独立分支）：FOV/旋转包络校核、RSS误差预算、
│                             厂商guidance优先、数据置信度降权、ETH/EIH、客户版方案生成
└── clean_ppt_shadows.py      阴影清理（历史污染修复工具）
```

资源目录（非脚本）：

```
assets/pointcloud_default/   3D 缺省点云图（pc_top / pc_slant_a / pc_slant_b，同型号典型成像）
assets/part_images/          工件/镜头示意图（2D 场景示意用）
images/                      相机产品图（按型号命名，database_updater 自动下载）
config/                      hardware_database.json 等数据文件
```

> `assets/pointcloud_default/` 是**缺省素材**，不是实拍证据：生成器用了它就标
> “同型号典型成像”，禁止当“实采”写进 PPT 或对外话术。

数据流（三条，按交付物选一条）：
1. **2D 客户版整册**：用户资料 → project_config.json（口径拍板）→ 选型
   （倍率窗口=相机×镜头联动）→ selection_result.json（validation_passed 必须 True）
   → `two_d_ppt.py` 12 页骨架生成 + 母版硬件页替换 → check_ppt_quality（FAIL=0 才可交付）
   → ppt_review 预览
2. **3D 客户版整册**：project_config_3d.json → `three_d_selector.py` →
   three_d_selection.json → `three_d_ppt.py` 12 页骨架生成 → 机检 → 预览
3. **仅模板硬件页替换**（内部/快速）：project_config.json → 选型 → `generate_ppt.py`
   母版数据替换 → 验收

> 三条产物默认同名同目录，后跑覆盖；弱模型只跑需要的那条（SKILL.md 执行卡已写明）。

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
| guidance_accuracy_mm | 厂商官方"视觉引导抓取精度"经验值（含抓取链路，scope=system） | 不是相机Z重复精度！无此字段才用 max(Z重复,VDI)+0.5×点距 自算，且必须标"估算" |
| data_confidence | 3D相机参数可信度 high/medium/low | low 只降权不够，必须排除出首选；纸面最优不可信数据不得当推荐结论 |
| design_target_mm | 3D误差预算分配基准=规格上限×80% | 不是规格上限！按上限分配=设计零余量，样机任一项超标即违约 |
| part_may_rotate | 产品可能任意旋转时FOV按外接圆校核 | 方形件45°外接宽度是边长1.414倍，按边长校核会漏判出视野 || 库=官网缓存 | 选中超龄条目主流程自动官网refresh（无变化续期/有变化入库重跑选型） | 官网才是数据源；联网失败WARN降级用库内值，不阻断交付 |
| strobe | 光源频闪能力三态：true=已核验支持 / false=明确不支持 / null=厂商资料未给、未核验 | 缺字段≠不支持！旧逻辑 `if not light.get('strobe')` 把未核验当不支持，飞拍查询恒空 |
| 接口带宽 | 需求帧率下数据率 ≤ 接口有效带宽（GigE≈110MB/s、USB3≈350、10GigE≈1100） | max_fps 是标称上限，不是工作点；5MP@24fps 黑白在 GigE 上约 121MB/s，跑不到满帧 |
| 快门类型 | 运动/飞拍必须全局快门；卷帘逐行曝光会拖影/果冻 | 静态工位卷帘可用，但提速后必须复评；缺字段=WARN 不得默认全局 |
| CheckResult.INFO | 厂家未给数据、无法判定的诚实披露（不计入PASS/WARN/FAIL，不阻断交付） | 不能因为没有厂家数据就沉默（沉默=假绿），也不能把"不知道"判成"不合格" |

## 运行时工作区约定（开发测试时也要遵守）

- 用户工作区（如 E:\Agent工作空间\视觉方案\）只有数据没有代码：用户资料图片、模板
  `视觉检测方案.pptx`（只读不写）、`project_config.json`（口径字段禁改）、`<PPT名>\` 交付物
- 交付物在 `<PPT名>\`（目录名与 PPT 同名）：方案PPT（验收通过自动只留最新版）、
  selection_result.json、acceptance_report.txt、ppt_review\ 预览三件套；中间失败版本由脚本自动清理
- **例外**：`project_config.json` 写了 `output_dir` 时（如 `output_贴片`），2D 整册产物
  落在该目录，而 selection 仍在 `<PPT名>\`——机检必须用 `--selection` 显式指定，
  否则型号白名单丢失会误判旧型号残留（v1.18.0 已修）
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
| 光源型号 `OPT RL-150-120-W` 进交付PPT（官网无此命名） | `light_selector.py` 把 6 条光源硬编码在代码里，型号由"品牌+尺寸+角度+颜色"拼造，且无 verified/官网链接；核验只查相机/镜头，CLI 连 light 都没传给 validator | 光源库改读 `hardware_database.json.light_sources`；库空/无匹配返回空型号并写"待选型（需扩库）"；新增光源可查证性+内径覆盖两项核验；CLI 补传 light；入库真实追光者/孚根型号 |
| 客户"偏差≤0.5mm"被填成 precision_requirement，需 144px 的荒谬结论 | 公差与设备精度口径混淆，精度链松 10 倍；原实现只提示不阻断，弱模型会忽略提示继续交付 | `_validate_params` 改为**硬阻断(exit 2)**：给出"公差/设备精度"原话问法 + `precision_basis_confirmed` 确认出口；禁止模型自行添加；SKILL.md 增加判别三问 |
| `--hardware_page 5` 越界后静默不生成PPT | 参数语义是"第N个硬件页"而非页码，越界只打印一行错误并 return None，上层继续验收 | 越界打印每个硬件页的真实页码；上层检查 None 并中止，main exit 非零 |
| 验收 FAIL 的 PPT 仍留在输出目录根 | `_run_acceptance` 只打印一句"处理前不要交付"，不改变文件位置，主流程仍 exit 0，弱模型看到文件就交付 | FAIL/验收异常 → PPT 移入 `<PPT名>\_rejected\`，`_run_acceptance` 返回 False，主流程 return None / exit 1 |
| 弱模型用 `--no_verify` 跳过验收，或从 `_rejected` 取文件改名交付 | 只靠文档提醒，无硬约束 | `--no_verify` 打印"产物不得作为交付依据"；SKILL.md 禁止事项第5条；汇报模板仅限退出码=0 |
| 追光者正确型号 `FL-R-10045-W` 被质检判"旧型号残留" | `FL-R-` 既是模板旧型号前缀，也是追光者真实型号前缀，前缀匹配无法区分 | 选中型号白名单放行；旧型号/历史假型号仍拦截；新增 `test_ppt_quality_contract.py` 锁边界 |
| 目录页 / 选型计算页被当成硬件展示页 | 目录里"硬件选型"是独立文本框（精确命中标题），计算页标题相同但无实物标注框 | 标题精确 + **文本框在页面顶部（<1.5in）** + (标注框≥2 或 含硬件参数词) 才判硬件页；展示页专属检查（光源类型/两页一致/相机图）只对带标注框的页执行。目录条目在正文区，加顶部约束后不再误判 |
| 3D 方案说明段落整段被 C4 判"断行 FAIL" | C4 只按单行估算宽度判定，正文段落天然是多行；3D 客户版一页 3~4 段全中，机检直接不可用 | 长正文（>20 字）且框高 ≥ 估算行数 × 字号 × 1.3 时豁免；短标注（≤20 字）与框高不足仍严格抓（v1.16.1） |
| `validate_selection` 在只填 `tolerance` 时 TypeError | `precision_requirement` 显式 null 时 `.get(k, 0)` 返回 None，`None <= 0` 直接崩 | `resolve_precision_mm()` 统一解析（优先设备精度，否则公差/10），四处共用；`--params` 用 selection 的 project_info 补齐视野 |
| MOD=500mm 的镜头在 WD=300mm 项目里"中选" | WD 没进配置模板、没进选型参数、没进核验；`distortion` 缺失时评分默认 1.0、显式 null 时崩溃 | `working_distance` 进配置模板；`lens_wd_status()` 单点判定；选型/核验两链共用同一口径；数据库补 `mod`/`wd_range`/`resolution_mp`；null 安全处理 |
| 客户型号 `MVL-KF7528M-12MP` 被"库里没有"排除；把锁紧螺钉说成微距专属 | 库被当成全集；凭印象给结构项定性，没查官网规格书 | 新增 `lens_audit.py` 库外核查工具 + `external_candidates` 留档；锁紧/接口/靶面等结构项一律以官网规格书为准，禁止凭印象断言 |
| 交付 PPT 写"实际视野 25.4mm"（薄透镜估算）| 库里 `magnification` 是单点值/估算值，选型拿它当任意 WD 都成立；MF7538 官方三点表 WD300 实际约 0.350x → 视野 24.1mm，余量≈0 | 新增 `wd_mag_table` + `magnification_at_wd()`（1/β=(WD−h)/f 拟合）；核验加"倍率依据"；视野靠 2% 容差过线记 WARN；本项目设计 WD 300→320（视野 26.3mm，余量 9.4%）|
| 精度链算成"公差÷10÷3"（0.5mm→16.7μm/px），并把中间值叫"设备精度" | 把"视觉直测公差带÷10"和"已分配误差÷3"当串联；行业是一步换算：基恩士 测量精度=10×像素精度、HSM 像素≤公差带1/10、POMEAS 测量≥5像素/特征 | 新增 `resolve_precision_budget()` + `precision_model.mode` 显式区分 system_budget/direct_measurement；核验加"精度口径"检查（默认1/10兜底=WARN）；本项目 0.5×20%÷3=33.3μm/px，PPT 精度文案改数据驱动 |
| 飞拍项目光源查询恒为空、核验必 FAIL | 库内 12 条光源全无 `strobe` 字段，`if not light.get('strobe')` 把"未核验"当"不支持"，先过滤再选型 | strobe 三态（true/false/null）：只硬排除 false；null 保留并 WARN 要求供应商确认；选型主流程不再提前 `strobe_pool` 过滤 |
| 5MP@24fps 相机在 GigE 上跑不到标称帧率 | 全 skill 无接口带宽校核，只查 `max_fps ≥ 1.5×节拍`；标称帧率≠工作帧率 | `camera_interface_status()` 按需求帧率算数据率；>80% WARN、>100% FAIL；选型/核验两链共用 |
| 运动/飞拍场景选中卷帘快门相机 | 快门类型只打印不参与选型；卷帘逐行曝光会拖影/果冻 | `is_moving_scene()` + `shutter_kind()`；选型链硬排除卷帘，核验层卷帘+运动=FAIL |
| 景深/解析力/衍射三项光学约束从未参与选型 | 景深只解析厂家字符串且需人工给高度波动；MTF 只打印；15 支镜头仅 8 支有景深字段 | `_check_optics_quality()`：厂家值优先、无值公式估算并标"估算"；无法判定记 INFO 而非沉默 |
| 选型器精度判据比预算模型松 3.3 倍（direct_measurement） | `select_cameras_for_fov`/`_match_lenses_for_camera` 仍用 `allowed_error ÷ pixel_factor`，预算模型已算过该步 | 两函数新增 `pixel_precision_max_mm` 入参，主流程原样下发；单点口径收口到预算模型 |
| "测量精度 0.5mm"被当整机公差再分 10%（实算 16.7μm/px，客户本意只需÷3=166.7） | 混淆"视觉指标"与"整机公差"：测量精度是视觉系统要保证的数字，不能再分配；旧防呆只认 `precision_requirement≥0.2` 就拦截，把合法指标也拦死 | 新增 `precision_basis=measurement_accuracy` 放行；文本入口识别"测量精度/检测精度/设备精度/重复精度"；`precision_requirement` 绝对优先于 `tolerance`（即使声明 model）；只写"精度0.5"仍 exit 2 问用户 |
| 文本"±0.5mm"解析后带宽只有 0.5mm（少一半） | `_extract_tolerance` 只填 `tolerance`，没填 `tolerance_type`，默认 unilateral 把双向公差当单向 | 命中 `±` 自动写 `tolerance_type=bilateral`（带宽2X）；config 模板/wizard 同步要求声明 |
| 默认分配 1/10 再÷3=公差÷30，比行业严 3 倍 | 行业常规是视觉占 1/3（×3像素≈÷9~10），旧默认把"保守"叠成了双重折扣 | `DEFAULT_PRECISION_MODEL.allocation_ratio` 0.1→0.3；核验/模板/wizard 文案统一 30%；config 显式 0.1~0.2 保留为严格档 |
| 示意图 320mm/220mm 标注线与实体脱节（客户退回） | 标注端点写死 1.72/4.67，与相机顶 1.40、工件面 4.55 无关；220mm 只有竖线没刻度；无任何机检覆盖；且 `build_ppt.py` 是每项目新生成，只改项目脚本换个工作区必复现 | 画法收敛到 skill 模块 `tools/ppt_diagram.py`：`add_dim_v()` 直接收实体 shape 自动读边界（刻度+界线+居中内置，端点传反/None 立即报错），项目 `build_ppt.py` 只 import 并在构建期 `self_check`；`check_ppt_quality` 新增 C8 机检：纯数字 mm 标注端点须与实体边界对齐、两端须有刻度，否则 WARN；SKILL.md 定为硬规则，禁止项目内自写标注函数 |
| 工作距离 320mm 从相机顶面起算（客户退回） | 物理定义错：WD 是镜头前端面→检测面，相机机身高度不计入；C8 只能查"贴没贴实体"，查不出"贴错实体" | 新增 `add_wd_dim()` 强制 `optic.bottom → target.top`（传入 `top_edge` 直接 TypeError，无法改回相机顶）；SKILL.md 写明相机与镜头必须独立成块、附正确/错误对照表；回归 4 条（镜头底/光源底/生成即过C8/禁止覆盖边） |
| 2D 12 页客户版已交付，SKILL.md 主路径仍指向模板替换（13 页） | 新生成器固化后未同步主入口；文档里"一条命令生成"与"整册生成"两处并存，弱模型只会读最短路径 | SKILL.md 顶部加「30 秒执行卡」；最短路径改为**按交付物三选一**表格；铁律 8：生成器上线必须同提交改文档 |
| 2D 生成器机检 FAIL 时退出码仍为 0 | `run_quality_check` 返回值没参与 `sys.exit`；3D 有、2D 漏 | `two_d_ppt.py` 改为 `return 0 if ok else 1` + `sys.exit(main())`；与 3D 对齐 |
| 正确的追光者光源被机检判"FL-R- 旧型号残留" | 机检只在 PPT 同目录找 selection；2D 的 `output_dir` 与 `<project_name>/` 分叉，型号白名单丢失，`FL-R-` 前缀误命中 | `ppt_layout.run_quality_check(pptx, selection=...)` 透传 `--selection`；2D/3D 都传真实路径 |
| 弱模型跑 12 页生成器时 selection 缺失即断链 | 生成器要求先手动跑选型，两步之间无强制，弱模型只跑第一条 | 两个生成器加 `auto_select()`：缺失时内部调 `--auto --dry-run` / `three_d_selector.py`；失败原样透出后停止，**不兜底填数字**（铁律 9） |
| `--text` 模式不落 config，弱模型无法从一句话需求走到 12 页客户版 | `generate_from_text` 只把 parsed_data 传给生成链，不落盘 | 解析成功即写 `project_config.json`（已存在不覆盖）；SKILL.md 改为 `--dry-run` 两步法 |
| 3D 配置传给 2D `--check-config` 被误判"精度口径偏大" | 2D 校验只认自己的字段，不认识 `installation`/误差预算，把 3D 的合法指标当口径错误 | `check_config_only` 先识别 3D 特征并指路 `three_d_ppt.py`（exit 2）；反向也拦（2D config 进 3D 生成器） |
| 弱模型把 `scene` 键名写错（`partFeature`）静默回落贴片文案 | `scene.update()` 不校验键名；`precision_chain` 格式错则直接崩 | `scene` 未知键打印可用键清单；`precision_chain` 校验三项+数字，报错给正确示例 |
| 弱模型无参数运行只看到"至少给 --config"不知下一步 | 报错只说缺什么，不说怎么给 | 补完整命令示例（含相对路径写法） |
| PowerShell 中文乱码被误认为脚本报错 | Windows 控制台编码与 UTF-8 输出不一致 | SKILL.md 注意事项：只看退出码与 `FAIL=` 数字，不因乱码改脚本/config |
| 弱模型可能改 skill 脚本"修 bug" | 只有"禁止在工作区写脚本"，没禁止改 skill 目录 | SKILL.md 禁止事项第 4 条：禁止修改 skill 目录任何 `.py`/`.md`，只能按对照表处置或报告 |
