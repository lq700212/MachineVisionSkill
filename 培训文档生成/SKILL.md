---
name: "培训文档生成"
description: "工业上位机软件培训文档全流程：自动截图各界面（Mock数据三规则＋防卡住看门狗＋脚本模板）到编写三份文档（操作员版/客户技术工艺版/内部版），含分段写作红线与一键核验脚本，弱模型照抄执行。当用户说截图配图、写使用说明、操作手册、培训文档时使用。"
---

# 培训文档生成（三份制）

一次交付三份，分别给三种人。先认人，再动笔。

## 一、三份定位与差异矩阵（铁律）

| | 操作员版 | 客户技术工艺版 | 内部版 |
| :--- | :--- | :--- | :--- |
| 对象 | 第一次摸软件的产线员工 | 客户方技术员、工艺工程师 | 我方现场工程师、技术支持 |
| 语言 | 大白话，背下来照着做 | 专业但不涉内部实现 | 行话，红线索引 |
| 硬件 | 只提见得到的设备 | **按项目实配品牌写**，未启用品牌一个不出现（门禁：全集−实配） | ＋产品全支持面（每处标注本项目实配） |
| 权限 | 只讲未登录操作员打得开的（先 grep 入口代码确认可达） | 只讲该管理员账号打得开的；仅我方最高权限账号可达的页面**零出现**（不点名不讲用途不给步骤不给图，见下方权限可达铁律） | ＋隐藏最高权限账号 |
| 授权 | 只讲"找商务开户、报码激活" | 同左 ＋ 一机一码注意事项 | ＋发码工具内部流程 |
| 工艺 | 只给红线（时长填0不行） | 配方设计方法、策略选用、换型清单 | 同左 ＋ 判定逻辑归属、代码红线 |
| 排障 | 先查什么 | 先查什么 ＋ 什么情况叫售后 | 先查什么 ＋ 什么情况升级开发 |
| 结尾 | 点检＋禁忌 | 自查 ＋ 升级条件 | 自查 ＋ 回炉对应节 |

**红线**：隐藏权限账号、内部发码/签发工具流程、源码文件级实现细节，绝不进客户版；
演示截图里的机器码注明"演示机示例"；密码只给初始值并要求首登修改。
截图涉密内容必须打码（三份一律，内部版也不留明文），细则见§三R4。
**权限可达铁律（2026-10 两轮血泪：先是最高权限专属测试页写进操作员/客户版教操作；
纠偏成"一句话认档"后，客户版第七节仍逐条点名 dev 页清单＋讲用途——客户不需要
知道这些功能存在，"它是干什么的"本身就是泄密面）**：
任一章节动笔前先 grep 该页面的 `new` 入口，确认调用路径在目标读者角色可达
（菜单/按钮是否跟登录走、面板是否仅某角色弹），按可达结论**三档分流**：
- 目标读者可达 → 展开写（步骤＋图）；
- 客户内更高角色可达（如操作员版讲管理员档功能）→ 一句话认档（干什么的＋找谁开），无步骤无图；
- **仅我方最高权限账号可达（dev 专属页）→ 客户两版零出现**：不点名、不讲用途、
  不给步骤、不给图，连"它是干什么的"也不写；唯一允许不带任何功能名的兜底句
  （"部分窗口仅我方工程师可操作，需要时联系我方"）＋"何时叫我方"的**场景清单**
  （讲联调验证/参数调整/加账号这类场景，绝不点页面名）。
  配置开关禁用的"节内一句话豁免"（§二⓪）不适用于本档——点名即违规；
  "开发者面板/功能开关/最高权限入口"等内部机制词同样不进客户两版
  （权限表里我方档位只写"最高权限，仅我方持有"，括号里的功能列举全删）。
门禁三件套（`check_docs.py`，名单按项目入口代码产出）：dev 页名禁词
（标题＋正文一起扫，含别名）、dev 页配图禁入（DEV_ONLY_IMGS）、人审兜底零出现。

## 二、工作流（六步）

```
⓪读配置 → ①盘点 → ②实拍 → ③分段写 → ④逐张核验 → ⑤同步周边
```

**⓪读配置（2026-10 血泪：文档写了开关已禁用的功能）**：动笔前先读
软件当前配置文件与当前项目配置文件，**以项目配置文件为主**，
输出"功能开关矩阵"，截图清单与章节只覆盖启用的。
本条全局生效，不限 MES（同轮血泪：MES 查看开关 OFF 却留了整节 MES 联调；
再如存图预览开关 OFF，则存图浏览章节同样禁入客户两版）：
- 软件级开关：运行目录主配置（如本项目 `00_ExeBuild/MainSetting/MainSetting.ini`
  `[DevPanel]`：扫码查看存图 / MES 查看 / 主题按钮 / Mock 等）；
- 项目级（料号）开关：`Programs/<当前料号>/` 下通讯/参数配置各节 Enable/Count
  （如本项目打码 `Count=0` 关、耐压串口空关、TCP 通道 OFF、震动盘 Feeder1 开）；
- 当前料号从主配置读（如 `[PN] CurrentPN`）；ini 可能是 UTF-8/GBK 混排文件，
  按行先 UTF-8 解码、失败回 GBK（与产品 IniFile 同规则，否则 CurrentPN 读出乱码）。
- 被禁用的功能：截图不拍、操作员/客户版整节不写（标题也不留，整节删，
  后面节号前移＋交叉引用全修＋内部版回指同步改；开关管的不只是图，更是章节）；
  内部版可保留全量，但每处必须标注开关状态（如"本项目：关"）。
- **硬件实配（品牌收敛，2026-10-04 血泪：系统组成堆了 4 家 PLC/2 家相机/2 家光源，
  本项目实配只有欧姆龙＋海康＋诺达佳）**：架构/系统组成/硬件对照等"全貌"章节，
  硬件品牌按**当前项目实配**写，禁堆产品全家桶——堆品牌＝泄我方支持能力面＋客户困惑。
  实配两类来源：有 ini 键的自动判定（如 PlcType→品牌映射）；无键的静态登记并注明证据
  （相机实装台数与品牌、料号 LightSetting.ini `Type=Nodaka`）。禁用通道（如 TCP OFF）
  从所有列举里去掉；界面固定文案自带别家品牌的（如分组标题"含汇川Modbus"，
  重拍也不会变）正文不复述、图题挑实配重点写。
  门禁：check_config.py 登记 BRANDS_ALL（全集）/BRANDS_PRESENT（实配），
  **禁词＝全集−实配自动算出**，客户两版全文扫（空格变体走正则），命中即 FAIL——
  登记表缺项即漏网（与开关映射表同纪律）；**品牌表没填不许写全貌章节**
  （同"不读配置不许定截图清单"）。
- 边界（一句话附带说明允许）：节内顺带一句"XX 菜单本项目已禁用，需要时联系我方"
  不算违规，读者找不到入口时需要这句解释；禁的是独立章节、操作步骤与配图。
  **注意分级**：本豁免只管**配置开关禁用**的功能（客户管理员本来可达，只是当前关着）；
  权限级不可达的 dev 专属页（§一铁律第三档）没有豁免——零出现，禁用说明也不许点它的名
  （写"该菜单本项目已禁用"可以，写"XX 测试页只有工程师能开"不行）。
- 登记义务（两处一次配齐，加新功能必做）：`check_config.py` 里 sw 登记开关 +
  `CHAPTER_GATES` 登记章节标题关键词（只扫 `## ` 独立标题，节内附带句不误杀），
  登完做反向验证（临时给客户版加一行该图引用＋一个该关键词标题，确认各 FAIL 一次，
  再回滚）。映射表缺项即漏网（datahub 漏登记即实证）。
- Mock/种子演示数据是例外（R1 确定性要求）：允许拍，但 caption 必须注明演示数据，
  且 screenshot 时的 Mock 开关状态要与 caption 一致（别在 Mock OFF 的机器上
  写"当前界面"，读者复现不出来）。
- 脚本化：`check_config.py`（读配置→矩阵→图片门禁＋章节门禁双交叉检查，
  操作员/客户版命中禁用图或禁用章节标题即 FAIL，内部版只 INFO），
  `check_docs.py` 集成调用，一处跑全绿才算完。

**①盘点功能入口**：读 README/AGENTS/菜单代码，列出全部窗口与"谁能点"；
定截图清单（每个窗口一张，尤其是自绘画布单独记）。
盘点三硬动作（漏过备用映射的血泪）：A. 扫全部右键/上下文菜单与弹窗内按钮
（grep ContextMenuStrip/右键/ShowXxxPopup/右键菜单注释），右键线是独立功能，
文件列表里看不见；A2. 逐项枚举全部菜单栏/工具栏下拉（WinForms 血泪 2026-10：
子窗"设置"MenuStrip 11 项漏盘点——委托回主窗的 8 项在矩阵里，子窗自有的输入框类
4 项曝光/增益/自动触发/胶片开关全漏）。扫法：Designer 里所有
`DropDownItems.AddRange` 逐个抄（二级/三级递归进，路径链记全；
内嵌 ComboBox/TextBox 单列，每项跟 Click/SelectedIndexChanged/TextChanged
绑定到哪个处理函数）；**每个弹窗都要有截图**：空表弹窗必须 mock 出演示行
（点"新增"加内存行、拍完 Dispose、绝不点保存，ini 零写入；
新增行若有"作业未就绪"类门控，把 mock 排到 VPP 加载完成后）；
B. 输出"权限×功能矩阵"（每个功能标角色），
"需要 X 权限"禁一句话带过——目标读者手握该权限的，必须展开操作步骤；
目标读者没有该权限的按§一铁律三档分流：客户内更高角色可达的只许一句话认档
（干什么的＋找谁开），禁展开步骤禁配图；**仅最高权限账号可达的 dev 专属页
（反例：测试页 `new` 全在开发者面板内、面板仅最高权限登录才弹）在操作员/客户版
零出现——不点名不讲用途，禁步骤禁图禁认档**。
每个功能必须 grep 到 `new 该窗体` 的生产调用点并确认调用路径在该角色可达
（菜单/按钮是否跟登录走、面板是否仅某角色弹；反例：测试页 `new` 全在
开发者面板内、面板仅最高权限登录才弹，则操作员/客户版禁写操作步骤）；
C. 功能清单与文档章节双向对账（见§五新增两条），对不上的功能就是漏网。

**②实拍**（见第三节截图五规则）：先跑通再写文档，写的时候才有图可配；
拍完先人眼过一遍，不合格（空白/无数据）当场重拍，不留到最后。

**③分段写**：三份一次写完；单次写入有长度上限（见第五节红线），
超长文档必须分段追加，写完逐段复读。

**④逐张核验**：每张图人眼确认"非空＋内容对版"（状态对、数据是演示数据、
 Pass/Fail 各有一张）；grep 全文档无截断标记；涉密截图已按§三R4打码
 （设备ID/设备码/授权码/机器码/外网IP/客户真实数据，打码区放大4倍无字符残留，
 PDF已重转，内嵌图与png一致）。

**⑤同步周边**：README 快速定位表、CHANGELOG 顶部新小节（改动范围/为什么/验证）、
旧文档删不删（被替代且无保留意义才删，协议类唯一文档永删不得）。

## 三、截图全流程（从界面到 PNG，核心章节）

目标：每个关键窗口一张"带生产数据的真图"，存进文档配图目录（如 `docs/images/`），
以后改了界面重跑一遍即换图。手段：独立 harness 直接 new 窗体（参考 winforms-ui-debug
指哪打哪），绝不靠手工一个个开窗截图。

### R1 数据走生产路径（禁止 P 图式伪造）

- 用 Mock/仿真设备 ＋ 公开 API 驱动**真实状态机** ＋ 真实落盘；
  唯一例外是"模拟用户打字"（登录密码/批号/配方名填框），那本就是用户输入。
- **确定性第一**：原生随机 Mock 在高频采集下几十秒全员报警，演不出"正常/完成"态。
  做法：注入定值仿真源（如恒定好真空），好阈值走完"抽真空→上电→完成"全流程，
  另设一个苛刻阈值工位首轮即报警，专门演"故障"；短时长配方专门演"已完成"。
- 时效态先拍：老化中/抽真空是过渡态（几分钟就变），完成/故障态稳定，
  开拍顺序把带活台数的图（状态总览、下料判定）放最前。
- 落盘类窗口（历史记录/报表）先写种子数据再开窗；当天真实日志先备份、拍完还原，
  还原成功要在日志里确认一行，不污染现场数据。
- 动态窗等稳了再拍：如"连接后每 N 秒自动读数"的窗口，多等两个周期，
  否则读数区全是"--"。

### R2 截图方式按窗体类型三选一

- 标准对话框：PrintWindow（渲染完整，与屏幕位置无关）。
- 自绘画布（网格/拓扑图/曲线）：置顶（TopMost）＋ CopyFromScreen 真屏截图，
  PrintWindow 在滚动过的画布上会丢 GDI 文字（框在字无）。
- 菜单内嵌输入框末级小窗（ToolStripTextBox/ComboBox 单独成窗）：
  PrintWindow 抓出全黑条（WinForms 血泪 2026-10，166×34 实证），改真屏抓
  （按窗口矩形 CopyFromScreen，要求窗口最前不被挡）。
  判据：先 PrintWindow 看指标——小窗 total=0 且人眼黑条即中招，切真屏重拍。
- 拍前窗口居中，拍后 sleep 300~800ms 等首帧；含标题栏一起存（文档要看到窗口名）。
- **harness 必须先调视觉样式（WinForms 血泪，2026-09 CommandCenter 实证）**：
  `Main()` 开头调 `Application.EnableVisualStyles()` ＋
  `Application.SetCompatibleTextRenderingDefault(false)`（与产品 `Program.Main`
  一致），否则全部标准控件（ComboBox 边框/滚动条/表格头/按钮）按 Windows
  Classic 渲染，与真实软件颜色风格不一致。判据：harness 图与真机实拍逐像素
  diff（`ImageChops.difference` 分区看），标题栏区 mean>15 即中招。
- 拍前 `f.Activate()`：非激活态标题栏是灰蓝色，与使用态不一致；主窗口按真实
  行为铺满（有多大拍多大），固定小尺寸会把标题栏按钮挤掉，与真机不符。
- **静态对话框优先真进程实拍（2026-09 CommandCenter 血泪，最高优先级）**：
  harness 里直 `new` 的对话框恒为 classic 边框（外框比真机小一圈），根因未完全查明
  （manifest/视觉样式 API/子系统/config/模态与否逐项对照排除），经验结论是
  "不要深究，直接用真进程拍"。分工固化：静态窗一律真进程驱动实拍
  （Win32 消息开窗截图取消，见下条），harness 只拍无硬件演不出的动态态。
- **驱动真进程严禁 `SendMessage(BM_CLICK)`（2026-09 现场事故）**：
  SendMessage 是同步的，按钮一弹模态框发送线程就卡死，每个弹窗都得用户手工关。
  开窗点击一律 `PostMessage(BM_CLICK)` ＋ WaitTitle，发送线程永不阻塞；配套：
  输入框按屏幕坐标排序定位（一次填对，不靠"顺序反了报错再换"）、看门狗只关
  非目标小弹窗、FAIL 当场截全屏、单实例预检、全英文日志、finally 验退。
  登录密码先读配置哈希比对确认默认值，不瞎试（试错弹窗即事故）。

### R3 非空校验（每张拍完当场验，FAIL 重拍一次，再 FAIL 存盘转人工）

- 双指标：内容区（去标题栏）采样 distinct 颜色数 ＋ 深色像素数。
- 阈值不要拍脑袋：先写个 20 行探针，对"稀疏表单＋真空白"实测校准。
  参考口径（SunnyUI 无边框窗）：`distinct>=6 && dark>=8`；
  登录窗 28/16、录入框 13/12、项目切换 6/12 都是真图，真空白约 2~4 色/0~5 深色。
- 校验只是绊线不是法官：FAIL 的图照样存，事后人眼复核，不得静默丢图。

### R4 涉密截图打码（强制，2026-10 血泪：activation.png 设备ID/设备码明文入库）

- 涉密清单（三份文档一律打码，内部版也不留明文）：设备ID/设备码/激活码/
  商业授权码/机器码、HslLicense.dat 内容、外网IP/域名、客户真实数据
  （SN/批号/人名/电话/工单号）。不算涉密、不用打码：内网IP（192.168/10段）、
  演示数据、已用圆点掩码的密码框（如 license-view.png）。
- 手法（默认首尾各露4字、只糊中间，如设备ID"178B…0F01"）：输入框留约2px边框，
  工具：项目 `Tools/DocShot/blur_sensitive.py`，
  `python blur_sensitive.py <图> x0,y0,x1,y1 [--block 10] --keep 4`（自动分字：
  行带底色取众数，白底黑字与蓝选中底白字都成立；切分点落字间隙中点；
  超宽/杂色伪段自动过滤；空区/段数不够/太窄自动拒绝，此时改 --keep 0 整区糊，
  不要硬露；勿对已打码图重跑）。
  例外整区糊（--keep 0）：短字段、空框、拒绝保留时。框体保留，
  只杀中间可读性——截图仍是真图（R1），不是P图伪造。
- 定位框体：按边框色扫整行定上下界（灰框扫灰线、蓝聚焦框扫蓝线），
  再在框内行找左右边框，内区=外框各缩2px；小图（<500px）允许手估比例，
  事后放大验证兜底。打码坐标记进 harness 说明或任务记录，同窗体重跑直接复用。
- 验证：打码区裁出放大4倍，人眼确认纯色块、无字符笔画残留；
  放大图存临时目录、看完即删，不进仓库。判据：肉眼原图不可读＋放大图无残留＝通过。
- PDF同步：png 打码后三份 PDF 必须重转（PDF 内嵌的是旧图），重转后跑 check 全绿。
- 脚本判不了图：check_docs.py 只查文本禁词与引用配对，像素级涉密靠本节人工打码＋
  放大验证，别指望脚本兜底。

### 防卡住三层（无人值守必须有）

1. 关窗只 `Dispose` 不 `Close`：跳过全部 FormClosing 确认框
   （"有未保存先确认"类弹窗曾把流程卡到超时），截图不需要优雅关闭。
2. 看门狗线程（每 300ms）：扫描本进程意外弹窗（对话框类 `#32770`，
   或有 Owner 的 WinForms 窗，且不在"自己打开的"名单里），按
   "否/取消优先，否则确定/是，都没有则 WM_CLOSE"自动点掉并打印日志。
   前提：截图流程里不存在"必须人工点的模态框"，冒出来的任何模态都是事故。
3. 单张失败记数续拍，不整批陪葬；退出码 0＝全绿；全程无人值守超时设足
   （驱动状态机要几十秒，总超时按分钟计）。

### harness 落盘要求：固定路径铁律（skill 全局通用、harness 按项目沉淀）

- 路径固定：`<项目>/tools/DocShot/`，文件名固定：截图源码（如 `DocShot.cs`）＋
  说明（含编译命令、输出目录、R1/R2/R3 参数、校准表、防卡住配置、已知坑）＋
  通用脚本（`check_docs.py`、`md_to_pdf.py` 原样复用）。
- 有沉淀的项目：直接用，禁重写 harness；只允许改种子数据与截图名单，
  改完重跑＋核验。没有才新建，建完必须落盘到此路径（弱模型找 harness
  只认此路径，找不到上报人类，禁自己另起目录）。
- 说明里必须记：csc 编译含中文源码要 `/codepage:65001`；产物 exe 跑完即删，
  不污染 bin；运行时文件备份还原点。

## 四、写作红线（血泪）

2. **单次写入有长度上限**：超长内容会被静默截断，并在文件里留下一行
   `...[truncated NNNN chars]` 标记。万字文档必须分段追加
   （先写骨架，再多次小步替换尾标续写，每段 3~5KB），写完必须
   `grep truncated` 全仓扫一遍，有标记就是没写完。
1. **开篇禁引用块**：标题后直接进第一节，不写"看这篇的人/对象/目标"之类的
   开篇引用（包括对象说明、前置阅读、截图声明，一律不写）。
3. **语言分层**：操作员版不说术语（说"吸稳了再通电"，不说"真空确认＋延时开启"）；
   客户版给方法不给实现（"配多大"不说"存在哪个寄存器"）；内部版才给文件/函数级红线。
4. **每个操作都配图**：截图文件名与文档引用一一对应；拍漏的窗口宁可补拍，不用文字凑。
5. **截图即证据**：文档里写的按钮名、状态文字、数字，必须和截图里的一致；
   第二节差异矩阵里"绝不出现"的东西，写完 grep 自查（如客户版扫隐藏账号名、
   dev 专属页名与"开发者面板"等内部机制词——名单进 check_docs.py 禁词表兜底）。
6. **MES 分层写法（自助闭环，仅功能开关 ON 时写）**：开关 OFF 则客户版整节删
   （见§二⓪章节级门禁；删节后后面节号前移＋交叉引用全修＋内部版回指同步改），
   不许留"以后能用"的预告章。ON 时才按：操作员版只写"不用管＋保证批号/SN 扫对"（上报字段来自这两样）；
   客户版给完整自助链（要厂方拿 5 样 → Mock 对格式 → 开真发 → 配置字典 →
   字段词汇表 → 排障三步 → 何时找我方），不给源码文件级细节；
   内部版才写代码边界（哪 5 种情况必须改代码、改哪）；协议类参数字典与客户版
   自助章双向对账（两边例子的地址/字段名一致）。
7. **编码**：中文文档写完自查 UTF-8 可读（`ReadAllText(path, UTF8).Contains("预期中文")`）。

## 五、核验清单（收尾逐项打勾）

- [ ] 三份齐全，图片引用全部有文件，逐张人眼"非空＋内容对版"
- [ ] 三份 md 都有同名 pdf（>50KB），HTML 预览截图看过字体/图片/表格
- [ ] 文档目录无残留 html（转完即删，核验脚本 2c 兜底）
- [ ] 功能双向对账：矩阵里每个功能在对应文档有章节（右键/下拉入口逐个有，
  弹窗类功能逐个有截图），每章回指矩阵项；"需要 X 权限"章节无一句话带过
  （目标读者有该权限即展开）
- [ ] 全文档无 `truncated` 标记，超长文件分段复读过首尾
- [ ] 客户版无隐藏权限/内部工具/源码细节；演示数据注明是演示数据
- [ ] 权限对账：客户版每个操作章节的入口已 grep 确认该角色可达；按§一铁律三档分流——
  更高角色可达的只一句话认档（无步骤无图）；**dev 专属页在客户两版零出现**
  （页名/别名/开发者面板等内部机制词全不在，禁词门禁全绿；仅存不带功能名的
  兜底句＋"何时叫我方"场景）
- [ ] 硬件实配：系统组成/架构/硬件对照只写真机实配品牌，未启用品牌与禁用通道
  全不在客户两版（品牌门禁全绿；界面固定文案里的别家品牌正文不复述）
- [ ] 涉密截图已打码（三份一律，内部版也不留明文；打码区4倍放大无字符残留；
  PDF已重转，内嵌图与png一致）
- [ ] MES 自助闭环（仅开关 ON；OFF 则本项改为"客户版无此节＋节号连续"）：
  ON 时客户版照着能走完 Mock→真发（要 5 样/配置字典/
  字段表/排障三步/何时找我方齐）；协议参数字典与客户版例子一致；
  内部版"改配置够/必须改代码"边界明确
- [ ] README 定位表、CHANGELOG 小节、旧文档去留都已处理
- [ ] `git status` 确认范围：只有文档＋配图（＋harness 沉淀），无运行时数据、无机密、无 bin 产物
- [ ] 产品代码零改动 → 不跑回归；动了产品代码 → 按项目回归规范走

## 六、三份大纲模板（开工直接套，章节只增不减）

**操作员版**：软件一句话＋硬件对照（实配品牌）→ 开机登录 → 主界面四区 →
标准生产流程（分步，每步一图）→ 状态文字对照表 → 报警处置 →
易混按钮 → 配方红线 → 策略认档 → 历史查询 → 打不开的窗口
（只讲"打不开是正常的＋别信偏方绕开登录"，不点名不讲用途不配图，
见§一权限可达铁律） →
管理员入口 → 每班点检 → 禁忌清单。

**客户技术工艺版**：系统组成（实配品牌，禁堆全家桶，见§二⓪硬件实配） → 账号权限 → 主界面 → 换型清单 →
配方设计方法 → 策略选用 → 记录报表MES联调（仅功能开关 ON 时保留整节，
OFF 则整节删＋节号前移，见§二⓪；自助闭环：要厂方拿什么/两步走Mock先行/
配置字典/字段词汇表/排障三步/何时找我方；若配置页仅最高权限可达，
该功能按§一铁律第三档**整体零出现**，连自助链也不留） →
权限分档＋何时叫我方（只讲"存在仅我方工程师可操作的窗口"＋叫人场景，
不列页名单、不讲用途、不给步骤不配图，见§一权限可达铁律） →
系统设置管理员实操（分类逐项/改自己密码/报表列；dev 专属页如用户管理
绝不进此节） →
排障（现象/先查/何时叫售后）→ 自查。

**内部版**：系统全景（架构一句话＋文件归属）→ 权限矩阵（含隐藏账号）→
主界面 → 参数设置逐项 → 系统设置/测试窗口 → 授权开户续期全流程 →
工艺知识 N 条 → 排障手册（含升级开发条件）→ 交付维护清单 →
技术实现篇（编排/判定/通讯/账号/授权/MES/规则/存储，每节固定
"职责边界/关键机制/改动红线"三段，方法名寄存器公式与代码一致，
存疑 grep 不背；MES 节必写"改配置够的/必须改代码的"边界＋甩给客户的附件名）→
自查回炉（含技术自查）。

## 七、脚本化总览（弱模型按表执行，不许跳步、不许发挥）

第 0 步（新项目）：先填§十四适配清单（技术栈→截图手段、受众重定、禁词/trio 名单），
再进下表。禁跳过第 0 步直接套 WinForms 模板。

| 步 | 动作 | 用什么脚本/模板 | 输出物 | 红灯（停下修，不许继续） |
| :--- | :--- | :--- | :--- | :--- |
| 0b | 读配置（每次任务） | 软件当前配置＋项目料号配置（§二⓪），`check_config.py` 出矩阵 | 功能开关矩阵（开/关逐项）＋硬件实配品牌清单 | 不读配置不许定截图清单 |
| 1 | 盘点窗口清单 | §八探针式枚举：Dialogs/*.cs 构造签名＋菜单代码 | 截图清单（窗体/构造/截图方式） | 构造含设备依赖 → 记下走 R1 注入 |
| 2 | 校准非空阈值 | §九 MetricProbe 通用版，必跑 | distinct/dark 实测表＋阈值 | 不跑探针不许定阈值 |
| 3 | 写截图 harness | §十看门狗＋§十一定值源模板＋R1/R2 | harness 源码＋说明 | 无看门狗不许无人值守跑 |
| 4 | 跑 harness | 一次全跑，超时按分钟计 | PNG＋ALL PASS/FAIL 名单 | 有 FAIL 先看图再定是重拍还是调阈值 |
| 5 | 人眼核验 | 每张打开看（§五第④条） | 不合格名单→回第 4 步 | 空白/无数据图不许进文档 |
| 6 | 分段写文档 | §十二规程，每段 ≤4KB | 三份 md | 出一段验一段（复读尾 10 行） |
| 7 | 一键核验 | §十一 check_docs.py 全绿 | 终端输出 | 任一红灯修完重跑本脚本 |
| 8 | 转 PDF＋清 html | §十三 md_to_pdf.py 全绿＋HTML 预览截图人眼过＋删 html | 同名 pdf（>50KB），无 html 残留 | 缺 PDF 回第 8 步，布局错改 CSS 重转 |
| 9 | 同步周边 | README＋CHANGELOG＋旧文档去留 | git status 范围确认 | 范围外文件出现先查原因 |

弱模型三不许：不许一次写超 4KB（必被截断）；不许无看门狗跑 harness；
不许跳过人眼核验（脚本是绊线，人是法官）。

## 八、模板 1：非空校验探针（先校准再定阈值，20 行核心）

```csharp
// MetricProbe.cs：对"稀疏表单＋真空白"实测，输出 distinct/dark 定阈值。
// 编译：csc /t:exe /codepage:65001 /out:Probe.exe MetricProbe.cs
//   /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.dll
//   "/r:你的主程序.exe" "/r:依赖UI库.dll"  （含中文必须 /codepage:65001）
static void Probe(Form f, string name) {
    f.StartPosition = FormStartPosition.CenterScreen;
    f.Show(); Application.DoEvents(); Thread.Sleep(600); Application.DoEvents();
    RECT r; GetWindowRect(f.Handle, out r); // user32 GetWindowRect
    using (var bmp = new Bitmap(r.Right - r.Left, r.Bottom - r.Top)) {
        using (var g = Graphics.FromImage(bmp)) {
            IntPtr hdc = g.GetHdc();
            try { PrintWindow(f.Handle, hdc, 0); } // user32 PrintWindow
            finally { g.ReleaseHdc(hdc); } }
        var colors = new HashSet<int>(); int dark = 0, total = 0;
        for (int y = 60; y < bmp.Height; y += 7)      // 跳过标题栏
            for (int x = 0; x < bmp.Width; x += 7) {
                total++;
                Color c = bmp.GetPixel(x, y);
                colors.Add((c.R >> 4) << 8 | (c.G >> 4) << 4 | (c.B >> 4));
                if (c.R + c.G + c.B < 240) dark++; }
        Console.WriteLine(name + " distinct=" + colors.Count + " dark=" + dark);
    }
    try { f.Dispose(); } catch { }  // 只 Dispose 不 Close（防确认框，见§十）
}
// 必测项：最稀疏的表单、最满的表格、一个 new Form() 空白对照。
// 定值法：阈值取"最小真图的一半"与"空白对照的两倍"之间；
//   参考：distinct>=6 && dark>=8（真空白约 2~4 色/0~5）。
// 注意：原生有边框窗的 dark 含系统边框（空白对照 dark 虚高），
//   自绘无边框窗（SunnyUI 等）无此项，两种窗体分开校准。
```

## 九、模板 2：看门狗（防模态卡死，直接抄）

```csharp
//  P/Invoke: user32 EnumWindows/GetWindowThreadProcessId/IsWindowVisible/
//  GetWindow(GW_OWNER=4)/GetClassName/GetWindowText/EnumChildWindows/
//  SendMessage(BM_CLICK=0xF5)/PostMessage(WM_CLOSE=0x10)
static readonly HashSet<IntPtr> knownWindows = new HashSet<IntPtr>(); // 自己打开的
static volatile bool watchdogRun = false;
static void StartWatchdog() { // 主函数开头调一次；结束调 StopWatchdog()
    watchdogRun = true;
    var t = new Thread(() => {
        uint me = (uint)Process.GetCurrentProcess().Id;
        while (watchdogRun) { try { ScanPopups(me); } catch { } Thread.Sleep(300); }
    });
    t.IsBackground = true; t.Start(); }
static void ScanPopups(uint me) {
    EnumWindows((h, l) => {
        try {
            uint pid; GetWindowThreadProcessId(h, out pid);
            if (pid != me || !IsWindowVisible(h)) return true;
            lock (knownWindows) { if (knownWindows.Contains(h)) return true; }
            var cls = new StringBuilder(256); GetClassName(h, cls, 256);
            bool isPopup = cls.ToString() == "#32770" || GetWindow(h, 4) != IntPtr.Zero;
            if (!isPopup) return true;   // 自己开的主窗（无 Owner、非对话框类）不动
            var btns = new List<Tuple<IntPtr, string>>();   // 收集按钮文本
            EnumChildWindows(h, (ch, ll) => {
                var cc = new StringBuilder(256); GetClassName(ch, cc, 256);
                if (cc.ToString() == "Button") {
                    var tx = new StringBuilder(256); GetWindowText(ch, tx, 256);
                    btns.Add(Tuple.Create(ch, tx.ToString())); }
                return true; }, IntPtr.Zero);
            IntPtr target = IntPtr.Zero; string why = "WM_CLOSE";
            foreach (var b in btns)   // 非破坏优先：否/取消 > 确定/是 > 关窗
                if (b.Item2.Contains("否") || b.Item2.Contains("取消") ||
                    b.Item2.Contains("No") || b.Item2.Contains("Cancel"))
                { target = b.Item1; why = "click[" + b.Item2 + "]"; break; }
            if (target == IntPtr.Zero)
                foreach (var b in btns)
                    if (b.Item2.Contains("确定") || b.Item2.Contains("OK") ||
                        b.Item2 == "是" || b.Item2.Contains("关闭"))
                    { target = b.Item1; why = "click[" + b.Item2 + "]"; break; }
            if (target != IntPtr.Zero) SendMessage(target, 0xF5, IntPtr.Zero, IntPtr.Zero);
            else PostMessage(h, 0x10, IntPtr.Zero, IntPtr.Zero);
            var cap = new StringBuilder(256); GetWindowText(h, cap, 256);
            Console.WriteLine("WATCHDOG dismiss '" + cap + "' via " + why);
        } catch { } return true; }, IntPtr.Zero); }
// 关窗配套：Show 后把 f.Handle 登记进 knownWindows；结束只 f.Dispose() 不 Close()。
// 配套检查项：harness 全程不点"启动/保存/删除"类按钮（前提：截图不需要真动作）。
```

## 十、模板 3：定值仿真源（确定性演出，思想＋最小实现）

思想：随机 Mock 在高频采集下几十秒全员报警，演不出"正常/完成"。
定值源让每台读数恒定 → 好阈值走完正常流程，苛刻阈值首轮即报警，
短时长配方走完"已完成"，三态一次拍齐，全程可重复。

```csharp
// 实现该项目的设备读取接口，恒定返回"好数据"：
sealed class SteadyReader : I你的设备接口 {
    public bool Connect(Config c) { _connected = true; return true; }
    public Data ReadData(int id) {   // 每台恒定好值，无随机坏读数
        return new Data { 压力 = 好值, 开关量 = 到位, 时间 = DateTime.Now }; }
    // 其余批量读/写阈值照抄 Mock 返回成功即可。
}
// 演出布阵（以老化测试为例，其它业务照此思路布"正常/完成/故障"三态）：
//   A 组：正常阈值＋长时长 → 拍"进行中"；B 组：正常阈值＋短时长 → 等待→拍"已完成"；
//   C 组：苛刻阈值 → 首轮即报警 → 拍"故障"；D 组：保持空闲 → 拍"待投料"。
// 时序：启动 A/B/C → 轮询等 B 完成 → staggered 启动过渡态 → 先拍时效态。
// 落盘种子：调真实日志接口写 N 条（启动/报警/完成/判定各至少一条），
//   当天真实文件先备份、拍完还原并打印确认。
```

## 十一、模板 4：一键核验脚本（只保留 Python 单脚本，跨平台）

```python
# check_docs.py：放到项目侧（如 tools/DocShot/），每次收尾跑一遍。
# 单脚本原则：Python 本就是跨平台的，只维护一份，不做 ps1/py 双份
# （双份必分叉）。Windows 上直接 python 跑。
# （ps1 旧版已删。单脚本原则：双份必分叉，以下 Python 实现是唯一标准，直接抄走。）
# 图片涉密不靠本脚本判（像素级不可判定）：走§三R4人工打码＋4倍放大验证＋PDF重转。

#!/usr/bin/env python3
# check_docs.py —— 单脚本唯一标准（checks: truncated/refs/pdf/html/banned/
# dev-only 页名+配图/config-gate 集成/scope）
# 用法：python check_docs.py [docs目录] [images目录]
# （配置级门禁——功能开关矩阵＋硬件品牌实配——独立在 check_config.py，
#   由本脚本末尾 subprocess 调用集成，一处跑全绿；项目侧实现见本项目 tools/DocShot/。）
import os, re, subprocess, sys
DOCS = sys.argv[1] if len(sys.argv) > 1 else "docs"
IMGS = sys.argv[2] if len(sys.argv) > 2 else os.path.join(DOCS, "images")
fail = 0
def bad(msg):
    global fail; fail += 1; print("FAIL: " + msg)
def ok(msg): print("OK: " + msg)
texts = {}
for m in sorted(os.listdir(DOCS)):
    if not m.endswith(".md"): continue
    try:
        with open(os.path.join(DOCS, m), encoding="utf-8") as fh:
            texts[m] = fh.read()
        if not texts[m]: bad(m + " 空文件")
    except Exception as e: bad(m + " 编码异常: " + str(e))
if any("truncated" in t for t in texts.values()): bad("截断标记残留")
else: ok("无截断标记")
pat = re.compile(r"images/[A-Za-z0-9_.-]+\.(?:png|jpg)")
refs = sorted({m.group(0) for t in texts.values() for m in pat.finditer(t)})
for r in refs:
    if not os.path.isfile(os.path.join(DOCS, r.replace("/", os.sep))):
        bad("引用缺文件: " + r)
files = sorted(f for f in os.listdir(IMGS) if f.endswith(".png")) if os.path.isdir(IMGS) else []
for f in files:
    if ("images/" + f) not in refs: print("WARN: 无人引用 " + f)
ok("图片引用 %d 个，文件 %d 个" % (len(refs), len(files)))
for m in ["手册A.md", "手册B.md", "手册C.md"]:  # 按项目改 trio：md 必须有同名 pdf
    if m in texts:
        p = os.path.join(DOCS, os.path.splitext(m)[0] + ".pdf")
        if not (os.path.isfile(p) and os.path.getsize(p) > 50 * 1024):
            bad("缺 PDF 或过小: " + p)
ok("PDF 配对检查完")
leftover = [f for f in os.listdir(DOCS)  # html 中间件转完即删，不许残留
            if f.endswith(".html") and os.path.isfile(os.path.join(DOCS, f))]
if leftover: bad("html 残留未清: " + ",".join(leftover))
else: ok("无 html 残留")
for w in ["发码", "后门"]:  # 按项目改禁词表（子串匹配；操作员+客户两版一起扫）
    if [m for m, t in texts.items()
        if (m.startswith("操作员") or m.startswith("客户")) and w in t]:
        bad("客户两版含禁词[%s]" % w)
import re as _re  # 账号类禁词走词边界：本站字段 device 含 dev 子串，子串匹配会误杀字段表
for w in [r"\bdev\b"]:
    if [m for m, t in texts.items() if m.startswith("客户") and _re.search(w, t, _re.IGNORECASE)]:
        bad("客户版含禁词[%s]" % w)
# dev 专属页名禁词（正则，含别名；标题＋正文一起扫，客户两版零出现）：
# 仅我方最高权限账号可达的页面，客户不需要知道其存在（§一权限可达铁律第三档）。
# 名单按项目 grep 开发者面板/最高权限入口产出；加新 dev 页 = 此处加一词。
for w in [r"PLC\s*通讯测试", r"读码器测试", r"相机快测", r"开发者面板"]:
    if [m for m, t in texts.items()
        if (m.startswith("操作员") or m.startswith("客户")) and _re.search(w, t)]:
        bad("客户两版含 dev 专属页名[%s]" % w)
# dev 专属页配图门禁（引用即 FAIL，配图=暗示能打开）；名单与页名禁词同源产出
DEV_ONLY_IMGS = ["plc-test.png", "reader-test.png", "cam-quick.png"]  # 按项目改
for img in DEV_ONLY_IMGS:
    ref = "images/" + img  # 按项目改图片目录名
    if [m for m, t in texts.items()
        if (m.startswith("操作员") or m.startswith("客户")) and ref in t]:
        bad("客户两版含 dev 专属页配图[%s]" % img)
ok("客户两版禁词＋编码检查完")
# 配置级门禁集成（功能开关矩阵＋硬件品牌实配，check_config.py 独立维护）：
# 调不到/非 0 即 FAIL——本脚本 ALL PASS 必须包含配置门禁全绿，缺这个集成弱模型会漏掉
# "开关 OFF 整节删"与"品牌实配收敛"两道门（项目侧实现见本项目 tools/DocShot/）。
try:
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "check_config.py")],
        capture_output=True, text=True, timeout=60)
    print(r.stdout.strip())
    if r.returncode != 0: bad("check_config gate failed")
except Exception as e:
    bad("check_config gate error: " + str(e))
print(subprocess.run(["git", "status", "--short"],
      capture_output=True, text=True, timeout=30).stdout)
print("ALL PASS" if fail == 0 else "FAILURES=%d" % fail)
sys.exit(1 if fail else 0)
```

## 十二、分段写作操作规程（万字文档不被截断的唯一走法）

1. 先写骨架（标题＋每节一句话＋图片占位），一次 ≤4KB，写完复读确认结构。
2. 逐节扩写：每次只替换一个"待续锚点"（如 `<!--more-->`），新内容 ≤4KB；
   每追加一段，复读该段首尾 10 行，确认接上了、没吞字（Edit 工具多行替换
   会模糊匹配吞间隔行，大段只许覆盖已逐行核对过的连续行）。
3. 全部写完跑 §十一脚本第 1 项；再抽查两处"我写过但不记得原文"的段落复读，
   对不上就地重写。
4. 图片引用与文件在写作中同步加（§十一第 2 项兜底），不要最后统一配图。

## 十三、PDF 生成（md 定稿后一步到位，单脚本）

链条：`pip install markdown` → md 转样式 HTML（图片改绝对 file:// 路径）
→ 系统 Edge/Chrome 无头 `--print-to-pdf`。不用 pandoc / weasyprint
（Windows 装机成本高）/ Word COM（不可靠）。模板见项目侧 md_to_pdf.py
（参数：docs 目录/输出目录/md 名单，缺省转手册；.html 中间件保留预览）。

CSS 要点：中文字体栈（Microsoft YaHei / PingFang / SimSun）、表格边框＋
表头底色、图片 max-width:100%、`print-color-adjust:exact`
（否则表头底色打印丢失）、@page A4＋页边距、无头去页眉页脚。

两个坑（实测）：Edge 的 stderr 含非 GBK 字节，subprocess 必须按字节收再
utf-8 errors=replace 解码，否则 text=True 在中文机上炸读线程（PDF 本身正常）；
中文文件名控制台打印乱码不影响判定，只看 OK/FAIL/退出码。

核验（弱模型照做）：①脚本末尾 ALL PASS；②每个 pdf >50KB；
③截一张 HTML 无头 screenshot（`--screenshot --window-size=1100,900`）
人眼看字体/图片/表格，三者正常＝PDF 正常。核验脚本第 2b 项锁死
"手册 md 必须有同名 pdf"，忘转即红灯。

清理（铁律）：.html 只是中间件，预览核对完即删，文档目录不许残留。
md_to_pdf 成功后自删（`--keep-html` 仅调试保留）；核验脚本第 2c 项
"html 残留"红灯兜底。弱模型顺序：转 PDF → 截图预览 → 过 → 删 html →
跑核验，缺一步都不算完。
## 十四、新项目适配清单（换项目 10 分钟照填，不许直接套模板）

1. 技术栈→截图手段对照（照抄对应行，别自创）：
   - WinForms（.NET Framework）：本 skill 全套（PrintWindow/真屏/看门狗/C# harness）。
   - WPF：离屏渲染（RenderTargetBitmap，无需置顶抢屏）；模态卡死同看门狗思想
     （用 UI Automation 找弹窗点掉）；其余 R1/R3 照用。
   - Web 前端：Playwright 脚本逐路由截图（登录态用 storageState 复用；
     数据走测试账号＋种子 API，等于 R1）；弹窗用 auto-dismiss fixture。
   - Qt/C++：先找项目内截图能力，无则系统截图＋脚本摆窗；R1（种子数据脚本化）
     与 R3（非空校验）保留，看门狗按平台重写。
   - 无界面（库/服务/控制台）：截图章整体替换为"终端输出＋日志证据＋配置样例"，
     三份文档的图位改放等宽输出块与样例文件，check 脚本的图片项改为"引用块非空"。
2. 受众重定：三份是工业软件形态；先填"谁会读"（一线/客户技术/内部），
   再填权限模型（各角色登录方式＋谁能开什么，以入口代码 grep 为准），
   再套§一矩阵的行（权限/授权/工艺/排障/结尾），列不变，禁词重填。
   权限模型不清不许定章节（§一权限可达铁律：先有可达结论，再有章节）。
3. 名单重填：禁词表（隐藏账号/内部工具/密钥）、**dev 专属页名禁词 DEV_ONLY_PAGES
   （仅最高权限账号可达的页面：页名＋别名＋"开发者面板"等内部机制词，客户两版
   零出现，标题正文一起扫；与 DEV_ONLY_IMGS 配图门禁同源产出，先 grep 入口代码
   再填）**、**硬件品牌表（BRANDS_ALL 全集＋BRANDS_PRESENT 实配＋PLC_BRAND_MAP
   映射，禁词=全集−实配自动算出；无 ini 键的类别静态登记并注明证据）**、PDF trio 名单、
   图片目录名、
   权限门禁图名单（读者打不开的页面配图，DEV_ONLY_IMGS）、
   章节门禁表（禁用功能的章节标题关键词，CHAPTER_GATES；加新功能与 sw 开关一次配齐），
   进 check_docs.py / check_config.py 头部变量，一处改完。
4. 非空阈值必须重校准：§八探针跑新项目的"最稀疏表单＋空白对照"，
   禁沿用别项目的 6/8（字体/主题一变就失效）。
5. 弱模型分工线：强模型只做一次"搭 harness＋沉淀到项目 `tools/DocShot/` 固定路径"；
   弱模型日常只做重跑/写作/核验三步，找 harness 只认固定路径，
   有沉淀禁重写（只改种子与名单），无沉淀上报人类不硬造；
   技术篇每句贴源码证据（文件:行号），无证据的句子删掉；
   人眼核验必须由人或视觉模型做，纯文本弱模型只认脚本 ALL PASS，
   多余的一律转交人类抽查。

