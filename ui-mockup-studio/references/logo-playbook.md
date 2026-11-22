# logo-playbook — 软件图标（App Icon / Logo）设计手册

> 出界面设计稿时的标配延伸产物：**4-6 款矢量图标方案 → 用户选款 → 一键转项目资源**。
> 全程两个脚本：`svg2res.py preview`（生成选款预览页）+ `svg2res.py convert`（转 PNG 阶梯 + ICO）。
> 设计经验首刷来源：AIris（AI 智瞳）六款图标实战（2026-11-22）。

---

## 1. 交付流程（三步，缺一步都不算完）

| 步 | 动作 | 产出 |
| --- | --- | --- |
| ① 设计 | AI 画 4-6 款 SVG（128 viewBox，手算几何），**方案语义写在每款 SVG 的头注释 `<!-- -->` 里** | `<项目>/docs/branding/logo-<款名>.svg` |
| ② 选款 | 跑 `svg2res.py preview` 生成预览页 → 浏览器截图目检 → 用户选款 | `preview.html` |
| ③ 转资源 | 跑 `svg2res.py convert`（选中的款；用户要全套就 `convert-dir`） | 多尺寸 PNG + 多帧 ICO，项目直接可用 |

```powershell
# 预览页（离线单文件，浅/深底 × 48/32/20 阶梯；语义自动取 SVG 头注释）
python "<skill>/scripts/svg2res.py" preview "docs\branding" --out preview.html --title "XX 图标方案"

# 转资源：PNG 512/256/128/64/48/32/24/20/16 + ICO(16~256 七帧)
python "<skill>/scripts/svg2res.py" convert "docs\branding\logo-x.svg" "docs\branding\icons\logo-x"
python "<skill>/scripts/svg2res.py" convert-dir "docs\branding" "docs\branding\icons"   # 批量
```

**预览页必须截图目检后才交给用户**（几何是手算的，翻车只能靠眼睛抓——AIris 首刷就在
预览截图里抓出"雪花感/风车感"两款返工）。

## 2. 设计口径（与界面设计稿同源）

1. **底板 = 渐变圆角方**：`rect rx≈30/128（23%，iOS 风格）`，渐变取**当前选中方案的
   Token 色系**（如 C 方案 `#F59E0B→#F97316→#EC4899`）——图标与界面同源，用户一眼认亲。
   每款方案文件内定义独立 `<linearGradient id="gX">`（id 唯一，避免同页内联冲突）。
2. **符号 = 白色为主**：任务栏/开始菜单/16px 小图上白符号对深渐变底对比最强。
3. **语义 = 一个图形讲清产品核心动作**：优先「产品域符号 + 名字双关」组合。
   隐喻池参考：瞳孔/虹膜（视觉、AI 之眼）、取景框/检测框四角（锁定、识别）、光圈快门
   （相机、工业）、对话气泡+神经网络（自然语言驱动）、盾+眼（防错守护）、花瓣（名字
   双关的柔和表达）。按产品域选 2-3 个符号做乘法，不做加法。
4. **透底一律 evenodd 挖洞**：需要在符号上"露底板渐变"（瞳孔、眼白）时，把外轮廓与
   洞写进同一个 path 用 `fill-rule="evenodd"`——**禁止叠一个"近似底色"的圆盖上去**
   （渐变底上必露馅，色相错位一眼假）。

## 3. 几何红线（AIris 实战返工教训）

- **全部坐标手算就要渲染验收**：圆上弦线端点、旋转复制角度这些手算值，先在预览页
  截图看整体，不要信任"算出来应该对"。
- **警惕意外联想**：6 重放射对称 + 直线弦 ≈ 雪花 ❄；三瓣太瘦 + 瓣间点缀 ≈ 风车。
  出现"像别的东西"立即返工换画法（AIris：直线弦光圈改**扇形叶片**、瘦花瓣改饱满水滴瓣）。
- **小尺寸纪律**（128 viewBox 下的最小值）：主线条 `stroke-width ≥ 6`；四角括号角长
  ≥ 16；中心挖孔直径 ≥ 13；元素间留白 ≥ 5。20px 档（预览页阶梯）必须仍可辨识主形。
- **旋转复制用 `transform="rotate(a 64 64)"`**，同一 path 写 `<g fill>` 里复制多份——
  不要用 `<use>`（部分工具链 href 兼容性坑）。

## 4. 转资源后的项目接入 —— 换图标 = 换全（用户选定后必须逐项过）

**exe 文件图标 ≠ 运行窗口图标，是两件独立的事，都要设**（2026-11-22 AIris 换标实测沉淀；
只设 ApplicationIcon 时任务栏运行态仍显示通用 WPF 图标）：

| 面 | WPF 做法 | 验证方法 |
| --- | --- | --- |
| ① exe 内嵌（资源管理器 / 桌面快捷方式 / 任务栏固定） | csproj `<ApplicationIcon>Assets\app.ico</ApplicationIcon>` | PowerShell `[System.Drawing.Icon]::ExtractAssociatedIcon(exe)` 提取对比 |
| ② 运行窗口（任务栏运行态 / Alt-Tab / 窗口标题栏） | 主窗根元素 `Icon="/Assets/app.ico"`，且 csproj 必须 `<Resource Include="Assets\app.ico">`——**ApplicationIcon 不会自动成 WPF Resource**，缺这行 XAML Icon 运行时加载失败 | 启动 exe 后截图任务栏 32px 帧 |
| ③ 界面品牌位（顶栏 Logo / 登录页 / 关于框） | 原"通用占位字符（◉ / 圆环 Border）"必须一并换成同源矢量：Viewbox + Canvas 按转换前 SVG 同款几何画白符号（跟随主题色/渐变底，缩放无损），或 Image 引 Resource PNG | 截图目检品牌位 |

- **WinForms 对应**：项目属性 ApplicationIcon（面①）+ 主窗 `Form.Icon`（面②）+ 品牌位（面③）。
- **弹窗体系**：Kaleidoscope `ChromeDialogWindow` 标题条走 `TitleIconChar` 设计字形、不读
  Window.Icon 且弹窗不上任务栏/Alt-Tab——弹窗无需逐个设图标，别画蛇添足。
- **快捷方式**：桌面没有就顺手建一个（`WScript.Shell` CreateShortcut，用户验收面之一）；
  换标后旧快捷方式可能因 Windows 图标缓存仍显旧图——删除重建最稳，批量刷缓存才考虑
  `ie4uinit.exe -show`。
- **Web/favicon**：同一 `.ico` 改名 `favicon.ico` 放站点根即可（多帧 16/32/48 已含）。
- **README/文档配图**：用 `_<size>.png` 阶梯（256/128 展示，20/16 只作验收证据）。
- 产物目录建议：`docs/branding/`（SVG 源 + 预览页）与 `docs/branding/icons/<款名>/`（转换产物）；
  未选定的候选款资源一并生成无妨（用户选完只留一款，其余随下次清理）。

## 5. 转换工具链说明（svg2res.py 实现，改它之前必读）

- **渲染器 = Edge headless**（Chromium 内核 SVG 支持完美、Windows 每台都有、零安装）：
  只渲一张 512px 高清（`--window-size=128,128 --force-device-scale-factor=4`，SVG 根有
  width/height 时；只有 viewBox 时窗口=输出尺寸），其余尺寸全 PIL LANCZOS 缩——
  逐尺寸截图慢一个数量级且质量无增益。
- **实踩坑**：Edge 截图必须带 `--user-data-dir`（临时目录）否则不落盘；
  `--default-background-color=00000000` 保透明底；SVG 根缺 width/height 也缺 viewBox 会报错拒绝转换。
- **ICO 打包 = PIL**：`img.save(path, format="ICO", sizes=[(16,16)…(256,256)])`，源必须 RGBA。
- 依赖：`pillow`（convert 用；preview 不需要）。本机已具备，无需另装渲染器
  （resvg/inkscape/magick/cairosvg 在本机均不可用，不要绕路）。
