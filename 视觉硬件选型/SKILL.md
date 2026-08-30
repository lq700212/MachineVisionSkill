---
name: "视觉硬件选型"
description: "机器视觉硬件选型专家，根据检测需求自动完成工业相机、镜头、光源的选型计算与方案文档生成。当用户提到机器视觉选型、工业相机选型、镜头选型、光源选型、视觉检测方案、AOI硬件选型、尺寸测量硬件选型、缺陷检测硬件选型时使用。"
---
# 视觉硬件选型技能

> **⚠️ 开发者入口**：如果你的任务是修改/迭代本 skill（代码、文档、硬件库），先读本目录
> `AGENTS.md`（开发规范与事故档案），再动手。
>
> **运行时省 token 指引**：标准任务只照本文件「标准作业流程」的**⚡ 最短路径**三步执行
> （工作区 config 已就绪时），**不要读本文件全文**。本文件其余内容按需查阅：
> 新项目需求登记（同章节）、扩库/库保鲜（数据库扩库流程节）、验收排障（FAIL 对照表/教训节）。

## 功能描述
机器视觉硬件选型专家。根据检测需求，按行业标准方法论自动完成**需求归一化 → 分辨率/倍率推导 → 相机选型 → 镜头联动匹配 → 光源推荐 → 全项核验 → 模板PPT生成**。

## 触发条件
机器视觉选型、工业相机选型、镜头选型、光源选型、视觉检测方案、AOI硬件选型、尺寸测量硬件选型、缺陷检测硬件选型。

---

## 选型方法论（已固化到脚本，AI无需重新推导）

### 第1步 需求归一化
| 输入 | 公式 | 示例 |
|------|------|------|
| 公差 → 精度 | **精度 = 公差 × 1/10**（行业标准） | ±0.25mm → 0.025mm |
| 工件尺寸/检测区域 → 视野 | **视野 = 尺寸 × 余量(1.2或1.5)** | 50x30 ×1.2 → 60x36mm |
| 直接给视野 | 不加余量 | fov:60x40 → 60x40mm |

### 第2步 分辨率需求（需求侧推导，与硬件无关）
```
像素精度上限 = 检测精度 / 亚像素因子k      （默认k=3：单特征≥3像素，亚像素算法）
所需像素 = 视野 ÷ 像素精度上限（逐轴，向上取整）
```

### 第3步 相机选型（视野+精度双约束的必要条件）
```
相机分辨率 ≥ 所需像素        （等价于存在可行倍率窗口）
帧率 ≥ 1.5 × 节拍频率
```

### 第4步 镜头联动匹配（倍率闭区间，杜绝"假设倍率"）
```
精度下限: 倍率 ≥ 像元尺寸 / 像素精度上限
视野上限: 倍率 ≤ 传感器尺寸 / 所需视野
可行镜头 = 倍率落在区间内 + 像圆覆盖靶面 + 卡口匹配 + 实际视野≥所需视野
```
评分偏好：倍率靠近视野上限（视野利用充分、精度余量大）、低畸变、高远心度。

### 第5步 光源推荐
- 工作距离 = 视野对角线 × 角度系数(30°:0.6/45°:0.8/60°:1.0/90°:1.5) × 1.2
- 照射范围外径 ≥ 视野对角线 × 1.1

### 第6步 全项核验（相当于发版前回归测试，有FAIL直接中止）
| 核验项 | 判据 |
|--------|------|
| 精度链 | 像素精度 ≤ 检测精度/k，余量≥1.3x为佳 |
| 视野覆盖 | 实际视野(相机+镜头闭环) ≥ 所需视野 |
| 倍率窗口 | 镜头倍率 ∈ [精度下限, 视野上限] |
| 像圆覆盖 | 镜头像圆 ≥ 相机靶面对角线 |
| 卡口匹配 | 相机lens_mount = 镜头mount |
| 帧率余量 | ≥ 1.5×节拍频率 |
| 远心必要性 | 尺寸测量或精度≤0.01mm时必须远心 |
| 型号可查证 | verified标记 + 官网链接 |

### 核心原则：参数必须有明确来源
- **不能从型号名称猜参数**（如DTCM110-64H的"64"≠0.64x，实际0.259x）
- 精度/公差、工件尺寸/检测区域/视野必须来自用户或资料，否则询问用户
- 数据库中倍率未确认的镜头（如DTCM110-56-AL）不参与自动选型

---

## 标准作业流程（模型无关：任何模型照此执行即可复现交付效果）

> 本节为弱模型防呆指引，也是**日常续跑的唯一入口**。计算/选型/PPT/验收全由脚本完成，
> 模型只需要执行三步并看一行结论，不需要专业判断。

### ⚡ 最短路径（工作区 project_config.json 已就绪的续跑场景）

前提：工作区 `project_config.json` 已就绪（口径由用户拍板，记录在 config 内）。
满足前提直接执行下面 3 步，**不要重新分析需求、不要改 config、不要自己算参数**：

**第1步 一条命令生成**（自动选型→核验→PPT→规则自查→导页面图→清理旧版本）：
```bash
python "C:\Users\Administrator\.agents\skills\视觉硬件选型\tools\vision_proposal_generator.py" --config "<工作区>\project_config.json" --output "<工作区>\output" --auto
```

**第2步 只看脚本的验收结论行**：
- `结论: ✓ 通过 FAIL=0` → 交付 `output\` 下唯一的 PPT，跳到第3步
- `结论: ✗ 存在FAIL` → 打开 `output\acceptance_report.txt` 尾部故障对照表处置；
  **对照表处置不了的新问题：原样报告用户并停止，禁止自行改 skill 脚本或手改 PPT**
- 脚本输出 `[无解诊断]` / `✅ 标准口径有解` → 按 ⛔ 防死循环铁律处理（见下文），
  把脚本里的口径确认问题原样转问用户，**答复前不要继续**
- **禁止读取 `output\ppt_review\` 里的图片**（slide_N.png/overview.png）——那是给用户
  看的预览；质量把关靠规则自查（纯文本机检），模型读图浪费大量 token 且不需要

**第3步 按此模板汇报**（不要展开更多细节）：
> 已生成视觉检测方案PPT：`output\<文件名>`（验收 FAIL=0）。
> 选型：<相机型号> + <镜头型号>（倍率X，像素精度X mm/pixel）+ <光源型号>。
> 页面预览图在 `output\ppt_review\`，可抽查。

### 禁止事项（违反即事故）
1. **禁止口述/手写方案代替脚本生成；禁止用代码手改 PPT**——方案只能由一条命令产出
2. **禁止修改** `project_config.json` 的 `precision_requirement` / `pixel_per_precision` /
   检测区域字段（那是用户拍板的口径，改了=发明口径）
3. **禁止在工作区创建任何 Python 脚本**；所有逻辑都在 skill 里，只能调用不能重写
4. 标准任务只读本节（最短路径三步）；本文件其余内容（使用方式/扩库/排障）按需查阅

### 新项目从0：需求登记（唯一需要AI理解的环节）
1. **--text 模式（推荐）**：AI 读用户图片/文档/口述后，把其中的数字信息**原样抄录**给脚本
   （不要自己解读成参数），脚本负责解析与口径判断：
   ```bash
   python "C:\Users\Administrator\.agents\skills\视觉硬件选型\tools\vision_proposal_generator.py" --text "设备精度≤0.03mm，生产节拍3秒，检测区域38.5x22mm，检测XX尺寸38.50±0.25..." --output "<工作区>\output" --auto
   ```
   图片必须 AI 直接读图抄字（勿依赖 OCR）。
2. **config 模式**：复制 skill 目录的 `config_template.json` 为工作区 `project_config.json`，
   把 null 换成真实值。字段说明与**口径决策表**都写在模板内：
   - 精度口径三选一：合同/用户明确精度 → `precision_requirement`；只有图纸公差 → `tolerance`（自动按公差/10反推）；用户口头放宽 → 以用户最新口径为准。**不确定就问用户，不要发明口径**
   - **单位铁律**：`precision_requirement` 的单位是毫米（设备检测精度），不是像素精度(mm/pixel)！像素精度上限 = precision_requirement ÷ pixel_per_precision（0.03÷3=0.01mm/pixel）。用户说"精度0.03"默认指设备精度；只有用户明说"像素精度是X mm/pixel"才按像素级口径处理
   - 尺寸三选一：`detection_area`（检测区域，推荐）> `part_size`（整体外形）> `field_of_view`（最终视野）
   - `template` 可省略：自动扫描工作目录 *.pptx；工作目录无模板时只输出选型结果（放模板后重跑即生成PPT）
3. 漏填/格式错不会静默出错方案：脚本报`【缺少XX】/【尺寸格式错误】`并给出可执行修正指引
   （exit=2），照提示补齐重跑；填好回到最短路径第 1 步执行

### ⛔ 防死循环铁律（选型无解时必读，任何模型适用）
弱模型曾因把"精度0.03"误解为"像素精度0.03mm/pixel"导致选型无解，然后无限循环调参
（反复打印"让我重新考虑/让我尝试更大的像素精度"）。以下铁律直接执行，不需要理解原理：

1. **同一参数组合最多跑2次**。脚本输出`[无解诊断]`后，按诊断文案行动，不要改参数重跑试探
2. **禁止改 `pixel_per_precision`、`precision_requirement` 等"凑出"选型解**——那是在发明口径
3. 脚本输出`✅ 标准口径有解`时：说明口径混淆已被脚本自动矫正，**把脚本里的确认问题原样转问用户**
   （"您说的精度0.03是设备检测精度(mm)还是像素精度(mm/pixel)？"），用户答复前不要继续生成PPT
4. 脚本输出`[镜头无匹配·根因]`时按根因走：窗口上限低于库内最低倍率→换更大靶面相机（脚本会自动
   遍历）；窗口下限高于库内最高倍率→走扩库流程；勿自行调镜头参数
5. 真无解（缺口报告出现）：把缺口报告原文转给用户，停止动作。**连续2次无解必须停下来向用户报告，
   禁止第3次重跑**

### 生成过程说明（最短路径第1步在做什么）
一条命令自动包含：需求校验 → 选型 → 19项核验（FAIL自动中止）→ 模板PPT替换 →
规则自查（check_ppt_quality）→ 页面渲染导出（export_ppt_images）→ 清理旧版本PPT。
完整自查报告：`output/acceptance_report.txt`；`--no_verify` 可跳过验收（不建议）。

### FAIL 详细处置对照表（验收结论行不为 ✓ 时查这里）
| 报告症状 | 原因与处置 |
|---------|-----------|
| 旧型号残留 | 模板触发词未被替换规则命中 → 把新触发词加进 generate_ppt.py 对应规则 |
| 光源类型矛盾 | 检查 light_selector 光源 type 与模板标注框；同义词逻辑在 generate_ppt 3.3b |
| 断行/溢出风险 | 替换值变长：WD标注需 word_wrap=False（已内置）；窄标注框只写短类型词（同义词保留逻辑已内置）。仍报溢出→缩短文案或联系人工 |
| 数值不合理 | 需求口径被改过 → 重跑选型 |
| 阴影 | 用 tools/clean_ppt_shadows.py 清理 |

处置不了的新问题 → 原样报告用户并停止。需终审时（可选）：把 ppt_review 页面图交视觉评审复核。

### 交付物清单
`output/` 下：方案PPT（验收通过自动只留最新版）、`selection_result.json`（选型明细+核验
结果）、`acceptance_report.txt`（自查报告）、`ppt_review/`（页面图+总览图+预览页）。

### 本次沉淀的教训（已固化进脚本，此处留档供理解）
- 精度口径曾从合同级0.012调整为实用级0.03：口径必须由用户拍板，工具只按给定值算
- 弱模型曾把"精度0.03"误解为像素精度导致死循环调参 → 脚本已内置无解诊断+口径自动复核+防死循环铁律
- config链曾漏掉选型核验（只有files链有）→ 已补齐，selection_result.json 的 validation_passed 现在两条链都可信
- **型号名≠参数**：DTCM110 系列曾被从型号推断 WD=110mm 入库，官网实测 64H-AL=158±3mm、
  56-AL=138±3mm——已 refresh 官网闭环修正并加 wd_spec 公差字段；任何参数禁止从型号名推断
- 远心系统工作距离由镜头物方WD决定：PPT"相机工作距离"直接取镜头WD（wd_spec优先显示公差）；
  光源WD必须小于镜头WD（选型自动约束+核验FAIL拦截），光源装在镜头与工件之间
- 光源类型前缀沿用模板原词会与实际光源矛盾（第4页"同轴光"vs第5页"环光"）→ 已按选中光源type纠正+同义词保留
- WD数值替换变长会在窄框断行（"51.1m/m"）→ 已对标注框关自动换行
- 长描述塞短标注框会溢出叠压 → 已规范为短类型词
- 以上全部可通过 check_ppt_quality 的注入测试复现检出

## 使用方式

### 方式1：从用户资料生成（AI调用必加 --auto）
```bash
python tools/vision_proposal_generator.py \
  --files 用户资料.jpg \
  --template 视觉检测方案.pptx \
  --output ./output --auto
```

### 方式2：JSON配置 + 模板（多视角模板用 --hardware_page 指定页）
```bash
python tools/vision_proposal_generator.py --config project_config.json \
  --template 视觉检测方案.pptx --output ./output --auto --hardware_page 2
```
- 模板可省略（--template/config的template字段都不给时）：自动扫描工作目录的 *.pptx
  （取修改时间最新）；工作目录也没有模板时**只输出选型方案结果并正常结束**
  （selection_result.json 照常落盘），放入模板后重跑同一命令即生成PPT

### 方式2b：需求文本从0入口（弱模型推荐：读图抄字，解析交给脚本）
```bash
python tools/vision_proposal_generator.py --text "设备精度≤0.03mm，生产节拍3秒，检测区域38.5x22mm，检测CD尺寸38.50±0.25..." --output ./output --auto
```
AI 把图片/文档/口述中的数字信息**原样抄录**给 --text（精度/公差/节拍/检测区域等），
脚本负责正则解析、口径判断与校验；漏填时脚本报`【缺少XX】`+可执行修正指引（exit=2）。
config_template.json 的示例值均为 null——禁止直接复制不改就跑。
配置字段说明与口径决策表见 `config_template.json`（复制后填值即用）：
```json
{
  "project_name": "弹簧垫片视觉检测方案-视角2",
  "tolerance": 0.25,
  "field_of_view": {"width": 24, "height": 20},
  "cycle_time": 3,
  "pixel_per_precision": 3.0
}
```

### 方式3：仅核验已有选型结果
```bash
python tools/validate_selection.py --selection output/selection_result.json \
  --json_out output/validation_report.json
```

### 方式4：仅对已生成的PPT做规则自查/导出预览
```bash
python tools/check_ppt_quality.py --pptx output/方案.pptx \
  --selection output/selection_result.json --out output/acceptance_report.txt
python tools/export_ppt_images.py output/方案.pptx          # 加 --open 自动打开预览页
```
预览产物（`ppt_review\`，主流程生成后自动产出）：`slide_N.png` 每页原图、
`overview.png` 全页联系表总览（一眼看全）、`index.html` 浏览器预览页（双击翻看）。
导出通道自动降级：本机 PowerPoint COM（首选，后台无窗口）→ 无 PowerPoint 时探测
LibreOffice headless 转 PDF。两者都没有时如实提示，不产出假预览。

---

## 数据库扩库流程（已固化到 database_updater.py）

选型无解时主流程自动输出**缺口报告**（需要什么倍率/像圆/分辨率/帧率的硬件），按以下流程扩库：

```bash
# 0. 查看各品牌核验通道（三级通道：静态快抓 → 无头渲染 → AI接管）
python tools/database_updater.py brands

# 1. 缺口报告（选型无解时也会自动打印）
python tools/database_updater.py gap --fov 63x42 --precision 0.025

# 2. fetch 一条命令走三级通道（推荐）：静态快抓 → 无头Edge渲染（后台零窗口）
#    → 前两级失败才输出AI浏览器接管SOP；省略--url时自动用品牌SOP入口
python tools/database_updater.py fetch --brand 视清科技 --model WWK03-110C-230 --type lens
python tools/database_updater.py fetch --model 型号 --url 详情页网址 --type lens   # 已知详情页直达

# 2b. 兜底：AI用浏览器打开官网详情页（多级交互/登录/验证码场景），
#     渲染完成后保存页面HTML，然后脚本提取+入库（一条命令完成）
python tools/database_updater.py add --html 页面.html --url 详情页网址 \
  --type lens --model 型号 --brand 视清科技

# 3. AI/人工对照官网复核参数 → 置为已验证
python tools/database_updater.py verify --model 型号

# 4. 重跑选型（新硬件即刻参与选型）
```

### 无头渲染（默认通道，对用户完全无感）
- `fetch`/`refresh` 内置：型号不在静态页面时自动降级用**系统自带 Edge 无头模式**
  （`--headless=new --dump-dom`）后台渲染，**不弹任何窗口、不闪任务栏**，效果与
  有头浏览器同内核一致（SPA/XHR 数据可取）
- 等待时间可调：`--render_ms 12000`（默认12秒虚拟时间预算）；`--static_only` 可强制只走静态
- 已验证：coolens（动态详情页）✓、海康SPA ✓、华睿SPA ✓；孚根详情页正文需真实交互，
  无头渲染会诚实报"页面未含型号"并降级 AI 接管（不编造数据）

### 库的保鲜（官网参数会变化，防止数据腐烂）
```bash
# 审计：check-db 会列出超过180天未复核的条目（阈值可改 --freshness_days）
python tools/database_updater.py check-db

# 刷新：直接refresh即可（自动走三级通道取官网最新页面，后台无窗口）
python tools/database_updater.py refresh --model 型号            # 预览diff
python tools/database_updater.py refresh --model 型号 --apply    # 应用
python tools/database_updater.py verify --model 型号             # 复核后重新置真
# 也可AI重新打开该型号官网页存HTML后：refresh --model 型号 --html 新页面.html
```
- refresh 有变化时自动把 verified 回退为 false（旧核验状态对新参数不再可信），每次变更写入条目 history（日期/来源URL/字段旧新值），全程可追溯
- 每次选型的核验报告自带新鲜度检查：条目超180天未复核 → WARNING 提示 refresh

**架构与守则**：
- 获取层：三级通道——静态快抓（最快）→ 无头Edge渲染（默认主力，后台零窗口，与有头浏览器同内核）→ AI浏览器接管（仅登录/验证码/需多级交互时兜底）
- 识别层：脚本从渲染后HTML提取参数——表格行级定位（按型号锁定`<tr>`，避免总表串行）、标签式详情页正则；提取不到的字段留空由AI补全
- 校验入库层：强校验（型号唯一、来源URL必填、数值合法）——**没有官网来源的参数一律拒绝入库**
- 新条目 `verified=false`（参与选型但核验报"可查证性"警告），AI对照官网复核后 `verify` 置真
- 每次写库自动备份 `.bak`；`check-db` 可随时校验库一致性

### PPT相关
```bash
# 阴影清理（修复被外部工具加阴影的PPT，默认备份.bak）
python tools/clean_ppt_shadows.py 文件.pptx [-o 输出.pptx]

# 仅做模板替换（已有选型JSON时）
python tools/generate_ppt.py --template 模板.pptx --output 输出.pptx \
  --selection_json output/selection_result.json --fov 24x20 --hardware_page 2
```

---

## PPT生成规则（模板数据替换，绝不重建）

1. **只替换"硬件选型"页**，其余页面一字不动；`--hardware_page N` 指定替换第N个硬件页（多视角模板每页一个视角）
2. **替换内容**：表格（相机工作距离/视野/精度/光源工作距离）、相机描述行、镜头行（远心镜头：/镜头：）、光源行（同轴光：/环光：）、独立WD标注文本框（大值→相机WD，小值→光源WD）、右上角相机产品图
3. **保留全部样式**：只改文字与图片，绝不写入阴影/发光等任何效果
4. 视野数值使用相机+镜头闭环计算的实际视野，与像素精度自洽
5. 已知限制：模板"方案设计"页（多视角混排描述）不做替换，避免跨视角误改

## 硬件数据库
`config/hardware_database.json`：海康威视相机（CS/CA系列）、视清科技远心镜头（WWK/WWH/DTCM系列，倍率0.3~1.5x）、OPT光源。所有型号带 verified 标记与官网链接，**扩展数据库时必须用官网可查证的型号**。

## 环境与输出
- 依赖：python-pptx、Pillow、numpy（easyocr可选）；首次运行自动检查安装
- 输出：`--output` 指定目录（PPT、selection_result.json、validation_report.json）

## 注意事项
1. AI调用脚本一律加 `--auto`（非交互自动选最优方案）
2. 精度计算预留安全余量：像素精度≤精度/3；帧率≥1.5×节拍
3. 数据库查不到可行镜头时工具会**诚实报错**（列出原因），不要编造型号，应提示用户扩库或调整视野/精度
