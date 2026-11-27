# 更新日志

本 skill 的所有版本变动统一记录在此。格式参考 Keep a Changelog。

## [v1.17.0]（2026-11-27）
### 变更：输出目录改为与 PPT 同名，不再固定 `output`

> 触发：用户要求方案输出目录以 PPT 同名命名。此前固定 `output`/`output_3d`，
> 多项目产物混放、验收报告/预览图与 PPT 的对应关系靠记忆，交付时容易拿错版本。

- **`vision_proposal_generator.py`**：默认输出目录 = `<config 所在目录>/<PPT名>/`，
  PPT 文件名不再带 `%Y%m%d_%H%M%S` 时间戳（验收通过只留最新版，重复运行直接覆盖）；
  新增 `_safe_name()` 清洗 Windows 非法字符（`<>:"/\|?*` 与控制符），空名回落
  `视觉检测项目`，长度截断 80 字符。基准目录取 config 所在目录而非 cwd——AI 用绝对路径
  从任意目录调用很常见，产物必须跟着工作区走。
- **`three_d_selector.py`**：`--output` 默认值从 `./output` 改为
  `<config 所在目录>/<项目名>/`（取 `project_name`，缺省 `3D视觉引导抓取方案`；
  命令行链无 config 时退回 cwd），同样经 `_safe_name` 清洗。
- **`--output` 仍可显式指定**：老用法与测试脚本不受影响。
- **文档**：SKILL.md / AGENTS.md / README.md 中 `output\` 路径约定全部改为 `<PPT名>\`；
  示例命令去掉多余的 `--output`。
- **测试**：新增 3 条契约（3D 默认目录=项目名且不生成 `output`；`_safe_name` 非法字符/空名/
  中文符号保留；2D 端到端默认目录=PPT 名且 report/json 同目录），全量 277 条通过。

## [v1.16.1]（2026-11-27）
### 修复：PPT 机检两处误判（3D 客户版验收暴露）

> 触发：3D 客户版 PPT（14 页）跑 `check_ppt_quality.py` 时，目录页被当成硬件页，
> 说明段落整段被 C4 判为断行 FAIL——工具不修，3D 方案无法走同一套交付验收。

- **`is_hardware_slide`**：标题文本框必须位于页面顶部（<1.5in）才认。
  目录页的"硬件选型"条目在正文区（2.77in），此前因描述含"工作距离/视野"命中参数词被误判。
- **`check_overflow`（C4）**：长正文（>20 字）且框高 ≥ 估算行数 × 字号 × 1.3 时豁免，
  按正常多行排版处理；短标注（≤20 字）与框高不足仍严格抓断行/溢出。
- **测试**：新增 3 条 C4 契约（长正文高框放行 / 长正文矮框拦截 / 短标注仍拦截），全量 274 条通过。
- **SKILL.md**：3D 章节新增"3D 方案 PPT（客户版）"小节（数据源唯一、WD 标注、机检适用项、14 页骨架）。

## [v1.16.0]（2026-11-27）

### 新增：3D 视觉引导选型分支（误差预算 + 数据置信度）

> 触发：客户 300×300 产品、0.5mm 引导精度、ETH 安装、底部不平需引导夹爪角度、
> 传送带静止拍照、需换型。厂商推荐梅卡曼德 PRO M，需独立选型并对比。

- **新增 `tools/three_d_selector.py`**：
  - 输入产品尺寸/精度/口径/节拍/安装方式/换型数，输出 FOV 校核、点距、引导误差、候选排序、Markdown 方案
  - 误差预算按 **设计目标 = 要求×80%** 分配（不是按规格上限，避免设计零余量）
  - 厂商 `guidance_accuracy_mm` 优先；无则 `max(Z重复, VDI) + 0.5×点距` 估算并标注"待样件实测"
  - 工作点从**最佳工作距离**起搜（不是最近端），FOV 不够才向近端回退
  - `--part-may-rotate`：产品可能任意旋转时 FOV 按外接圆校核（300×300 → Ø424mm）
  - `--customer`：额外生成客户交付版方案（BOM/ETH标定/换型/验收计划/待确认清单）
  - 退出码 0/1/2：参数缺失或精度口径未声明直接 exit 2，禁止自行补口径
- **新增 `config_template_3d.json`**：3D 需求登记模板，含误差预算四项现场值、旋转包络字段
- **数据库新增 `three_d_cameras` 表（11 台）**：
  - 梅卡曼德 PRO S-V4D500M/700M、PRO M-V4D1200M、NANO-V4D550M
  - Zivid 2+ M60、Photoneo PhoXi M Gen3
  - 迁移科技 Epic Eye Pixel Pro / Laser M V3
  - Cognex 3D-A5060、图漾 PS800-E1 / VMD03-1230(C)
  - 每条含 `data_confidence` 与 `needs_vendor_confirmation`；参数全部来自官网/官方数据表
- **新增 `SKILL.md` 3D 章节**：何时走 3D、与 2D 的口径区别、七条硬规则、
  底部不平/6D 位姿风险、ETH 标定要点、3D 常见坑表
- **评分加入置信度因子**：low × 0.78 / medium × 0.92；**low 不得成为推荐首选**
- **测试**：新增 `test_3d_selection.py` 35 条（库 schema/FOV 数学/误差预算/厂商口径优先/
  参数校验/旋转包络/推荐规则/客户版/假设标注/注入），全量 271 条通过
- **本项目结论**：PRO M 官方引导精度 ±1.5mm 不满足 0.5mm；PRO S 系列 FOV 或精度至少一项不满足；
  梅卡曼德全线在本项目约束下无可行型号。候选池 PASS 4 台，Photoneo PhoXi M Gen3 与
  Zivid 2+ M60 并列首选（评分差 <3%），迁移 Laser M V3 因 VDI 数据存疑降为"待确认潜力候选"

## [v1.15.3]（2026-11-23）

### 修复：工作距离标注的物理语义错误（客户第二次退回）

> 触发：坐标已经贴到实体了，但客户指出 `320mm` 的起点在**相机顶面**——
> 工作距离是镜头前端面到检测面的距离，不该把相机机身高度算进去。

- **根因**：`add_dim_v` 只保证"端点落在某个实体边界"（C8 也只能查这个），
  无法表达"这个标注在物理上应该从哪条边量"。语义错误不会报任何 WARN。
- **修复**：`tools/ppt_diagram.py` 新增专用入口 `add_wd_dim()`：
  - 固定取 `optic.bottom → target.top`，调用方不指定边；
  - 试图用 `top_edge=` 覆盖会直接 `TypeError`，无法偷偷改回相机顶；
  - 文档字符串写明 WD 定义与本次事故。
- **布局联动**：光源下移 0.12in（2.62→2.74），避免 320mm 上端界线贴着光源顶
  造成误读；光源内部发光面改为 `LIGHT_BOX_Y + 0.04` 派生，不再硬编码 2.66。
- **文档**：`SKILL.md` 增加"物理语义"小节（正确/错误对照表），明确相机与镜头
  必须画成两个独立实体，工作距离一律用 `add_wd_dim`。
- **回归**：新增 4 条（镜头底=2.57 / 光源底=3.02 / 生成即过 C8 / 禁止覆盖边）。
- **验证**：成品 PPT 实测 320mm 顶端 2.57in（镜头底）、220mm 顶端 3.02in
  （光源底），QC FAIL=0 / WARN=0。

## [v1.15.2]（2026-11-23）

### 修复：标注画法模块化（跨项目复现问题）

> 触发：用户追问"build_ppt.py 换项目就会重新生成，只改它，换个工作区不就
> 又有这个绘制问题了？"——确认 skill 里没有 `build_ppt.py` 模板，项目脚本
> 每次都是新写的，只改项目等于没修。

- **根因**：正确画法只存在于文档和单个项目里，新项目由模型即兴手写标注线，
  手写坐标的问题 100% 复现。
- **修复**：新增 skill 内置模块 `tools/ppt_diagram.py`，提供 `add_dim_v()`：
  - 端点可直接传实体 shape（`top/height` 自动读取），从物理上消除写错坐标；
  - 传数值时只接受实体派生变量，`None` / 上下传反 立即 `ValueError`；
  - 内置两端刻度（0.20in）、尺寸界线（自动伸到实体边缘外侧）、文字居中。
- **接入**：项目 `build_ppt.py` 改为 `import ppt_diagram`，删除本地手写版；
  构建期调用 `self_check(slide)`，不合格直接 `SystemExit`，不等客户发现。
- **文档**：`SKILL.md` 改为硬规则——新建 `build_ppt.py` 必须用该模块，
  禁止项目内自写标注函数或手写标注线坐标。
- **顺带修正**：C8 报错坐标显示曾把 `Length`（int 子类）直接格式化，出现
  `y≈1280160.00in`；改为 `float(yy)/EMU`，WARN 文案同时给出修复指引。
- **回归**：新增 7 条模块契约（模块存在 / shape 边界读取 / 光源底面 /
  Length 单位 / 生成即满足 C8 / 端点传反报错 / None 报错）。

## [v1.15.1]（2026-11-23）

### 修复：示意图尺寸标注与实体对齐（客户退回）

> 触发：客户指出系统方案页 320mm/220mm 的标注线没有对齐实体——
> 320mm 竖线上端悬空、下端扎进工件，220mm 只有一条光秃竖线没有刻度。

- **根因**：标注端点写死坐标（1.72/4.67），与实体（相机顶 1.40、工件面 4.55）
  完全脱节；布局一改就错，且没有任何机检覆盖。
- **修复**：示意图实体坐标全部变量化（`CAM_TOP`/`LIGHT_BOT`/`WORK_TOP`），
  新增 `add_dim_v()` 统一画法（竖线 + 两端刻度 + 尺寸界线 + 文字纵向居中），
  调用处只准传实体变量。
- **机检**：`check_ppt_quality` 新增 **C8 尺寸标注对齐**——纯数字 mm 文本
  （`^\d+(\.\d+)?\s*mm$`）附近有竖直标注线时，检查两端刻度是否存在、
  端点是否与实体形状上/下边界对齐（容差 0.08in）；无竖线视为普通数据标注不检查。
- **回归**：新增 4 条（端点悬空 WARN / 缺刻度 WARN / 对齐放行 / 普通数据标注不误报）。

## [v1.15.0]（2026-11-22）

### 修复：精度口径语义与行业对齐（用户拍板规则）

> 触发：用户指出"客户说测量精度 0.5mm，就用 0.5mm 算；说 ±0.5mm 才用 ±0.5 算"，
> 并质疑"÷3 再叠加 10% 分配"是否比行业常规严。

#### 语义修正（会导致口径错 2~20 倍）

- **"测量精度 X"直接算**：`precision_requirement: X` + `precision_basis: "measurement_accuracy"`，
  像素当量 = X ÷ 3，**不再乘整机分配比例**。旧实现把它当整机公差按 1/10 再 ÷3，
  0.5mm 被算成 16.7μm/px，比客户本意严 10 倍。
- **"±X"带宽翻倍**：文本入口命中 `±` 时自动写 `tolerance_type: "bilateral"`（带宽 2X）。
  旧实现只填 `tolerance`，默认 unilateral 把带宽少算一半。
- **precision_requirement 绝对优先**：即使 config 声明了 `precision_model`，只要
  `precision_requirement` 存在就不再走 tolerance 分配。修复旧逻辑在 model 已声明时
  让 tolerance 压过 precision_requirement（日志说"精度优先"、预算却按公差算）的双链分裂。
- **防呆放行**：`precision_basis=measurement_accuracy` 的 0.5mm 不再被"疑似公差"拦截；
  只说"精度 0.5mm"（无限定词）仍 exit 2 要求用户确认。

#### 行业口径对齐

- **默认分配比例 1/10 → 3/10**：视觉占整机公差 1/3，再 ÷3 像素，等效"整机公差 ÷ 9"，
  与基恩士/HSM 的"像素当量 = 公差带 ÷ 10"同一量级。旧默认 ÷30 比行业严 3 倍，
  会把相机/镜头选贵一个档。
- `--check-config`、核验报告、config 模板、wizard 文案同步改为 30%。
- 新增 `precision_basis` 字段：`measurement_accuracy`（客户明确测量/检测精度）/
  `drawing_tolerance`（图纸公差备注）/ `null`（未说明，触发人工确认）。

#### 回归

- 新增 7 条：测量精度不分配、±公差带宽翻倍、precision_requirement 优先于已声明 model、
  防呆放行/拦截、默认 30% 口径、workflow exit code 放行。
- 全量 **218/218 通过**。

## [v1.14.0]（2026-11-21）

### 新增+修复：对照工控机器视觉选型规范补齐硬约束（2026-11-21）

> 触发：用户要求审查 skill 与工控行业选型规范是否有出入，并评估弱模型可用性。
> 审查发现 7 处规范缺口，其中 4 处会导致交付错误（P0），本轮全部修复并补回归。

#### P0：会导致交付错误的缺口

- **飞拍光源恒为空（真 bug）**：`select_light_source(is_fly_shooting=True)`
  用 `if not light.get('strobe')` 过滤，把"库内无 strobe 字段"当成"不支持频闪"；
  12 条光源全无该字段 → 飞拍项目必然空池 + 核验 FAIL。
  改为 **strobe 三态**：`true`=已核验支持（再比 `min_exposure_us`）；
  `false`=明确不支持（硬排除）；缺字段/`null`=未核验（保留并 WARN，
  要求供应商确认 μs 级频闪与最短脉宽）。核验对 `null` 给 WARNING 而非 FAIL，
  避免把"不知道"判成"不支持"。
- **接口带宽从不校核**：5MP×24.2fps 黑白在 GigE 上约 121MB/s，
  已超 1Gbps 有效带宽（约 110MB/s），相机跑不到标称帧率。
  新增 `camera_interface_status()`：按需求帧率（1.5/节拍）算
  `W×H×位深/8×fps`，>80%=WARN、>100%=FAIL、未知接口=INFO。
  选型链同步打印超带宽提示。
- **快门类型不参与选型**：卷帘快门相机（MV-CS200/CS120）在运动/飞拍场景
  会拖影/果冻。新增 `is_moving_scene()` + `shutter_kind()`：
  选型链对运动场景**硬排除卷帘机型**；核验层卷帘+运动=FAIL、
  静态场景卷帘=PASS（注明可后续提速复评）、缺字段=WARN。
- **景深/MTF/衍射不参与核验**：旧实现只在 `part_height_variation_mm`
  存在时解析厂家 `depth_of_field` 字符串，15 支镜头仅 8 支有该字段，
  选型阶段完全不用。新增 `_check_optics_quality()`：
  - 景深：厂家 `±X mm` 优先，无值按 `2·N·c·(1+β)/β²` 估算并标"估算"；
    景深 < 高度波动=FAIL；未给高度波动=INFO 待确认；无法估算=INFO。
  - 镜头解析力：MTF30 ≥ 相机奈奎斯特 `1000/(2×像元)`；低于=WARN，未给=INFO。
  - 衍射：艾里斑 `2.44·λ·F#` ≤3×像元；超过=WARN（收小光圈只会更差）。
  - 新增 `CheckResult.INFO`：只用于"厂家未给数据、无法判定"的诚实披露，
    不计入 PASS/WARN/FAIL、不阻断交付，但报告可见（禁止沉默=假绿）。

#### P1：选型链与核验链口径不一致

- `camera_selector.select_cameras_for_fov()` / `lens_selector.select_lenses_for_camera()`
  新增 `pixel_precision_max_mm` 入参，`vision_proposal_generator._select_candidates()`
  把预算模型的像素当量上限原样下发。此前 `_match_lenses_for_camera` 仍用
  `required_precision_mm / pixel_per_precision`，在 `direct_measurement` 模式下
  会把"公差带÷10"再按 ÷3 算，选型松 3.3 倍。
- `calculate_light_working_distance()` 的 `camera_wd` 参数此前收了却不用，
  与 SKILL.md 声称的"光源 WD < 镜头 WD"不一致；现按 `max(20, 镜头WD-15)`
  封顶并返回 `capped_by_camera` / `camera_wd_cap_mm`。
- `_check_fly_shooting` 曝光时间优先用 `params['pixel_precision_max_mm']`，
  不再从 allowed_error 二次除亚像素因子。
- `tolerance_to_precision()` 标记废弃（两套口径无法表达，bilateral 语义与
  预算模型矛盾），仅保留旧调用兼容，新代码禁止调用。

#### P2：弱模型可用性

- 新增 `--check-config <json>`：只校验参数（不选型/不生成PPT），几秒出结论，
  退出码 0=合法 / 2=需修正。解决"跑 30 秒生成才发现口径填错"。
- 新增 `--dry-run`：只跑选型+核验并保存 `selection_result.json`，不生成PPT；
  `--config` / `--text` / `--wizard` 均支持，`--files` 链显式提示忽略。
- `--help` epilog 重写为"三种入口 + 退出码表 + 硬规则"，`--version` 输出
  `视觉硬件选型 skill v1.14.0`。
- `config_template.json` 新增 `is_fly_shooting` / `conveyor_speed` /
  `part_height_variation_mm` 三个字段及字段说明（此前弱模型不知道要填）。

#### 文档与测试

- `SKILL.md`：第3步加带宽/快门判据，第4步加光学质量三件套，第5步加频闪三态，
  第6步核验表加 5 行；最短路径新增"第0步 配置自检"。
- 新增 `test_industry_compliance.py`（28 条）：光学估算函数/带宽/快门/
  频闪三态/选型链口径一致；全量 **211/211 通过**。
- 本项目复跑：MV-CS050-10GM + MVL-MF7538M-ML + FL-R-7060-W 不变，
  核验 28 PASS + 2 INFO（景深估算 ±0.168mm 未给高度波动、MF7538 无 MTF30），
  0 WARN / 0 FAIL。

## [v1.13.0]

### 修复：精度口径被叠加，比行业常规严 3 倍（2026-11-21）

- **发现**：客户给"贴合精度 ≤0.5mm"，脚本算成 `0.5 ÷ 10 ÷ 3 = 16.7μm/px`，
  并把中间值 0.05mm 写成"设备精度"。核对基恩士官网、HSM University、
  POMEAS TR-001 后确认：业界是**一步换算**，不是两段叠加——
  - 基恩士：尺寸测量 `测量精度 = 10 × 像素精度`；外观 `检测精度 = 4 × 像素精度`；
    另一处口径：公差判定阈值 = ±5 像素（总带宽 10 像素）
  - HSM University：计量类 `像素当量 ≤ 公差带 1/10`
  - POMEAS TR-001：检测 ≥3 像素/特征，测量 ≥5 像素/特征
  - 旧实现把"公差带÷10"（视觉直测口径）和"允许误差÷3"（亚像素判据）
    连用，等价 `公差÷30`，比行业常规严 3 倍；且"设备精度"命名会被读成整机精度。
- **新增 `resolve_precision_budget()`**（`precision_calculator.py`）：
  用 `precision_model.mode` 显式区分两种口径——
  - `system_budget`：整机公差带 × `allocation_ratio`（1/10~1/3）
    = 视觉允许误差，再 ÷ `pixel_factor`（默认 3）
  - `direct_measurement`：公差带 ÷ `direct_factor`（测量 10 / 外观 4 / 定位 6）
  另支持 `tolerance_type`（unilateral/bilateral/total，双向自动×2）、
  `pixel_precision`（用户直给像素当量）、`precision_requirement`（已确认视觉误差）。
- **选型链**：`_validate_params` 的 tolerance 分支改走统一预算，输出
  `precision_basis_text`；`_calculate_field_of_view` 直接用预算的像素当量，
  不再二次除；"像素上限异常宽松"警告只在尺寸测量场景触发。
- **核验链**：新增"精度口径"检查（声明 model=PASS，默认 1/10 兜底=WARN）；
  "精度链"改用预算的 `pixel_precision_max_um`，报告写明分配比例。
- **本项目决策**：`precision_model = system_budget + positioning + unilateral
  + allocation_ratio 0.2 + pixel_factor 3`
  → 整机公差 0.5mm × 视觉 20% = 允许误差 100μm ÷ 3 = **33.3μm/px**
  （原 16.7μm）。所需像素 24mm÷33.3μm = **720px**（原 1440px）；
  MF7538 实际 10.73μm，余量 **3.1x**（原 1.55x）。相机选型结论不变。
- **PPT**：第 7 页"① 精度换算"改为数据驱动，不再写死 ÷10÷3
  （版面短式 `±0.5mm→带宽1mm×10%=100μm÷3=33.3μm/px`，完整推导进演讲者备注）；
  第 6/7 页"相机精度/像素精度"统一改为"像素当量"（避免被读成精度指标）；
  封面公差随 `tolerance_type` 显示 `±0.5 mm`；
  第 9 页补注解：视觉测量链 RSS ±0.062mm 在允许误差 100μm 内（1.6x），
  机器人重复定位/吸嘴属执行链，由整机公差剩余份额覆盖。
  底部注说明"像素需求仅 720px，选 500 万像素是为孔边缘多像素覆盖与短曝光余量"。
- **用例**：新增 14 条（预算模型 9 + 核验口径 3 + 模板防绕过 2），
  全量 **183/183 通过**。

## [Unreleased]（v1.12.2）

### 新增+修复：工作距离成为选型硬约束、库外型号核查留档（2026-11-20）

#### 第二轮：WD 决定倍率，单点倍率不能冒充全行程（同日补）

- **发现**：调研 75mm 候选时核对海康官网，MF7538 给的是一张三点表
  （250mm/0.46x、400mm/0.24x、550mm/0.16x），而库里 `magnification=0.333`
  是薄透镜估算。按官方三点拟合 `1/β=(WD−h)/f`，WD300 实际约 **0.350x**，
  视野 **24.1mm**——相对 24mm 需求余量≈0，而旧交付物写的是 25.4mm。
  这说明"WD 进选型"只解决了"能否合焦"，没解决"合焦后倍率/视野是多少"。
- **数据库**：新增 `wd_mag_table`（MF7538 三点、M7528-MP 五点含接圈态）
  + `wd_mag_table_basis`；修正 MF7538 的 note（删除薄透镜推断句）。
- **选型链**：新增 `magnification_at_wd()`，按 `1/β=(WD−h)/f` 对厂家表做
  最小二乘拟合，表内插值、表外标记 extrapolated；无表才用薄透镜估算。
  结果条目带 `magnification_at_wd` / `magnification_source`。
- **核验链**：新增"倍率依据"检查（表插值=PASS，估算/单点/外推=WARN）；
  精度链、视野覆盖、倍率窗口统一改用 `effective_magnification()`；
  视野靠 2% 容差过线（未达标称值）改为 WARN 并给出"WD 上调 20~30mm"建议；
  光源 WD 检查改用项目声明 WD（此前打印的是镜头标称值）。
- **本项目决策**：设计 WD 300→**320mm**（β≈0.322x、视野 26.3×22.0mm、
  余量 9.4%、像素精度 10.73μm、余量 1.55x）。WD300 属零余量，不交付。
- **第二轮库外调研**（写入 `external_candidates`）：
  - Kowa `LM75JC`：2/3"、75mm、F2.5~F22、MOD 1200mm、畸变 -0.1%；
    官方接圈表 20mm→285mm/0.34x，WD300 插值约 0.326x/25.9mm → usable_with_risk；
  - Kowa `LM75HC`：1"、5MP、F1.8~F16、MOD 1000mm、畸变 -0.2%；
    官方接圈表 10mm→389mm/0.21x、20mm→251mm/0.34x，WD300 约 0.29x → usable_with_risk；
  - Fujinon `HF75HA-1B`：MOD 1100mm、MOD 处仅 0.077x、无接圈表 → rejected。
  - 结论：75mm 级 FA 镜头原生 MOD 普遍 0.5~1.2m，只有 MF7538（微距）与
    M7528-MP 原生覆盖 300mm；Kowa 两只要加 13~18mm 接圈（厂家表支持）。
- **用例**：新增 10 条（倍率表拟合 6 + 视野余量 3 + 数据完整性 1），
  全量 **169/169 通过**。

### 背景与第一轮修复

- **触发**：用户质疑"MVEL-KF7528M-12MP 为什么不行"，并指出两处流程问题：
  ①锁紧螺钉不是微距专属；②"库里没有"不能作为排除理由，必须去官网查。
- **根因（比型号本身严重）**：
  - `project_config.json` 没有 `working_distance` 字段，WD 从未进入配置；
  - `select_lenses_for_camera` 没有 WD 参数，`_match_lenses_for_camera`
    只比倍率/视野/靶面 → MOD=500mm 的镜头在 WD=300mm 项目里也能"中选"；
  - `validate_selection` 同样不查 MOD → 两条链一起漏；
  - 数据库没有 `mod`/`wd_range`，`distortion` 部分缺失，缺值时评分默认 1.0；
  - `distortion` 键存在但值为 `null` 时 `None <= 0.05` 直接抛 TypeError。
- **数据库 v1.1.0**：
  - 15 支镜头全部补 `mod` / `wd_range` / `resolution_mp`，缺值显式 `null`；
  - 新增 `M7528-MP`（Computar，2/3"，75mm，原生 MOD 300mm，畸变 0.4%）；
  - 新增 `external_candidates` 留档：`MVL-KF7528M-12MP`（rejected，
    MOD 500>300）、`M7528-MPW3`（rejected，停产且 MOD 400）；
  - `_metadata.notes` 明确"禁止以库内无此型号代替官网核查结论"。
- **选型链**：
  - `lens_wd_status()` 单点判定（ok/too_close/too_far/unknown）；
  - `select_lenses_for_camera(required_working_distance=...)` 传入 WD，
    `_match_lenses_for_camera` 在倍率检查前硬过滤，并记录排除型号；
  - 无匹配时输出 `[镜头无匹配·WD约束]` 根因，列出最接近的 3 款及能力区间；
  - 结果条目带 `wd_status` / `wd_capability` / `wd_requirement`；
  - `distortion`/`telecentricity` 为 `null` 时按中性 1.0 处理，不再崩溃。
- **配置链**：`config_template.json` 新增 `working_distance` 字段与说明；
  `vision_proposal_generator` 把 `params['working_distance']` 传入选型器。
- **核验链**：`validate_selection._check_working_distance()` 复查同一口径，
  超 MOD = FAIL；缺 `mod` = WARN；配置未声明 WD 时用镜头标称值兜底并降级 WARN。
- **新增工具** `tools/lens_audit.py`：库内型号直接判定，库外型号必须补
  `--mod/--mag/--distortion/--sensor-support` 才给结论；缺字段拒绝判定；
  退出码 0/1/2 分别对应 usable / usable_with_risk / rejected。
- **关键认知**：工作距离-倍率关系**不能用薄透镜公式跨型号推算**。
  Computar M7528-MP 官方表 WD=300mm→0.214x，薄透镜估算却是 0.333x；
  同标 75mm 的镜头主面位置不同，差 50%。必须用厂家 WD-倍率表。
- **用例**：新增 15 条（WD 契约 7 + 核验 4 + 数据完整性 4），
  全量 **159/159 通过**（16.5s）。

## [Unreleased]（v1.12.1）

### 修复：硬件页识别误伤目录页 / 计算页（2026-11-20）

- **背景**：用 11 页交付版跑 `check_ppt_quality` 时，硬件页被识别成 `[2,6,7]`：
  - 目录页（p2）里"03"和"硬件选型"是两个独立文本框，标题精确命中；
  - 计算页（p7）标题同为"硬件选型"，但内容是参数表格，没有实物标注框；
  - 结果：误报"未识别到光源类型标注""未发现产品图片"，噪音掩盖真实问题。
- **分级判定**：
  - `is_hardware_slide`：标题精确等于"硬件选型"等 **且**（有 ≥2 个硬件标注框
    **或** 含分辨率/像素/工作距离/视野等参数词）→ 目录页排除，计算页保留；
  - 新增 `has_hw_labels`：只有带 相机/镜头/环形光/物料 标注框的展示页才做
    C2 光源类型一致、C3 两页参数一致、C7 相机图检查；计算页只参与
    C1 旧型号残留与 C4 溢出检查（这两项对它同样有效）。
- **验证**：真实交付 PPT 硬件页识别为 `[6,7]`、FAIL=0；新增 3 条边界用例，
  全量 144/144 通过。

### 修复：`validate_selection` 在"只给公差"时崩溃（2026-11-20）

- **症状**：`python validate_selection.py --selection ... --params project_config.json`
  直接 `TypeError: '<=' not supported between instances of 'NoneType' and 'int'`。
  原因：`precision_requirement` 显式为 `null`（正确口径是只填 `tolerance`）时，
  `.get('precision_requirement', 0)` 返回 `None`，三处比较全部炸掉。
- **修复**：新增 `resolve_precision_mm()` 统一口径解析（优先
  `precision_requirement`，否则 `tolerance/10` 推导），`_check_precision_chain`、
  `_check_magnification_window`、飞拍精度、远心必要性四处共用；
  `--params` 模式还会用 `selection_result.project_info` 补齐视野等缺失字段，
  避免 CLI 单独核验时视野检查被静默跳过。
- **效果**：贴片方案核验从"崩溃"变为 22 PASS / 0 WARN / 0 FAIL。
- **用例**：`TestValidateToleranceOnly`（公差口径不崩且 PASS、两个口径都缺
  必须明确 FAIL 而非崩溃）。

## [Unreleased]（v1.12.0）

### 修复+新增：光源防幻觉、品牌优先级与角度档位、公差口径复核（2026-11-20）

- **背景**：贴片方案交付后发现 PPT 里的光源 `OPT RL-150-120-W` 在 OPT 官网
  并不存在——`light_selector.py` 把 6 条光源硬编码在代码里，型号由"品牌+尺寸+
  角度+颜色"拼造，且无 verified/官网链接；核验只查相机/镜头，CLI 连 light 都
  没传给 validator，于是"19 项 PASS、0 警告"的报告带着假型号进了交付物。
- **光源唯一数据源**：删除 `LIGHT_SOURCE_DATABASE`，`light_selector` 改读
  `config/hardware_database.json.light_sources`，并清掉显式硬件分支里
  `{'brand':'OPT','model':'RL-100-90-W'}` 的默认值（无光源则按需求自动选）；
  库空/无匹配返回空型号 + `needs_expansion`，PPT 写"待选型（需扩库）"，
  **禁止拼造型号兜底**（删除 `_recommend_light_source` 中 `RL-100-90-W` 的兜底）。
- **核验补两项**：`光源可查证性`（verified + verification_url；库内查无型号
  提示疑似编造）、`光源内径覆盖`（内径 ≥ 视野对角线×1.1；缺内径=WARNING 待
  核验）。`validate_selection.py --selection` 现在会把 light_source 一起核验。
- **品牌优先级**（用户指定）：默认 `追光者 > 孚根 > OPT > CCS`，逐层降级，
  首层有合适型号不降级；config 可用 `light_brand_priority` 覆盖。
- **角度档位**（用户指定，环光必须区分高/低角度）：定位/测量/孔中心/贴装引导
  → 高角度 60~90°（孔壁阴影短、边缘位置真实）；表面划痕/纹理/凹凸 → 低角度
  10~30°（掠射增强凹凸对比）；通用 → 45°。`light_angle` 可强制指定。
- **口径复核（硬阻断）**：`precision_requirement ≥ 0.2mm` 且定位/贴装类时
  **直接中止(exit 2)**，输出"是图纸公差还是设备检测精度"的原话问法。此前只打印
  提示，弱模型会忽略提示继续交付低配方案（0.5mm 被算成 144px 的荒谬结论）。
  用户确认非公差后填 `precision_basis_confirmed: true` 放行，**禁止模型自行添加**。
- **验收隔离（防误交付）**：规则自查 FAIL 或验收脚本异常时，PPT 自动移入
  `output\_rejected\`，`_run_acceptance` 返回 False，主流程 return None / exit 1。
  此前 FAIL 只打印"处理前不要交付"，PPT 仍留在 output 根目录，弱模型看到文件就交付。
- **质检白名单误杀修复**：追光者真实型号以 `FL-R-` 开头，与"旧型号残留"触发词
  重叠，正确交付会被 `check_ppt_quality` 判 FAIL（本轮实测复现）。现把本次选中的
  相机/镜头/光源型号作为白名单传入；旧型号与历史假型号（`RL-150-120-W`、
  `RL-100-90-W`、`OPT-RI15030-W` 等）仍照常拦截。
- **靶面反推**：SKILL.md 补"工作距离/镜头被机械结构锁死时先反推最小靶面，
  再选相机"分支（24mm×0.333=8.0mm → 必须 2/3"）。
- **`--hardware_page` 越界**：打印每个硬件页的真实页码并明确失败；上层检查
  `generate_ppt` 返回 None 后中止，不再"跑完没 PPT"；不产出半成品、不进入验收。
- **硬件库**：入库追光者 FL-R 高角度 6 款 + 低角度 4 款（官网参数表逐项抄录
  外径/内径/角度/功率/重量，verified=true + 官网链接）；孚根 FG-DR 2 款仅有
  型号页信息（内径/功率/WD 缺失），verified=false 待厂商确认。
- **测试**：新增 37 条回归/注入用例（分层冒烟/数据完整性/文档契约/质检判定边界/
  工作流退出码与幂等），加上光源与口径相关用例，全量 139/139 通过、0 跳过、26.3s。
  分层入口见 `视觉选型测试/SKILL.md`（`--layer smoke|data|doc|core|ppt|workflow`）。

### 元数据：frontmatter `name` 改 ASCII slug（DSH 接入，2026-10-22）

- 仅改 SKILL.md frontmatter 的 `name`：`视觉硬件选型` → `vision-hardware-selection`（1 行）；目录名/正文/脚本/资产零改动，未升版
- 原因：DSH 加载器硬校验 `SKILL_NAME = /^[a-z0-9]+(-[a-z0-9]+)*$/`，中文名被静默丢弃（不可调用）
- 影响：DSH 内本 skill 调用名改为 `vision-hardware-selection`；目录名不变，脚本内路径引用不受影响

### 修复：fetch 通道3（浏览器接管自动执行）4处链路断裂（v1.11.2）

- **背景**：用户反馈"代理浏览器不完美"，评估 Selenium 接入时实查代码发现
  通道3（AI浏览器接管自动兜底）自上线以来从未成功过——4处缺陷叠加使其
  形同虚设，fetch 永远落到人工SOP。结论：不接入 Selenium（与通道3的
  Playwright 同层重复且引入驱动版本耦合），修通既有通道3即可
- **4处缺陷与修复**（`database_updater.py` + `browser_fetch.py`）：
  1. 子进程参数错位：传 `[url, model]` 而 browser_fetch CLI 约定
     `<型号> [品牌]`——url 被当型号搜索必然失败；改为
     `[型号, 品牌, '--headless']`，触发条件同步改为按 `--model` 而非 `--url`
  2. 输出协议不匹配：只认 `页面已保存到:`，browser_fetch 实际输出
     `文件路径:`——HTML 路径永远解析不到；改为双标记兼容解析，
     browser_fetch 侧也补打印 `页面已保存到:` 行（双向兼容）
  3. `timeout=60` 太短：browser_fetch 含模拟人工随机延迟+多次 networkidle
     等待，60s 必超时；放宽到 240s，并显式 `encoding='utf-8'`
     （防 GBK 控制台解码崩溃）
  4. AttributeError：调用不存在的 `_html_to_plain`（模块内只有
     `html_to_plain`）——即使前三关全过，最后一步也崩；已改正
- **测试**：新增 `视觉选型测试/tests/test_channel3.py`（5用例，全离线
  mock，不碰真实库与网络）：参数顺序契约、timeout≥180s、双协议解析、
  HTML→提取→草稿全链路无 AttributeError、子进程失败诚实降级 exit=2
- **验证**：全量 80/80 通过（原75 + 新增5），0失败 0跳过

## [Unreleased]（v1.11.1）

### 修复：全链逻辑审查 12 项

- **背景**：用户要求检查 skill 脚本逻辑 bug；逐文件通读 + 执行复现确认，
  修完跑测试套件（75 用例 73 过 2 跳 0 失败，含本次新增 17 用例）
- **崩溃类**：
  - `vision_proposal_generator.py` files 链无模板分支引用未定义的 `result_json`
    → NameError 崩溃（已复现）；`_save_selection_result` 改为返回落盘路径并接住
  - `validate_selection.py` `_check_performance_margin` 在 `cycle_time: null`
    时 `None > 0` 直接 TypeError（已复现）；缺省改 3，各核验的 k 取值同步防 null
  - `_calculate_field_of_view` 对字符串型 `field_of_view`（如 `"60x40"`）
    穿透全部分支误报【内部错误】；与 `field_of_view_input` 同规则解析
- **飞拍链三处断裂**（飞拍项目此前恒 FAIL 或误选）：
  - `light_selector.select_light_source` 的类型过滤把唯一频闪光源提前滤空
    （默认 `light_type='环形光'`）；飞拍时频闪免于类型过滤
  - 曝光上下限检查方向反了：系统上限比光源 max 宽松是正常余量，
    仅当系统上限短于光源最短时才过滤（`validate_selection` 同改）
  - `_recommend_light_source` 忽略 `is_fly_shooting` 且丢弃 strobe 三字段，
    飞拍随机拿普通环形光→核验必 FAIL；改为频闪池优先 + 透传 strobe 标记，
    与 `select_light_source` 取同 WD 容差（0.8/1.2），类型标签去重
    （`LED频闪光源光源` → `LED频闪光源`）
  - `parse_user_data.py` 飞拍关键词用子串 `in` 匹配：正则 `fly.*shot`
    永远命中不了且大小写敏感；改 `re.search(..., IGNORECASE)`
- **数值类**：
  - `camera_selector.py` 余量比只算宽轴，高向受限时虚高（实例虚高约 8 倍）；
    改取双轴最大值；两处 `int(x+0.999)` 改 `math.ceil`
    （小数部分 <0.001 时少进一位），`precision_calculator.required_pixels` 同改
  - `recommend_precision_from_tolerance` 的 conservative/relaxed 写反
    （保守 ×1.5 更松）；对调为 ×0.7 / ×1.5
  - `calculate_max_exposure_time` 对像素精度 ≤0 返回 0μs 无意义结果；改抛错
  - 旧接口 `lens_selector.select_lenses` 传整精度不除亚像素因子，
    比主流程宽松 3 倍（0.3x 物方 11.5μm＞上限 10μm 旧接口放行）；
    新增 `pixel_per_precision` 参数（默认 3.0）并对齐主链
  - `_perform_selection` 标准口径重试公式 `ppm/3` 实为精度/(k旧×3)，
    k旧≠1 时越算越严；改精度/3 并同步 `required_pixels`
- **链路一致性**：
  - config 显式硬件分支跳过核验（`validation_passed` 恒 False，
    无效硬件照生成 PPT）；补核验 + FAIL 中止 + 选型摘要（显式硬件只核验不换型）
  - `main` 在选型无解/核验 FAIL（返回 None）时仍 exit 0；改非零退出
- **控制台编码崩溃**（端到端自包含测试暴露）：
  - `check_ppt_quality.py` 先 `print(report)` 再写 `--out` 文件；
    gbk 控制台遇到 ✓/✗ 直接 UnicodeEncodeError 崩溃，报告没落盘、
    主流程验收误报"存在FAIL项"；改先落盘再打印，打印失败降级为 PASS/FAIL 纯文本
- **测试**：视觉选型测试套件新增 17 用例（飞拍解析 3/数值 3/相机轴 1/
  旧口径 1/核验防崩 1/飞拍光源链 5/显式硬件 2/字符串视野 1），全绿；
  另将 workspace 门控的 2 个端到端用例改写为自包含（临时目录现场合成
  config＋最小硬件模板），任何环境实跑不跳过

### 新功能：FA镜头入库范式 + "用户指定相机"反推口径用法（v1.10.0）

- **背景**：实际项目（85×15mm 零件、视野 128×22.5mm、节拍 3件/秒不停线、
  客户无精度要求、用户拍板 2000 万像素相机）暴露两个库/用法缺口：
  ① 大视野低倍率（0.103x）场景库内只有远心镜头（最低 0.259x），必然无解，
  正确选型是普通 FA 镜头；② 用户直接指定相机时脚本无"指定型号"参数，
  --auto 会按评分选更大相机
- **FA 镜头入库范式**（hardware_database.json，数据层无代码改动）：
  库内首颗 FA 镜头——海康 KF-P 系列 MVL-KF1624M-25MP（16mm F2.4、1.2" 像圆、
  2500 万分辨率、C 口，官网 API 查证 id=12857 已发布）。FA 镜头可调焦、
  倍率/WD 不固定，入库约定：**存本方案设计工作点**（β=靶面宽/视野宽=0.1026x，
  WD=f/β=16/0.1026≈156mm），`focal_length` 记录焦距，`note` 字段说明
  "换视野/相机须重算工作点"。选型链（倍率窗口/像圆/卡口/光源WD约束）零改动
  直接兼容
- **"用户指定相机"用法固化**（SKILL.md 口径决策补充，无代码改动）：客户无
  精度要求、用户拍板相机型号时——用 `pixel_precision` 反推口径：
  基准值=视野长边/相机水平像素，再放宽使余量比>1.3（评分进入"最佳区间"，
  指定相机综合分胜出且精度链核验余量达标）。本次基准 128/5472=0.0234 →
  取 0.031，MV-CS200-10GM 以 205 分中选，精度链余量 1.33x
- **大视野远心短路判定**（lens_selector.py `select_lenses_for_camera`）：
  测量场景分层前先做物理可行性预判——倍率窗口上限 < 库内远心最低倍率
  （数据驱动，不写死阈值；扩库小倍率远心后自动让位）时，远心层注定为空
  （大视野=低倍率，物方远心前组口径须≥视野宽，物理/成本不可行），跳过
  空搜索直接回退普通镜头并输出明确原因；回退命中仍带 telecentric_fallback
  标记，核验 WARNING 链不变
- **测试**：视觉选型测试套件新增 2 用例（大视野短路必须跳过远心层并带
  fallback 标记 / 小视野注入防误伤——短路不得架空远心优先策略），
  全量 58 用例绿；真实项目重跑日志确认短路文案生效
- **验证**：全量 58 用例绿；实际项目出方案 FAIL=0（PPT/selection_result/
  验收报告齐）；核验仅 1 个预期 WARNING（测量场景回退 FA 镜头的透视误差
  提示，符合远心优先分层设计）

### 新功能：尺寸测量远心优先分层选型 + 库保鲜官网闭环（v1.9.0）

- **背景**：用户明确两条策略——① 尺寸测量优先远心镜头，库内远心无匹配时
  回退普通镜头（不再硬卡类型导致无解）；② 数据以官网为准，库=缓存：
  新鲜直接用，超龄必须官网查证后更新库再用于选型
- **远心优先分层**（lens_selector.py）：
  - `select_lenses_for_camera` 新增 `prefer_telecentric` 参数：测量场景先只搜
    远心层（type 含"远心"，兼容物方/双远心/百万像素远心），命中即返回并标记
    `telecentric_preferred`；无匹配自动回退普通镜头层，命中标记
    `telecentric_fallback`；倍率窗口无解时提前返回不做无意义分层
  - 旧接口 `select_lenses` 的"精度≤0.01 强制远心（精确匹配'物方远心镜头'）"
    同步改为远心优先+回退（原逻辑会漏掉双远心/百万像素远心两类）
  - 回退方案不 FAIL 拦死：透视误差风险由核验 WARNING 醒目提示
    （建议扩库远心+向用户说明），交用户拍板
- **测量场景判定单点化**（precision_calculator.py `is_measurement_scene`）：
  detection_type 含测量关键词 / application=measurement / 精度≤0.01mm 三条件
  之一；选型分层与核验判定共用同一函数，杜绝两链条件漂移（历史事故模式）
- **detection_type 解析**（parse_user_data.py）：--text 新增
  `_extract_detection_type`（尺寸测量/外径测量/位置度测量等 17 个关键词，
  "检测区域"类几何描述不误伤）；config_template 新增 `detection_type` 字段；
  selection_result.json 的 project_info 落盘该字段可追溯
- **库保鲜闭环**（vision_proposal_generator.py `_refresh_selection_fresh`）：
  files/config 两链在选定方案后、核验前检查选中相机/镜头的新鲜度——
  超龄（>180天）条目自动走 `cmd_refresh`（apply 模式，三级通道官网查证）：
  无变化自动续期时间戳；有变化自动 apply 入库（verified 回退 false 待人工
  复核）并用新参数重跑一次选型；联网失败诚实 WARN 降级用库内值继续不阻断
- **核验**（validate_selection.py）：`_check_telecentric_necessity` 改用
  `is_measurement_scene` 单点判定；新增回退方案专属文案（"库内无匹配远心
  已回退普通镜头"+透视误差风险建议）
- **测试**：视觉选型测试套件新增 10 用例（场景判定4/文本解析2/分层行为3含
  注入"全层无匹配必须空手而归"/核验文案2），单文件 17/17 绿；全量 56 用例
  54 过 2 失败——2 失败为工作区 config 当日被改为 85x15+精度0.1（倍率窗口
  0.07~0.13x 低于库内最低 0.259x，库内无普通镜头可回退），stash 基线复现
  一致，与本次改动无关；该场景正确走缺口报告扩库指引

### 修复：用户指定像素精度时弱模型思考死循环（v1.8.1）
- **根因**：脚本链路没有"像素级口径"入口——用户明说"像素精度X mm/pixel"时，
  ① --text 解析的 `_extract_precision` 正则会把"像素精度：0.01mm"误抓成设备精度
  `precision_requirement`（keywords 表里的像素精度正则从未被使用），再被 ÷3 成
  异常严格的口径 → 选型无解；② config 无 pixel_precision 字段，SKILL.md 写了
  "按像素级口径处理"但脚本不支持，弱模型无合法路径；③ 无解诊断只有"口径过松
  (>20μm)"一个方向，没有"口径过严疑似像素精度被当设备精度"的反向提示 →
  弱模型只能反复"重新考虑/调参重试"死循环
- **修复**：
  - parse_user_data.py：新增 `_extract_pixel_precision`（"像素精度X mm/pixel"、
    "X mm/pixel"两种写法，先于设备精度提取）；`_extract_precision` 加 `(?<!像素)`
    负向后行断言，设备精度与像素精度两口径各走各路
  - vision_proposal_generator.py `_validate_params`：支持 config 字段
    `pixel_precision`（mm/pixel），等效设备精度=pixel_precision×pixel_per_precision
    后走原设备精度链（下游零改动）；与 precision_requirement 同给时警告冲突并采用
    像素级口径；【缺少精度口径】指引更新为三选一
  - `_perform_selection` 无解诊断新增反向口径复核：像素精度上限<5μm/pixel 异常
    严格且非像素级口径来源时，明确指引"把值改填 pixel_precision 字段"，
    禁止调 pixel_per_precision 凑解
  - config_template.json 决策表更新（像素级口径列为优先级1）+ 新增
    `pixel_precision` 字段；SKILL.md 口径三选一/单位铁律/防死循环铁律同步更新
- **测试**：视觉选型测试套件新增 5 用例（文本解析3：像素精度带/不带 /pixel
  后缀不被误抓、设备精度不被劫持；config链2：等效换算+口径冲突取舍），
  全量 42 用例 40 过 2 错——2 错为改动前即存在的环境问题
  （test_image_fetch CLI 子进程 gbk 解码，与本次改动无关，stash 基线复现一致）

### 硬件页三件套产品图替换（新功能，待执行验证）
- fetch_product_image.py replace 新增 --all_parts / --part camera|lens|light：
  相机+镜头+光源产品图按选型结果一条命令替换（相机走 blob 精确匹配与官网取图
  链路；镜头/光源为本地资产，三级匹配：库 image_path > images/{型号}.png >
  类型图资产目录 assets/part_images/）
- 类型图自动关联（用户实时可增，不改代码）：资产目录中文命名（远心镜头/条光/
  环光/同轴光.png…）运行时动态扫描，与选型 type 互包含或别名命中即自动配对；
  内置常用光源/镜头领域别名表（环形/条形/同轴/点光/圆顶/背光/无影/远心/定焦/
  变焦），aliases.json 可扩展；新增 map 子命令：--list 看资产与别名 / --migrate
  把 images/ 旧类型图一键搬家（型号横幅不动）/ --add 标准名 --alias 别名 实时
  登记新关联（立即生效）；缺图部件 WARN 并提示 map --add，绝不就近猜图
- 镜头/光源页面定位=文字锚定：硬件描述文本框（远心镜头/镜头/光源/环光/同轴）
  左侧同行最近的图片即其产品图；光路示意图部件标签（左侧无照片）天然跳过；
  未锚定到图 → WARN 列清单转人工，绝不瞎换
- 尺寸规则：原框内等比 contain 居中，任意形状产品图不变形不溢出
- 各件独立降级：缺图/未锚定 WARN 不阻断；全部 0 命中不产出文件
- 附 6 个离线测试（锚定命中/原文件字节不动/无图不误锚/库映射优先/
  selection 解析降级/CLI 三件套端到端，临时库隔离）
- 实测修复 3 缺陷（2026-08-31 首轮真实跑暴露）：
  ① find_local_image 库内正斜杠路径未归一（normpath 统一）；
  ② replace 三件套流转自拷自（相机命中后 tmp 既是源又是目标 → WinError 32
  文件占用），改为 a/b 两级交替中转文件；
  ③ 主流程验收相对路径静默失效（--output output 时验收子进程 cwd=tools_dir，
  相对路径 abspath 错位到 tools\output，查错文件仍打印完成——**交付失检**），
  _run_acceptance 入口统一归一为绝对路径；端到端测试原用绝对路径 temp 未覆盖，
  补"相对 --output 验收仍 FAIL=0"回归用例；仓库白名单同步落地（.gitignore
  只跟踪4个skill；git自动提交推送为symlink致白名单失效，换junction修复）

### 换相机图效果预览固化（新功能，高频场景一条命令）
- fetch_product_image.py 新增 replace 子命令：把方案 PPT 中的相机产品图换成指定
  型号的官网图，产出 `*_相机图预览_*.pptx` 预览件，原方案文件字节级不动。
  旧图定位自动读 PPT 同目录 selection_result.json 选型相机，也可 --old-model /
  --old-image 指定；0 处替换时诚实报错并列出各页图片清单（防瞎猜），不留半成品
- 基础版不在售自动发现：型号在官网系列列表缺失时，报错自动列出同前缀在售变体
  （实测 MV-CS060-10GM 基础版下架，仅 -PRO/V5 在售）；replace 配合 --auto_variant
  自动改用主推变体（-PRO > V5 > 其他），弱模型报基础版型号也能一条命令跑通
- 复用短路：库条目 image_path 或本地横幅文件已在 → 直接复用不重复请求官网
  （高频场景省时），--force 强制重取
- 弱模型 SOP 沉淀至 SKILL.md「相机产品图与效果预览」节；边界声明：预览件仅换图，
  页面文字仍是原选型型号，不可当正式方案交付（换型号须重新走选型链）
- 测试沉淀 6 用例（总 28 全绿）：离线 replace 三例（多页替换+原文件不动/0 命中
  不留半成品/CLI 端到端）+ 变体发现两例（前缀过滤不混 GC/UM 款/在线列变体）+
  复用短路一例；并修复复用短路引入的测试语义漂移（e2e 用例曾被短路架空，
  加 force=True 恢复真实网络链路覆盖——教训记入测试 skill AGENTS.md）

### 官网产品图自动获取（新功能）
- 新增 tools/fetch_product_image.py：选型后为相机自动补官方产品图。海康 API 通道
  （纯 HTTP 零浏览器）：官网系列树匹配 → Vision/Cameras 系列列表（productModel
  全等匹配防串行）→ VisionProductIntroduction（productModel 二次校验 + previewUrl
  + 中文描述）→ 下载原图 → PIL 合成 662x163 标准横幅（与 images/ 现有图同风格：
  型号名+描述+产品图）→ 写回库 image_path 并沉淀 source_product_id 可追溯
- 子命令：fetch（单型号）/ batch（库内缺图相机逐个补图，实测补齐 CS 系列缺图 3 台）
- 诚实降级：型号不在官网列表/系列名不唯一/品牌未接入/图源异常均报错转人工（exit 2），
  绝不编造图片；未接入品牌明说未接入（当前仅海康威视，其余品牌待扩）
- 主流程集成：generate_ppt 前 _ensure_camera_image 钩子——选中相机缺图自动补，
  失败仅 WARN 不阻断 PPT 生成
- batch 实测发现 MV-CA400-10GM / MV-CA500-10GM 不在官网在售列表；因"列表未收录"
  证据不足以判下架（该 API 可能仅含主推型号），恢复 verified=true 待人工复核并留痕
  ——教训：下架判定需要更强证据，已写入治理记录

### 口径与解析修复（bug，附测试沉淀）
- 修复口径优先级 bug：tolerance 曾无条件覆盖 precision_requirement（违反
  config_template 决策表"同时给时 precision_requirement 优先"），导致本项目
  唯一可行相机被口径漂移挤出局、选型无解。修复为决策表语义：precision_requirement
  优先，仅无明确精度时才按公差/10 反推
- 补齐 --text 公差解析：parse_user_data 原本无 ±公差提取，README 示例
  （检测CD尺寸38.50±0.25）的公差会被静默丢弃；新增 _extract_tolerance

### 测试体系（新 skill）
- 新增独立测试 skill「视觉选型测试」（opencode skills 目录，ZCode 经 junction 共用）：
  run_all.py 一键全量（--fast 跳过 PPT 端到端），回归+注入 22 用例覆盖选型核心/
  --text 解析/产品图获取/PPT 端到端，全绿（在线用例断网自动跳过）
- 纪律固化：bug→用例一一沉淀；注入用例对应历史事故不许删；测试用临时库副本
  不污染真实数据；被测 skill 修 bug 后必须跑本套件全绿才算迭代完成

## [v1.0.0] - 2026-08-30

首个正式版本：机器视觉检测方案的自动化选型与交付系统。从需求登记到方案
PPT 全流程脚本化，任何模型（含弱模型、无多模态模型）按 SKILL.md
「标准作业流程」执行即可复现交付效果。

### 选型引擎
- 视野+精度双约束选型管线：像素精度上限（精度 ÷ 亚像素因子 k=3）→ 所需像素
  → 倍率闭区间，相机与镜头联动匹配，输出 Top 3 候选方案
- SelectionValidator 全项核验：精度链/视野覆盖/倍率窗口/像圆/卡口/帧率/景深/
  远心必要性/可查证性等 19 项，有 FAIL 自动中止
- 选型无解时自动诊断：输出所需倍率窗口/像圆/分辨率/帧率的缺口报告，镜头无
  匹配时给出根因分类（换相机/扩库/核口径）；口径混淆时自动按标准口径复核
  重试并输出防死循环铁律

### 从0入口与防呆
- `--text` 需求文本入口：模型读图/文档后把数字信息原样抄录，解析、口径判断、
  校验全脚本化（自动识别检测区域/工件尺寸/视野并计算余量）
- 非交互防呆：缺精度/尺寸/格式错均报 `【缺少XX】` + 可执行修正指引并
  exit=2，不卡 input()，不静默按默认值计算
- config_template.json 内嵌字段说明与精度口径决策表（合同精度 / 图纸公差
  自动反推 / 用户口径优先），示例值全 null 防复制瞎抄
- 模板三级发现：`--template` → config 的 template 字段（相对路径按 config
  所在目录解析）→ 工作目录扫描 *.pptx；无模板时只输出选型方案结果并正常
  结束，有无模板都在终端打印选型汇总

### 方案 PPT 生成与自动验收
- 纯模板数据替换生成（保留模板母版与全部样式，绝不引入阴影等效果）
- check_ppt_quality 七项规则机检：旧型号残留 / 光源类型矛盾（含跨页）/
  两页参数一致 / 文本溢出断行预检 / 数值合理性复算 / 阴影污染 / 相机图替换
- 生成后自动验收：产出 acceptance_report.txt（FAIL=0 才可交付，尾部带
  故障处置对照表）
- 预览三件套：slide_N.png + overview.png 全页联系表 + index.html，导出通道
  自动降级（PowerPoint COM → LibreOffice headless → 如实报错不造假）
- 验收通过自动清理旧版本 PPT，output 下始终只留最新交付物

### 硬件数据库治理
- database_updater：gap 缺口报告 / fetch 获取 / add 强校验入库 / verify 复核 /
  check-db 新鲜度审计（超 180 天提醒）/ refresh 保鲜（字段级 diff，--apply
  确认，变更自动回退 verified 并写入 history）
- fetch 三级通道：静态快抓 → 无头 Edge 渲染（后台零窗口，SPA 动态页可用）
  → AI 浏览器接管兜底；无来源 URL 的参数一律拒绝入库，新条目 verified=false
  需人工对照官网后 verify 置真
- 提取防串行：表格行级定位 → 卡片容器定位 → 全文三级提取，多型号页无法
  定位参数区时拒绝自动提取并提示 --html 通道
- 镜头参数禁止从型号名推断：WD 以官网实测为准，wd_spec 存公差原文
  （如"158±3"）且 PPT 优先显示；远心系统"相机工作距离"= 镜头物方 WD；
  光源 WD 必须小于镜头 WD（选型约束 + 核验 FAIL 双重拦截）

### 弱模型支持与文档体系
- SKILL.md「标准作业流程」：填表 → 一条命令 → 读一行结论 → 按模板汇报，
  日常续跑全程约 2000~3000 token；质量机检纯文本（零图像依赖），无视觉
  能力的模型也能跑通闭环
- 防死循环铁律：同一参数组合最多跑 2 次 / 禁止改口径字段凑解 / 连续 2 次
  无解必须转问用户
- 文档分工：SKILL.md = 使用说明（运行时触发即读）、AGENTS.md = 开发规范
  （含历史事故档案）、README.md = 特性与快速开始、CHANGELOG.md = 版本记录
