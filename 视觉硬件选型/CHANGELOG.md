# 更新日志

本 skill 的所有版本变动统一记录在此。格式参考 Keep a Changelog。

## [Unreleased]

### 修复：全链逻辑审查 12 项（v1.11.1）

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
