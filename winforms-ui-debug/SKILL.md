---
name: winforms-ui-debug
description: 跨项目 WinForms/.NET Framework + SunnyUI 界面像素级调试与深色模式换肤：编译独立 harness 指哪打哪直启目标窗体（绕过登录/主流程），反射探私有字段 + PrintWindow/真实截图 + 像素扫描定位根因并验证修复；深色/浅色主题换肤的坑位总表与新界面一步到位清单。用户提到界面竖线/横线/颜色不对/叠色/裁剪/滚动条/DPI 缩放/控件错位遮挡、深色模式/换肤/主题，或点名具体窗体/页面时使用。沉淀多项目血泪与可复用脚本（矩形枚举/置顶截图）。
---

# WinForms 界面像素级调试（指哪打哪）

本技能沉淀"编译并直接启动指定窗体 + 像素探针"的调试套路，是 WinForms/SunnyUI 界面 bug
定位最快的方式：**不改主程序流程、不进登录页，直接 new 出目标窗体来观察**。适用于所有
WinForms/SunnyUI 渲染问题（分割线、颜色、裁剪、DPI、滚动条、对齐、遮挡错位）。

适用项目见附录 A（AgingTestSystem / CommandCenter / HuaJiVision / Kaleidoscope，
构建命令与 bin 目录各不相同，**开工先查附录 A 拿本项目三件套**）。

> 开工前先读本项目的 `AGENTS.md`（文件编码 UTF-8、改后必构建、文档同步等红线全部适用）。

## 一、总流程

```
1. 构建项目（拿到最新的 exe + DLL）
2. 写独立 harness（.cs）→ 用 csc 编译成一个小 exe
3. 运行 harness：直接 new 目标窗体并 Show
4. harness 内用反射读私有字段、打印几何、像素扫描 / PrintWindow 截图
5. 定位根因 → 改代码 → 重新构建 → 重跑 harness 对比 before/after 像素
6. 冒烟测试主程序 + 更新本项目 CHANGELOG（+ 必要时 README/docs，按本项目约定）
```

## 二、构建与 harness 编译命令

### 1. 构建主项目

```powershell
& "D:\Program Files\Microsoft Visual Studio\18\Enterprise\MSBuild\Current\Bin\MSBuild.exe" <项目csproj相对路径> /p:Configuration=Debug /p:Platform=AnyCPU /t:Build /nologo /v:m
```

构建产物在 `<bin>`（exe + 全部依赖 DLL）。**每次改完代码都必须重新构建再跑 harness**，
否则 harness 引用的是旧 exe。`<项目csproj相对路径>` / `<bin>` / 主 exe 名见附录 A
（各项目不同；HuaJiVision 的输出是运行目录 `00_ExeBuild\` 而非 `bin\Debug\`，别套错）。

### 2. 编译 harness（关键命令，可复用）

```powershell
$bin = "<附录A的bin绝对路径>"
& "D:\Program Files\Microsoft Visual Studio\18\Enterprise\MSBuild\Current\Bin\Roslyn\csc.exe" `
  /nologo /t:exe "/out:$bin\UiProbe.exe" "C:\Users\ADMINI~1\AppData\Local\Temp\opencode\UiProbe.cs" `
  /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.dll `
  "/r:$bin\<主exe>" "/r:$bin\<依赖DLL1>" "/r:$bin\<依赖DLL2>" ...
```

依赖 DLL 清单见附录 A（缺哪个 `/r` 哪个，编译报错会告诉你）。

要点：
- 编译报错只看 `error CS` 行（`2>&1 | Select-String -Pattern "error CS"`）。
- `$?` 为真才运行 exe：`if ($?) { Push-Location $bin; & ".\UiProbe.exe"; Pop-Location }`。
- 若 `Roslyn\csc.exe` 找不到，用 `Get-ChildItem 'D:\Program Files\Microsoft Visual Studio' -Recurse -Filter csc.exe` 定位。
- **harness 源码放临时目录**（`C:\Users\ADMINI~1\AppData\Local\Temp\opencode\`），产物放 bin/输出目录（gitignore，不污染仓库）。调试完记得删掉 bin 里生成的 `UiProbe*.exe`。

## 三、harness 通用骨架（直接改目标窗体）

```csharp
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Windows.Forms;

static class UiProbe
{
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    static extern bool SetProcessDPIAware();

    [STAThread]
    static void Main()
    {
        SetProcessDPIAware();          // 关键！不设的话渲染结果 ≠ 真实程序（DPI 会不同）
        Application.EnableVisualStyles();
        var config = new YourNamespace.Models.YourConfig();      // ① 换成目标窗体真实依赖
        var form = new YourNamespace.Dialogs.TargetForm(config); // ① 换成目标窗体
        form.StartPosition = FormStartPosition.CenterScreen;
        form.Show();
        Application.DoEvents();
        System.Threading.Thread.Sleep(400);   // 等首帧画完
        Application.DoEvents();

        // ② 反射拿私有字段（表格、面板等）
        var f = typeof(YourNamespace.Dialogs.TargetForm)
            .GetField("_grid", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        var grid = f.GetValue(form) as DataGridView;

        // ③ 打印几何（帮理解布局/坐标系）
        Console.WriteLine("Form=" + form.ClientSize + " Grid=" + grid.ClientSize + " DisplayRect=" + grid.DisplayRectangle);
        foreach (DataGridViewColumn col in grid.Columns)
            Console.WriteLine("Col " + col.Name + " W=" + col.Width + " Auto=" + col.AutoSizeMode);

        form.Close();
    }
}
```

### 如何"指哪打哪"启动任意窗体
- 打开目标窗体的 `.cs`，看构造函数签名（例：`SettingsForm(DeviceConfig)`、`RecipeManagerForm()`、`mFormScriptEdit()`）。
- 构造所需依赖：大部分窗体直接 `new`；若依赖配置类 / 用户管理类 / 主窗体引用，用反射或 `new` 现造的实例传进去。
- 不是主窗体的对话框类，直接 `new + Show()` 就能独立运行。

## 四、三大调试工具（本技能核心）

### 1. PrintWindow 整窗截图（默认手段，与屏幕位置无关）

`Screen Capture / CopyFromScreen` 在"窗体被居中到非标准分辨率 / 半屏外"时会得到错位、
裁剪、甚至不可复现的像素数据（踩过坑）。**整窗截图默认用 PrintWindow**，它渲染完整窗口
（含标题栏/边框），输出位图坐标 = 窗口坐标，稳定可复现：

```csharp
[DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
struct RECT { public int Left, Top, Right, Bottom; }

static Bitmap CaptureWindow(Form form)
{
    RECT r; GetWindowRect(form.Handle, out r);
    var bmp = new Bitmap(r.Right - r.Left, r.Bottom - r.Top);
    using (var g = Graphics.FromImage(bmp))
    {
        IntPtr hdc = g.GetHdc();
        PrintWindow(form.Handle, hdc, 0);
        g.ReleaseHdc(hdc);
    }
    return bmp;
}
```

> 例外（Kaleidoscope 沉淀）：SunnyUI 自绘控件在 `WM_PRINT` 下可能渲染不全
> （只画顶部一条，产生"控件被裁"假象），WPF ElementHost 内容 `f=0` 截出来空白
> （必须 `f=2` 即 `PW_RENDERFULLCONTENT`，见坑 17）。这类情况改用§十一的
> "TOPMOST 置顶 + CopyFromScreen 真实截图"，三者选用关系见§十一末尾。

### 2. grid 客户区坐标 → PNG 位图像素坐标映射

DPI 感知进程里 `GetCellDisplayRectangle`/`GetRowDisplayRectangle` 返回的可能是**物理像素**，
且窗口有边框偏移，不能直接当 PNG 坐标用。正确换算：

```csharp
static Point GridToPng(Form form, DataGridView grid, Bitmap bmp, int gx, int gy)
{
    RECT win; GetWindowRect(form.Handle, out win);
    Point clientOrigin = form.PointToScreen(Point.Empty);   // 客户区原点(屏幕)
    Point gridOrigin  = grid.PointToScreen(Point.Empty);    // grid 客户区原点(屏幕)
    Rectangle scrGrid = grid.RectangleToScreen(grid.ClientRectangle);
    double scale = (double)scrGrid.Width / grid.ClientSize.Width;   // DPI 缩放（150% 时 = 1.5）
    int px = (int)Math.Round((gridOrigin.X - clientOrigin.X) + gx * scale) + (clientOrigin.X - win.Left);
    int py = (int)Math.Round((gridOrigin.Y - clientOrigin.Y) + gy * scale) + (clientOrigin.Y - win.Top);
    return new Point(px, py);
}
```

### 3. 像素扫描找"线"（定位竖线/横线/叠色的颜色与坐标）

沿一条水平线逐像素 `bmp.GetPixel(x,y)`，按颜色特征找线：
- 先打印整段色值（`x:R,G,B`），**用颜色值反推来源**：不同颜色 = 不同绘制者
  （AgingTestSystem 实测例：cell border=GridColor `104,173,255`，滚动条左线=`80,160,255`，
  标题蓝=`48,119,238`——你的项目第一次用时同样扫一段建自己的色值字典）。
- 再扫多行 y（行 top/mid/bot），确认是"整行贯穿"还是"局部"，区分竖线/横线/文字像素。
- 用已知控件属性值做色值字典（`Color.FromArgb(...)` 与屏幕采样比对），快速锁定是谁画的。

### 4. 改像素前先读几何（一次命中的关键）

遇到"某处要不要有竖线/横线、线画在哪"这类问题，**先反射打印布局几何 + 扫描色值，
用几何推导出绘制坐标，再改代码**，往往一稿就过。比"改了→看→再改"的试错快得多。
**而且一定要打印真实尺寸，别信代码注释里的硬编码值**（踩坑 8）。

示例思路链（AgingTestSystem 工位网格"数据行最右边缘要有竖线、分组标题行不要"，
数字是该项目实测，方法通用）：

```csharp
// 1) 容器与边界真实几何（反射私有字段）
Console.WriteLine("pnlScroll.Padding=" + pnlScroll.Padding);          // 实测 Left=18，注释写 12 是错的！
Console.WriteLine("DisplayRect=" + grid.DisplayRectangle);           // 内容可视区
Console.WriteLine("CellBorderStyle=" + grid.CellBorderStyle + " GridColor=" + grid.GridColor);
// 2) 找盖在表格右边缘的滚动条子控件，这是"视线终点"
var sc = grid.Controls.OfType<Sunny.UI.UIScrollBar>().FirstOrDefault();
Console.WriteLine("UIScrollBar Bounds=" + sc.Bounds + " ShowLeftLine=" + sc.ShowLeftLine); // X=1377 W=27
// 3) 最后一列逻辑右边缘（即"想画线的位置"）
var cr = grid.GetCellDisplayRectangle(grid.Columns.Count - 1, 0, false);
Console.WriteLine("lastCol cell0=" + cr);                            // Right=1378
// 4) 推导：scrollBar 从 1377 起盖住 1377~1404，所以 cell.Right(1378) 不可见，
//    数据行"可见的最右像素"= scrollBar.Bounds.Left - 1 = 1376 ← 竖线就画这
// 5) 扫描该行带前后各 10px 确认底色（这一步是"验证候选坐标"而不是"找 bug"）
```

**通用推导口诀**：被子控件遮住的像素别去画——`可见最右 x = 子控件.Bounds.Left - 1`，
`可见最下 y = 子控件.Bounds.Top - 1`。拿到这个 x 再决定画线的颜色（跟 `GridColor`
或对应 cell border 一致，避免另造新色）。

## 五、本技能沉淀的坑（下次直接避）

（1〜12 条三项目共有，坐标/色值是 AgingTestSystem 实测；13 条起按来源标注，
详述见六〜九节或项目案例。）

1. **Child 控件永远画在父内容之上**：SunnyUI `UIDataGridView` 内置一个 `UIScrollBar` **子控件**盖在表格右边缘（最后一列右边界 ~ 表格右边界）。它默认 `ShowLeftLine = True`，在 X=918 画一条 `80,160,255` 竖线贯穿每一行——分组标题行最右侧的"竖线"真凶就是它。**任何 RowPostPaint / CellPainting / 覆写 OnPaint 都压不过子控件**；正解是找到子控件改属性（`grid.Controls.OfType<Sunny.UI.UIScrollBar>().First().ShowLeftLine = false;`）。
2. **RowPostPaint 的 Graphics 被裁剪在行显示矩形内**：`e.Graphics.ClipBounds` 打印确认。想覆盖 cell border 画到 `_grid.Width+1` 是没用的——超出裁剪的部分画不上。别在"覆盖宽度差 1px"上反复纠结，先确认那个"线"到底是谁画的。
3. **逻辑像素 vs 物理像素（DPI）**：150% 缩放下 1 逻辑像素对应 1.5 物理像素，border 落在半像素上会被渲染到某个物理像素，颜色可能与你预期不同。**harness 必须 `SetProcessDPIAware()`**，否则渲染路径都不一样，探针结果不可信。
4. **Screen Capture 不可靠，用 PrintWindow**：`CopyFromScreen` + 居中窗口在多显示器/窗体超屏时像素错位、时有时无，浪费大量时间。整窗截图默认 PrintWindow（例外见§四.1 注与§十一）。
5. **Color 值是最强的线索**：同一列边框是 `104,173,255`、滚动条左线是 `80,160,255`、滚动条轨道 `243,249,255`、表格背景 `237,243,253`、数据行背景 `243,249,255`（AgingTestSystem 实测字典，你的项目照§四.3 建自己的）。像素颜色不匹配 ≠ 你改的那个对象，先反查绘制来源再动手。
6. **验证 DPI 与"行是否真的被扫到"**：探针 y 取错位置会得出"没线"的假结论。用 `grid.GetRowDisplayRectangle(i,false)` + `RectangleToScreen` 映射后再取 y，别凭肉眼估。
7. **cell 逻辑右边缘 ≠ 可见最右像素**：SunnyUI UIDataGridView 的 `UIScrollBar` 子控件（Bounds.X=1377, Width=27）会盖住最后一列（colValue）右边缘 1~27px。所以 `GetCellDisplayRectangle(...).Right`（=1378）那个像素你是画不上/看不见的；想给数据行画"表格右边界竖线"，X 要取 `scrollBar.Bounds.Left - 1`（=1376）。**别把线画进子控件地盘**。
8. **代码注释里的硬编码坐标可能是错的，以实测为准**：例如 `Grid_RowPostPaint` 注释写"pnlScroll.Padding.Left=12"，实测却是 **18**；注释写"滚动条线在 X=918"，那只是当时窗口宽度的值。调试/改布局时，先反射打印 `Padding`/`Bounds`/`DisplayRectangle` 等真实值，再决定画在哪。自己写注释时也标注"实测"值。
9. **"某行有、某行没有"这类需求，用行号集合分流，不要另开事件**：需在 RowPostPaint 里给普通数据行画线、给分组行不画时，直接复用已有的 `_groupRows`（行号集合）做分支：`if (!_groupRows.Contains(e.RowIndex)) { 数据行逻辑; return; } else { 分组行逻辑; }`。既不动行样式、也不用区分事件，一次画绘里处理两类，可读性好。
10. **善用"批量纵向扫描多行"一次性确认规则**：改完"按行分支画线"后，harness 里循环前 N 行（`for r in 0..13`）对固定 X 取色，对照行号集合打印 `行号 [GROUP|data] 色值`，能一眼确认"分组行=浅蓝、数据行=线色"全部命中，比单看两行更稳。
11. **纯代码窗体的 AutoScale 不生效 = 99% 缺 `SuspendLayout()`**（V1.58.4 血泪）：只设 `AutoScaleMode.Font` + `AutoScaleDimensions` 不够，未挂起布局时逐次 `Controls.Add` 会把 AutoScaleDimensions 固化当前 DPI 值（144 DPI 下 6×12→9×18），缩放因子恒 1。验证时先看 `form.AutoScaleDimensions` 构造后是不是还是 6×12，被改成 9×18 就是缺 SuspendLayout。
12. **测 AutoScale 缩放必须用 PerMonitorV2 harness**：只 `SetProcessDPIAware()` 是 System-aware，AutoScaleDimensions 自动按当前 DPI 初始化，永远测不出缩放（假结论）。csc 编译带 `/win32manifest:pmv2.manifest` + bin 里放同名 `.exe.config`（`DpiAwareness=PerMonitorV2` 开关）才走真路径；对照 Designer 窗体能缩放即证明环境正确（对照窗体见附录 A）。
13. **禁窗口缩放：`Maximized` 是最大的坑，改用手动铺满 `WorkingArea`**（AgingTestSystem/CommandCenter 共有，V1.11.0 CommandCenter 沉淀，详见§六）。
14. **WinForms 点击/双击生效，先问"真实命中谁 + 冒不冒泡"**（AgingTestSystem/CommandCenter 共有，V1.12.15 CommandCenter 三轮血泪，详见§七；CommandCenter 案例：`Controls/CameraDisplayControl.cs` 的 `HandleDoubleClick`）。
15. **DataGridView ComboBox 列选中行高亮**（CommandCenter 独有，V2.15.22 血泪，详见§八；案例控件 `dgvPrograms`）。
16. **`AutoSize=true` 的 CheckBox 在高 DPI 下会膨胀，压住旁边按钮**（HuaJiVision 独有，V4.3.2 血泪）：checkbox 会按当前 DPI 字体**重新测量文本**（1.125 倍缩放下"调试模式"从 83px 膨胀到 116px），而固定尺寸按钮随窗体 AutoScale **线性**缩放，两者膨胀率不一致 → 高 DPI 下 checkbox 右边缘盖住相邻按钮（实测重叠 21px，用户反馈"调试模式被挡住"）。**修法：`AutoSize=false` + 固定 `Size`**（固定宽度后 checkbox 与按钮同样按 AutoScale 因子线性缩放，间距等比保持）。验证用 PrintWindow 扫顶栏 y 中线的颜色段，checkbox 深色背景应止于按钮深色背景之前，再反射打印 `chk.Right` 与 `bt_Continue.Left` 确认 `overlap<0`。
17. **WinForms+WPF ElementHost 混合窗体 harness 要点**（HuaJiVision 独有；案例窗体 `mFormScriptEdit`）：WPF 程序集（WindowsBase/PresentationCore/PresentationFramework/System.Windows.Presentation/WindowsFormsIntegration）在 GAC `$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\WPF\` 下，csc 引用要写全路径；WindowsFormsIntegration.dll 不在 bin 而在这同目录。PrintWindow 截混合窗体必须 `f=2`（PW_RENDERFULLCONTENT），否则 WPF 内容空白。DPI 缩放后控件 Bounds 是逻辑值，像素扫描要加 `offX/offY = PointToScreen(Point.Empty) - GetWindowRect.Left/Top` 偏移。
18. **ElementHost 混合窗体：给编辑器绑 Ctrl+F 等快捷键必须绑在 WPF 层，别只靠 WinForms `KeyPreview`**（HuaJiVision 独有，V4.3.4 血泪）：用户点进代码区后焦点在 WPF 内部窗口（`GetFocus()` 类名是 `HwndWrapper[xxx.exe;;...]`），WinForms 键消息链**根本不触发 KeyPreview**，Ctrl+F 被吃掉。正解双保险：①焦点在编辑器时用 `editor.InputBindings.Add(new KeyBinding(RoutedCommand, new KeyGesture(Key.F, ModifierKeys.Control)))` + `editor.CommandBindings.Add(new CommandBinding(cmd, (s,e)=>ShowSearchBar()))`（WPF 层，用独立 `RoutedCommand` 不冲突）；②焦点在右侧 WinForms 控件时保留窗体 `KeyPreview`+`KeyDown`。两者都需。**另外**：AvalonEdit 自带 `SearchPanel`（WPF Adorner）在 ElementHost 下 `Reactivate()` 显示不可靠（实测呼不出），自研 WinForms Dock=Top 的 `panel_Search` + `Visible` 切换最可控。
19. **harness 里验证模态 ShowDialog 窗体**（HuaJiVision 独有，V4.3.4 + V4.7.3 两轮沉淀，本条是合并版）：主线程调 `OnDoubleClick`→`ShowDialog` 会一直阻塞，两种可靠手段二选一：①**物理按键法**：必须先点击一次激活窗口、再点击一次聚焦（"点击未激活窗口首次只激活不给焦点"是 Windows 行为），验证 WPF 层快捷键必须用 `keybd_event`（SendInput）模拟物理按键，**不能用 `PostMessage`**（跳过 TranslateMessage/输入预处理，WPF 不识别修饰键组合 → 假阴性；实测 keybd 路径 `[4] PreviewKeyDown=True, panel.Visible=True`）；`SendKeys` 在有完整 `Application.Run` 消息循环时可用，`DoEvents` 泵消息不够。②**线程池 Timer 法**：用 `System.Threading.Timer`（线程池线程）延时后按类型找到模态窗体 → `PrintWindow` 截图（GDI 截图可跨线程）→ `BeginInvoke(Close)` 关掉，主线程即从 ShowDialog 返回。Timer 回调里别用 DoEvents（那是 UI 线程 API）。
20. **"选中紫框被浅色边框包住" = 系统非客户区边框，不是业务控件**（HuaJiVision 独有，V4.7.2 血泪）：深色主题下窗体获焦高亮已有，但用户看到最外缘还有一圈"黄色/浅色边框"把紫框包在里面。**根因是 `FormBorderStyle=Sizable` 的系统边框本身**：标题栏纯白(255,255,255)、左右外缘黑阴影+深灰细线，深色主题下这圈浅色系统边框就是用户眼中的"黄边"。**定位套路**：先打印 `winRect vs clientScreen` 算 `border`（Sizable 实测 8x31），再扫描 `y=1..30` 标题栏全白、`x=0..6` 黑阴影、`x=7` 深灰 → 确认非客户区；同时扫标题栏左上角 `x=17..30/y=8..21` 会看到金色+蓝色窗体图标（`252,203,59`/`122,175,224`），**那是应用图标不是边框，别误判**。
21. **无边框窗体（FormBorderStyle=None）+ 自绘标题栏的标准做法**（HuaJiVision 独有，V4.7.2 落地，可照抄）：①窗体 `Padding=3` 露出的窗体背景色就是"最外层边框"，获焦置紫/失焦置主题底色即可实现"窗体级选中边框"；②自绘标题栏 `Panel Dock=Top 高30` + 文字 Label(Fill) + ✕/— 按钮(Dock=Right 宽40)，**在构造函数里最后 `Controls.Add(_titleBar)`**（z-order 最前 → Dock 布局先占最顶部）；③**固定定位的容器（如 `Location=(0,46)` 的 splitContainer）要改成 `Dock=Fill`**，否则不随 Padding 避让、会盖住 3px 边框区；④拖动/缩放靠 `WndProc(WM_NCHITTEST=0x0084)`：边缘 6px 返回 HTLEFT=10/HTRIGHT=11/HTTOP=12/HTBOTTOM=15/四角 13/14/16/17，标题栏空白区返回 `HTCAPTION=2` 交给系统拖动；⑤**关闭/最小化按钮矩形必须从 HTCAPTION 命中里排除**（`_btnClose.Bounds.Offset(_titleBar.Left,_titleBar.Top)` 转窗体客户区坐标后 `Contains` 判断），否则点按钮变拖动、收不到 Click；⑥WM_NCHITTEST 的 LParam 取坐标要防负值：`(short)(lParam & 0xFFFF)` / `(short)((lParam>>16)&0xFFFF)`。**验证**：改造后打印 `border=0x0`（系统边框消失），获焦扫 `x=0/1/2`、`x=W-1/W-2`、`y=0..2`、`y=H-3..H-1` 全列=紫(155,109,255)，失焦后紫色像素数=0、恢复 `37,37,38`，重新聚焦紫框恢复。
22. **多个 Dock=Right 按钮的排列顺序：后 Add 的占最右**（HuaJiVision 独有，V4.7.2 实测）：WinForms 的 Dock 布局从 Controls 集合末尾往前处理，所以 `Controls.Add` 顺序反过来决定左右位置——要让按钮从右到左排成 `✕ □ —`，添加顺序必须是 `_btnMin → _btnMax → _btnClose`（关闭最后 Add 才贴最右）。别想当然"先 Add 的靠右"。probe 反射读 `btnClose/btnMax/btnMin.Bounds` 验证：`btnClose.Right==titleBar.Width && btnMax.Right==btnClose.Left && btnMin.Right==btnMax.Left`。
23. **无边框窗体最大化会盖住任务栏，必须 WM_GETMINMAXINFO 限制工作区**（HuaJiVision 独有，V4.7.2 实测）：无系统边框的窗体 Maximized 默认铺满整屏（含任务栏，实测 1920x1080，工作区只有 1920x1040）。在 `WndProc` 拦截 `WM_GETMINMAXINFO(0x0024)`：`Marshal.PtrToStructure<MINMAXINFO>(m.LParam)` → `ptMaxSize=WorkingArea.Size`、`ptMaxPosition=WorkingArea.Location` → `Marshal.StructureToPtr` → `m.Result=IntPtr.Zero`。MINMAXINFO 字段顺序必须与 Win32 完全一致（ptReserved/ptMaxSize/ptMaxPosition/ptMinTrackSize/ptMaxTrackSize），错一位最大化尺寸就乱。验证：最大化后 PrintWindow 尺寸应== `Screen.PrimaryScreen.WorkingArea.Size`。
24. **运行时 `new` 的 Form/控件 `Name` 默认是空串**（HuaJiVision 独有，V4.7.3 实测）：`Application.OpenForms["类名"]` 靠 Name 索引，非设计器创建的窗体永远找不到（假阴性，还容易误判成"窗体没打开"）。**按类型遍历**：`foreach (Form f in Application.OpenForms) if (f is TargetPopup) {...}`。
25. **"构造函数里启动后台加载 + BeginInvoke 回 UI"的窗体，首次加载必须放 OnShown**（HuaJiVision 独有，V4.7.3 实测，症状=窗体打开后内容区一片空白/背景色）：构造时窗体句柄尚未创建，后台线程几毫秒就完成加载，回调里 `IsHandleCreated==false` 走丢弃分支（图片直接 Dispose），之后句柄创建了也没人再加载。修法：构造函数只 BuildUi，`OnShown` 里调首次加载（ShowDialog 也会触发 Shown，模态同样适用）。
26. **PictureBox `SizeMode=Normal` 不缩放图像**（HuaJiVision 独有，V4.7.3 实测，症状=设置了 Size=原图×zoom 但图片永远原始尺寸一小块）：Normal 模式 Image 永远按原始像素绘制在左上角，控件 Size 只影响裁剪和滚动范围。手动"缩放+AutoScroll 滚动"方案要用 `SizeMode=StretchImage`（图像拉伸填满控件表面=显示尺寸即 Size），配合 `Size=原图×zoom` 才是完整缩放。
27. **父容器 Paint 里画的装饰会被子 Label 盖住**（HuaJiVision 独有，V4.7.3 实测）：Label 重绘时用父背景色填自身矩形（视觉不透明），Panel.OnPaint 在其下画的图标/色块被盖。装饰要么画进 Label 自己的 `Paint` 事件（配合 Label.Padding 留出空白区），要么别在该区域放 Label。
28. **TableLayoutPanel 固定列的高 DPI 余量 + 单行输入框余量 + 假绿探针三连坑**（HuaJiVision 独有，V4.4.7 实测，症状=150% 下顶行标签换行、授权码单行装不下，96DPI 全正常）：①**固定列余量按 96DPI 实测修必复发**——"打码机："需 56px 给 70px（余 14）、"台数："需 44px 给 54px（余 10），线性推算 150% 下格宽×1.5、字体×1.43~1.48（一次性 harness 实测 Consolas/微软雅黑）似乎更宽松，但真机 144DPI 字体渲染非线性仍吃掉余量换行。修法：顶行小列各加 12px（余量 26/22），24px 由弹性列吸收（右对齐标签 96DPI 下仅左留白稍增无感）；另给易换行标签加 `AutoEllipsis=true` 作保险（宁可单行省略号，不让换行把第二行截半）。②**单行 TextBox 余量 <15px 即高危**——36 位授权码（Consolas 9.5pt 实测需 259px）对文本区（ClientW−眼睛宽−2）270px 只剩 11px，150% 下必滚。修法：窗加宽 40（560→600），输入框 296→336（余量 51，150% 下约 100），右缘与标题右端仍对齐；回归用假 36 位串量长度，不碰真实授权码明文。③**`PerformAutoScale(SizeF,SizeF)` 反射模拟是假绿**——.NET Framework 的 `ContainerControl` 根本没有该重载（只有 `bool,bool`），传 SizeF 必抛 `ArgumentException`，又被外层 catch 吞掉且未置失败标志，150% 断言从未执行却 PASS。修法三件套：改用"1.5x 字体实测 need150 vs 1.5x 格宽"（`new Font(f.FontFamily, f.Size*1.5f)` 量 need，比格宽×1.5），另锁 96DPI 余量阈值（标签≥20/15、输入区≥30），catch 里必置失败；上线前做反向验证（暂回旧尺寸重建，新探针必须精准 FAIL 报 slack 值）。

29. **Sunny UIForm 客户区顶部 35px 是自绘标题禁区，Y<35 的控件会被静默搬家**（HuaJiVision 独有，V4.4.8 实测）：UIForm 的 `FormBorderStyle=None` + 自绘蓝标题栏约 35px 高；`Controls.Add` 时 Y<35 的控件会被强制搬到 Y=35（harness 实测：`Location=(16,5)` 的 Label 加完读回即 `(16,35)`，与 Show 无关、建造前/后一致）。症状极具迷惑性——Designer 坐标全对、其他控件位置全对，只有顶行压住下方组框顶边（mFormAirtight 首版模式行 Y=14/16 被搬到 35，正好盖住 grpIO 组框标题）。**修法：首行从 Y≥40 起排**（本案模式行→50/52、组框→84、窗高同步+36）；DevPanel 首控件 Y=52 天然免疫。**验证**：harness 里 new 完立刻打印顶行 `Bounds`（不等 Show），设计值≠读回值即中招；再截一帧确认组框标题无横线穿过。注意与坑 11 区分：这是 Add 时强制搬家，不是 AutoScale 固化（本案 `AutoScaleDimensions` 全程 0,0）。

30. **DataGridView 换肤表头惨白 = `EnableHeadersVisualStyles` 没关**（HuaJiVision 独有，V4.4.13 实测）：开着时表头/行头走系统视觉样式绘制，代码设的 `ColumnHeadersDefaultCellStyle.BackColor` 根本画不上——深色下整个表头一片惨白（harness 深色截图抓获，设置页 PLC/TCP 两表）。**修法：换肤时 `EnableHeadersVisualStyles=false`**，再设五件套（底/字/表头/网格/选中）；浅色表头用 Control 实色，与系统渐变肉眼无差。通用规则：任何"设了颜色却没变化"的表头/行头，先查这个开关。
31. **HuaJiVision 魔改版 SunnyUI 窗体 PrintWindow 渲染完整**（V4.4.13 实测，与 Kaleidoscope 例外相反）：三个 Sunny 窗体（震动盘/开发者面板/设置页）深/浅双版 PrintWindow 截图，标题/按钮/输入框/下拉/表格全渲染、无裁剪——本项目做换肤目检可直接用 PrintWindow，不必上真实截图。WPF 混合窗（脚本编辑器）仍须 `f=2`（坑 17 不变）。
32. **换肤快照必须"整树先快照、再整树刷色"，禁止边读边刷**（HuaJiVision 独有，V4.4.13 实测）：WinForms 底色/字色是环境继承属性——子控件未显式设色时读到的是父级颜色。若先刷黑父窗再逐个"读原值"，读到的就是继承来的深色，切回浅色等于没恢复（组框/输入框残留深色，harness 深→浅截图抓获）。**修法：快照遍与刷色遍严格分离**，快照时继承链全是设计色；改换肤动了哪个属性，快照/恢复两处同步加行（三处一一对应，缺一行浅色就恢复不出来）。
33. **原生 GroupBox 整组禁用后标题恒黑，换肤救不回来**（HuaJiVision 独有，V4.4.15 实测）：`Enabled=false` 的组框标题走系统灰字、无视 `ForeColor`（决定性实验：运行时设 `ForeColor=Red`，标题条 0 红像素）——深色下只有被禁用的那组标题发黑（用户截图：TCP 组黑、上面三组浅）。**修法：组内控件级禁用**（组框本身恒启用，只禁里面表格/按钮，语义不变），标题保持换肤色。
34. **ToolStripItem 不在 Controls 里，换肤递归碰不到**（HuaJiVision 独有，V4.4.15 实测）：状态条/菜单条的 Item 设了语义底色（Lime/Yellow），深色继承来的灰白字看不见。**修法：赋值处直接钉死文字色**（`ForeColor=Black`，双主题常驻），别指望换肤递归。另：菜单项状态判据用 `Available` 而非 `Visible`（父下拉未展开时 Visible 恒 false）。
35. **单色字形按钮深色三连：底刷深则字形隐身、留浅底用户不要、转白要配暗底**（HuaJiVision 独有，V4.4.15→V4.4.16 两轮）：字形资源是按浅色底画的深色线条（resx 实测 200×200 单色深灰、半透明抗锯齿边）——底刷深=深字压深底隐身；留设计浅底能看但用户要"和菜单栏一整块"。**正解三件套**：①换肤只认 `Tag="DarkGlyph"` 注册（构造期挂，换肤不认控件名；**彩色图标按钮千万别挂**，转白洗色不可逆）；②底对齐所在容器/菜单栏主体色（别自创第 N 种灰）；③字形转白（Alpha 原样保留、RGB 全白，原图快照、浅色引用级恢复）。**验证铁律**：真机资源逐像素断言（尺寸/Alpha/全白/缓存）+ 反向验证（去掉换白、删一个 Tag 都必须 FAIL）。
35b. **同名标记可扩展到 ToolStripItem，但先实测再动手**（HuaJiVision 独有，V4.4.17）：菜单条字形项（设置/排序分裂按钮）不在 Controls 里，Button 那套够不着——独立原图本（恢复不依赖本体快照）+ 同样 Tag 注册。**教训**：分裂按钮 Designer 写着 `ImageTransparentColor=Magenta`，实测图里一个品红像素都没有（真 32bpp Alpha 透明，色键设置是残留）——若按"色键图"预处理（品红转透明）就全错。**老资源先逐像素普查（透明/品红/深色/其它四分类计数）再定转白策略**，别信 Designer 里的透明色声明。
35c. **下拉菜单换肤必须走 ToolStripManager 全局接管，逐个设粘不住**（HuaJiVision 独有，V4.4.17 血泪）：下拉是独立顶层窗（换肤递归够不着），直觉是给每个下拉设 `Renderer=暗版`——实测读回的是默认渲染器（疑似下拉跟随宿主渲染器），菜单照旧浅底。**正解**：`ToolStripManager.Renderer=暗渲染器` 一次接管（全软件下拉自动跟随，主菜单条有显式 BackColor 走实色不受影响）+ 每个下拉 `ForeColor=白`（子项继承，别逐项设）；浅色把渲染器还回接管前原值（首次接管时记下）+ `ForeColor=Empty`。**断言注意**：`ForeColor=Empty` 读回的是继承默认值（ControlText 黑），别断言 `==Empty`（保护方法 `ShouldSerialize` 探针调不到，用读回值等价判定）。
36. **预乘 Alpha 舍入：Bitmap 拷贝后 GetPixel 白变 254**（HuaJiVision 独有，V4.4.16 实测）：半透明像素经 32bpp 预乘存取，`GetPixel` 读回 254/254/254 而非 255——断言写 `==255` 全员假失败。**修法：白色断言容差 250**（肉眼无差），Alpha 仍要求逐像素一致。
37. **Sunny UIGroupBox 自绘认 FillColor/RectColor，不认 BackColor**（HuaJiVision 独有，V4.4.15 实测，反射列属性确认）：`BackColor` 设了也画不上，深色下组框一直白底。**修法：反射设 `FillColor=底`/`RectColor=框`**，快照与换肤一一对应。连带：Sunny 蓝色按钮组（UIButton 等 chrome 系）深浅通吃，保持不动，别去"统一刷色"。
38. **深色断言必须配反向验证，否则等于没测**（HuaJiVision 独有，V4.4.7 + V4.4.15/16 三轮共识）："全绿"可能是断言从未执行（`PerformAutoScale(SizeF,SizeF)` 反射根本无此重载，异常被 catch 吞掉即假绿，见坑 28）。**铁律**：新探针落地后，往源码 temporarily 改坏一处（删一行赋值/注掉一个分支），重跑必须精准 FAIL，再改回来。静态结构探针还要先剥注释再匹配（注释里的历史教训词会假 FAIL）。
39. **SunnyUI 的 UITabControl + UIPage 必须走 AddPage，手写 TabPage 包裹必空白**（AgingTestSystem 独有，V1.63.2 血泪）：`UIPage` 是 Form（`Visible=false` 起步），`UITabControl.AddPage(page)` 内部做四件事——建 TabPage + `Dock=Fill` + `TabPage` 绑定 + `Show()`。若 Designer 里手写 `TabPage` 包裹 + `Controls.Add`（VS 设计器 serial 出来的样子），漏掉 `Show()` 则页面永远 `Visible=false`：子控件全建好（本案 72 灯按钮一个不少）、页签之外的按钮照常工作，现场症状=“页上没图标、但连接测试正常”，极具迷惑性。**判据**：`tabControl.GetPage(page.PageGuid) != null` 且 `page.Visible == true`。**harness 探针三件套**：反射读 `page.Visible` + `Helper.GetPage(guid)` 是否 null + PrintWindow 后沿按钮行扫特征色（本案 OFF 态深灰 `70,70,76`，修前 0 命中、修后 50+）。修法：删 TabPage 字段/`Controls.Add`/`TabPage=`/`Visible=false` 四类行，Designer 末尾手写 `AddPage` 两行（设计器不会生成，仿旧版注释写明，防后人“优化”回手写包裹）。反向验证天然成立：本案修前 harness 即 FAIL 态。
40. **AI 改 Designer 必须做"声明/实例化配对"扫描**（AgingTestSystem 独有，V1.71 血泪）：Edit 工具的多行块替换会模糊匹配、静默吞掉被跳过的间隔行（本案 27 行块吞掉 3 个 `new`，编译照过、构造即 NRE）。**修法**：每次改完 Designer 跑配对扫描——每个 `private Xxx field;` 必须有 `this.field = new ...`（PowerShell 正则 10 行）；再 harness 里把改过的窗体 new 一次（NRE 当场现形）；再截图目检。**教训：多行 oldString 只许覆盖已用 Read 逐行核对过的连续行**，跨段批量改名用单行 replaceAll。
41. **SunnyUI 自绘控件的类型判定三兄弟**（AgingTestSystem 独有，V1.71 实测，反射列继承链确认）：`UILabel : Label`（`is Label` 照用无碍）；`UIButton : UIControl`、`UITextBox : UIPanel`、`UIComboBox : UIDropControl`（全不是原生子类，`is Button/TextBox/ComboBox` 永远 false）。**后果有三**：①换肤/布局递归里的 `is` 判断全部走空分支（本案按钮会被容器表误染）；②字段声明改了类型后，code-behind 里 `as TextBox` 拿回 null（回归当场红两条）；③`UITextBox` 没有 `ScrollBars/WordWrap`（用 `ShowScrollBar/WordWarp`，注意 Sunny 把 Wrap 拼错了），`UseSystemPasswordChar` 没有（用 `PasswordChar='*'`），`ComboBoxStyle` 不能用（用 `UIDropDownStyle`）。**探针**：反射列 `BaseType` + 读关键属性/方法名，API 差异编译期一次收敛（本案 `Add-Type` 读 DLL，10 分钟收齐）。
42. **UIForm 标题禁区的两种正确姿势**（AgingTestSystem 独有，V1.71 harness 实测）：自绘蓝标题占约 35px 客户区，`Controls.Add` 时 Y&lt;35 的控件会被静默搬到 Y=35（含 Dock=Fill，照搬不误）。绝对布局：内容整体下移 35px + 窗体加高 + `MinimumSize` 锁缩小；Dock 布局：窗体加 `Padding(2,38,2,2)`（搬家后的 Dock 内容恰好从 38 开始，无双重偏移，harness 读 `Bounds` 验证）；Dock 窗若内容贴底（如 ID 绑定的保存按钮），窗体仍要加高 35（Panel 缩了，绝对子控件会溢出）。**判据**：改完 harness 构造一次 + PrintWindow 截一帧，按钮/列表无裁剪、无压标题。
 43. **自绘画布开 DoubleBuffered = 所有 TextRenderer 走离屏慢路径 + PrintWindow 取证失效**（AgingTestSystem 独有，V1.81.2 两轮实锤）：①性能：`DoubleBuffered=true` 逼整窗文字走离屏缓冲（GDI 每处 ~2.2ms，见§九 V1.57.3），可见区 25 行×2 处 ≈ 110ms/帧，滚快了"字出不来"还拖影（看着像错位）。修法：关双缓冲直画屏幕 DC（近 0ms）+ `OnPaintBackground` 留空并在 OnPaint 里按裁剪区自填底（不闪）+ 可见区裁剪照做；长文本布局态预截断（ Paint 里不再量字）。②取证：关掉之后 PrintWindow 在**滚动过的画布**上会丢 GDI 文字（框在字无，真屏 CopyFromScreen 文字完好——已用深色像素计数双面裁定）。以后这类窗体：像素计数用离屏 `OnPaint` 重放（DC 可控），视觉证据一律 TOPMOST 置顶 + CopyFromScreen（见§十一），别信滚动后的 PrintWindow。
44. **AutoScroll 内容剧变后滚动范围卡旧，滑块拉不到底**（AgingTestSystem 独有，V1.88.15 harness 五轮实锤）：症状是拖 Splitter 改宽后纵向滑块卡 80% 拉不到底（或底部大片空白）。根因是布局时序三连——①内容 `Size` 跳变后父容器 `DisplayRectangle`/滚动 `Maximum` 不更新（`vMax` 纹丝不动，2 秒不收敛，是稳定脏态不是时序慢）；②`Resize` 事件里调 `PerformLayout()` 正撞上布局挂起、被静默忽略（手动调一次立刻全好，反证自动布局没跑）；③`Layout` 事件里压 `HorizontalScroll.Visible=false` 注定失败（布局引擎在事件之后还会覆盖，-nohook 对照实验证明去留无差）。修法三件套（只动自家容器）：①设完 `Size` 同步设 `AutoScrollMinSize=Size`（值语义驱动 `DisplayRectangle`，不赌子控件布局时序，横向 `MinSize.Width=客户宽-1` 顺带让布局永不判需横向条）；②同步布局后按旧滚动比例恢复位置并钳制；③`BeginInvoke` 在布局彻底完成后跑校正（再 `PerformLayout` + 压横向条 + 钳位置，释放检查防重建串扰）。验证法：harness"滚到底→加宽→减窄→再到底"，断言 `posY==内容高-客户高` + `hVis==False` + `vMax==内容高-1` + 2 秒稳定判据（未滚动行的 `posY=0 vs expectMax>0` 是 harness 判定逻辑问题，忽略，只看"再到底"行）。另：面板间缝隙点选误翻选同案修——行列整除把缝隙算进上一格，`TryHitPanel` 加内容 bounds 检查，缝隙一律不命中（行/列缝不命中+底边内仍命中三条回归锁）。
45. **像素扫描量文字宽度，先把边框/分隔线排除，否则把边框当墨迹**（AgingTestSystem 独有，V1.88.17 harness 实锤）：症状是离屏截图上量出"标签墨迹 52px、槽位才 47px"，看着像文字溢出被裁。根因是扫描带扫进了值框的 1px 黑边框（左右边框各贡献 1 列深色像素，min/max 直接顶到边框坐标）——墨迹宽度=文字+边框，虚增。修法：量某行文字时把扫描 x 范围收在边框内侧（`右界=框左边缘-1`），或分段确认（文字墨迹应止于边框前 N px）；先拿 `TextRenderer.MeasureText(同字体)` 的理论值对照，差出边框厚度（2px）以上再怀疑溢出。本案复核：标签墨迹止于框边 14px 前，无裁剪，虚惊一场。
46. **Sunny UIForm 去标题栏标准套路**（AgingTestSystem 独有，V1.89 主窗落地、可跨项目照抄）：基类保持 `UIForm`，只加 `ShowTitle=false`（`Dock=Fill` 内容不再被顶 35px、Y&lt;35 不再搬家，Padding 顶清零，`Resizable=false` 维持不动——Sunny 本来就不做边缘 NCHITTEST，`Resizable=true` 照样全回 CLIENT，别指望它）。三按钮用原生 Button 进顶栏最右，GDI 线条自绘字形（禁 emoji/Unicode，老工控机字体回退显示方块），悬停底自管（ThemeManager 跳过按钮类，换肤后手动 Invalidate）。`WndProc` 先调 base 再改写 `WM_NCHITTEST`（Normal 下边缘 6px 回缩放码、顶栏非按钮区回 `HTCAPTION`，按钮经类型判定放行保可点——Sunny UIButton 不是 Button 子类，按类型名认）；`WM_NCLBUTTONDBLCLK` 必须拦在 base 之前切完直接返回——DefWindowProc 收到 HTCAPTION 双击自己会切一次，两边各切一次正好抵消（本案 harness 两次纹丝不动实锤，改前置后 17/17 全绿）。任务栏标题带版本号走运行时常量（禁 Designer 写死旧版本）。验证五件套：构造不断言 NRE＋配对扫描＋真窗 Show＋PrintWindow（顶栏条带×3 看字形）＋NCHITTEST 探针（边缘/顶栏/按钮各一）＋三按钮点击真实路径（最小化→Minimized、方框→Maximized、关闭→!Visible），缺一不可。另：`CreateControl()` 不跑布局，几何断言（Bounds.Y==0 这类）必须真 Show 后读，否则读到 Designer 旧值假红。

## 六、窗口全屏 / 禁缩放 / 边框行为专项（V1.11.0 CommandCenter 沉淀）

"开机全屏、禁缩放、但保留最小化/关闭按钮"是工控界面的常见需求，也是 WinForms 最容易反复翻车的点。核心原则：**让"固定"成为真实状态，而不是看起来固定**。下表是各方案的实测结果（客户现场逐版验证过）：

| 方案 | 结果 | 结论 |
| --- | --- | --- |
| `FormBorderStyle=None` + 铺满屏 | 无边框、无任何系统按钮 | 关不了软件，客户投诉 |
| `FixedDialog` | 边框固定、**无最小化/最大化按钮** | 客户要最小化 |
| `Sizable` + `MaximizeBox=false` | 按钮禁用，但**边框仍可拖拽缩放** | 拖拽漏网 |
| `FixedSingle` + `WindowState=Maximized` | **Windows 把边框强制切成可调整样式，边缘拖拽照常开放** | 最隐蔽的坑 |
| ✅ `FixedSingle` + `Normal` + 手动铺 `WorkingArea` + `MaximizeBox=false` + `MinimizeBox=true` | 全屏等效、无拖拽句柄、最小化/关闭都在 | 正解 |

### 关键机制：为什么 `Maximized` 不能用
`WindowState=Maximized` 时 Windows 会临时把 `FormBorderStyle` 当作可调整边框处理（为了支持最大化窗口边缘拖拽调整），**与你 Designer 里写的 `FixedSingle` 无关**。此时即使 `WndProc` 拦截 `WM_NCHITTEST` 把四边热区改 HTCLIENT 也挡不住——系统在最大化状态下直接走自己的缩放通道。

### 正确组合（照抄即可）
```csharp
// Designer / InitializeComponent：
this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedSingle; // Normal 下无拖拽句柄
this.MaximizeBox = false;   // 中间的"最大化/还原"按钮变灰
this.MinimizeBox = true;    // 最小化按钮保留
this.WindowState = System.Windows.Forms.FormWindowState.Normal; // 千万别用 Maximized！

// OnShown：手动铺满工作区（等效全屏，保留任务栏）
var work = Screen.FromControl(this).WorkingArea;
Bounds = new Rectangle(work.Location, work.Size);
```

### 双保险（可选，防系统残留热区）
`WndProc` 拦截 `WM_NCHITTEST`（0x0084），把命中码 10~17（HTLEFT..HTBOTTOMRIGHT 四边四角）一律改写为 1（HTCLIENT），Windows 不再进入缩放拖拽流程；最小化（8）/关闭（20）/标题栏拖动（2）不受影响。Normal + FixedSingle 下其实已够，这条是兜底。

### 排查口诀
- 用户说"拖拽还是能缩放" → 先查 `WindowState` 是不是 `Maximized`（十有八九是它）；
- 用户说"最小化按钮没了" → 查 `FormBorderStyle` 是不是 `FixedDialog`/`None`；
- 用户说"关不了软件" → 查是不是 `FormBorderStyle=None`；
- 想全屏 → **别用 Maximized，用 OnShown 手动铺 Bounds**；否则 `FixedSingle` 白设。

## 七、WinForms 点击/双击生效判定（V1.12.15 CommandCenter 三轮血泪）

做"双击放大/还原/整窗响应双击"先读这条（CommandCenter 案例：`Controls/CameraDisplayControl.cs` 的 `HandleDoubleClick`，图像区 PictureBox `Dock=Fill` 占满整窗）：判断某控件上"点击/双击有没有反应"，先想清两件事，否则白改：
- **① 真实命中目标是谁**：鼠标双击落在**最内层子控件**上，**不会"自动落到父 UserControl"**。红线：双击 BI 控件时只有被点的那个控件收到消息。
- **② 事件冒不冒泡**：WinForms 中带 `Mouse` 前缀的（`MouseClick`/`MouseDoubleClick`/`MouseDown`…）会沿父链冒泡；不带前缀的（`Click`/`DoubleClick`）**不冒泡**。
- **最稳写法，直接背**：直接订阅最内层子控件（PictureBox）的 `MouseDoubleClick`，它在真实命中点、必然触发、不依赖冒泡。**别用**父控件 `OnDoubleClick` 重写（不冒泡→没反应，第一版就这么挂的）；**也别赌**父控件 `MouseDoubleClick` 冒泡（部分环境不稳定，第二版也挂）。
- **验证不能用合成鼠标**：headless / 无桌面交互会话下，`mouse_event`、`SendMessage WM_LBUTTONDBLCLK` 都**触发不了 WinForms 双击**——WinForms 对双击有内部状态/计时免疫，合成事件被吞，发多少遍都不生效，别拿它当验证依据（在这上面空转了很久）。
- **可靠的验证手段**：进程序 harness 反射调用**真实命中控件（PictureBox）的 `protected OnMouseDoubleClick`** 注入双击（不依赖消息/计时），再反射读私有字段断言结果（如 `_fullScreenForm` 是否非空、放大的 `_windows[?]` 是否同一、`RestoreFullScreenWindow` 后是否置 null）。这是验证"双击→放大→还原"类行为的可靠手段；状态文本类就反射读 `Label.Text`。

## 八、DataGridView ComboBox 列选中行高亮（V2.15.22 CommandCenter 血泪）

`DataGridViewComboBoxColumn` 的单元格使用 ComboBox 渲染引擎画背景，会**忽略** `DefaultCellStyle.SelectionBackColor`——设置再醒目的蓝色，选中行也只显示系统默认的极淡蓝色，与未选中行几乎无区别。**必须用 `CellPainting` 事件强制覆盖**：在选中行的每个单元格绘制前先铺一层蓝色背景（`e.Graphics.FillRectangle(brush, e.CellBounds)`），再 `e.Paint(ClipBounds, ContentForeground)` 绘制内容，`e.Handled = true` 阻止默认渲染。样式配合：`CellBorderStyle=None`（移除边框让蓝色更连贯）、`GridColor=ControlDark`（恢复系统默认）、`DefaultCellStyle` 用 `SystemColors.Highlight/HighlightText`。**禁止只设 `SelectionBackColor` 不加 `CellPainting`**——那是无效的。改 CommandCenter `dgvPrograms` 等 ComboBox 列表格的选中样式先读这段。

## 九、高 DPI 适配专项（V1.55 沉淀）

用户报"高分辨率屏幕界面显示不正常"时，先分清两类控件，再决定适配方式：

### 判断根因：先确认是"不缩放"还是"缩放比例不一致"
- 打印 `form.DeviceDpi`、各关键控件 `CreateGraphics().DpiX`、`AutoScaleMode`。
- **标准控件窗体（AutoScaleMode.Font）**：WinForms 会自动按字体比例放大，通常无需动代码，只需保证 `app.manifest` 有 `PerMonitorV2` + `App.config` 有 `Switch.System.Windows.Forms.DpiAwareness=PerMonitorV2` 运行时开关（**两个缺一不可**）。**注意：这适用于 Designer 生成的窗体；纯代码窗体要额外显式设 `AutoScaleDimensions(6F,12F)` + `SuspendLayout`/`ResumeLayout` 包裹，否则不缩放**（见下文"纯代码窗体 AutoScale 验证专项"）。
- **自绘控件（AutoScaleMode.None）**：画布尺寸和坐标是"96DPI 逻辑像素"，**不随 DPI 放大**，但 pt 字体会自动放大 → 文字溢出格子、与周围标准控件比例失调。这是"主界面显示不正常"的典型根因（AgingTestSystem 例：自绘工位网格；对照见附录 A）。

### 自绘控件 DPI 适配三步
1. **计算缩放因子**：句柄创建后（`OnHandleCreated`）算 `_dpiScale = 实际DPI / 96`。**踩坑：`Control.DeviceDpi` 在 PerMonitorV2 下句柄刚创建时返回 96（不准确），必须用 `CreateGraphics().DpiX`（实测 144 才是真值）**。
2. **手动乘坐标，别用 ScaleTransform**：自绘里 TextRenderer 走 GDI 不认 `Graphics.ScaleTransform/TranslateTransform`（见坑 1、V1.51 踩坑），必须写 `Scaled(int/Point/Rectangle)` 辅助方法，把所有绘制坐标、画布 Size、命中检测（鼠标坐标是物理像素）、tooltip、局部重绘矩形统一乘 `_dpiScale`。字体保持 pt 单位自动放大，两者同步放大比例才一致。
3. **命中检测别漏**：鼠标 `e.Location` 是物理像素，与缩放后的布局矩形比较；可见列/行范围计算（`clip.Left / 列宽`）也要用缩放后的列宽，否则只重绘左上角一小块。

### 验证超画布自绘控件：用离屏 OnPaint，别用 PrintWindow
- 自绘画布 3060×3038 远超屏幕，**PrintWindow 只截可见区**，超屏部分全是背景残留色（Magenta），像素扫描全假失败。
- 正解：反射调用 `Control.OnPaint` 渲染到完整尺寸 Bitmap（`new PaintEventArgs(g, new Rectangle(0,0,宽,高))`），无视屏幕限制，再逐像素验证。
- 验证点示例（150% 缩放 = 逻辑坐标 ×1.5，AgingTestSystem 实测）：面板左上角 = `Scaled(2)=3`；上电块 = `Offset(Scaled(RcPower),3,3)`；行全选列 x = `Scaled(8*245+2)=2943`。

### 纯代码窗体（无 Designer）AutoScale 验证专项（V1.58.4 沉淀）
用户报"纯代码窗体高分屏不放大/偏小"时，先分清是哪个环节坏了。**这类问题 harness 默认验证不出来，必须按下面的 PerMonitorV2 全套配置跑，否则拿到的是假结果**：

- **harness 只调 `SetProcessDPIAware()` 是 System-aware，测不出 AutoScale 缩放**：System-aware 下 WinForms 会把 `AutoScaleDimensions` 初始化为"当前 DPI 设计值"（144 DPI 下自动变 9×18），导致设计基准==运行基准、缩放因子恒为 1、窗体永不放大。**必须两步配齐才走 PerMonitorV2 路径**：
  1. 编译时带 manifest：`csc ... "/win32manifest:C:\...\pmv2.manifest"`（manifest 内容见下方模板）。
  2. 运行时带 config：在 bin 放 `<exe名>.exe.config`，配 `<AppContextSwitchOverrides value="Switch.System.Windows.Forms.DpiAwareness=PerMonitorV2" />`。
  - 判断依据：同样流程下 **Designer 窗体能缩放、你的纯代码窗体不缩放**，说明 harness 环境对了，问题在窗体的 AutoScale 写法（Designer 对照窗体见附录 A）。
- **纯代码窗体高 DPI 三要素**（缺一不可，缺任意一个就"永不放大"）：
  1. `AutoScaleDimensions = new SizeF(6F, 12F)`——只设 `AutoScaleMode.Font` 会以 96DPI 为基准不缩放；
  2. **`SuspendLayout()` 包裹全部控件创建 + 末尾 `ResumeLayout(false)`**——未挂起时逐次 `Controls.Add` 会触发 PerformAutoScale 并把 AutoScaleDimensions 固化成当前 DPI 值，缩放失效。这是最隐蔽的一环（Designer 窗体天生带，所以从没人发现纯代码窗体缺它）；
  3. 主程序 `app.manifest`(PerMonitorV2) + `App.config`(DpiAwareness=PerMonitorV2) 两处已配。
- **验证"是否缩放"的正确探针**：打印 `form.AutoScaleDimensions` / `form.CurrentAutoScaleDimensions` / `form.ClientSize`，以及关键面板 `Size`。144 DPI 下修复后应为 `ClientSize=640×520 → 960×780`、各面板×1.5（`pnlValues 148→222`、预览区 294→441），且 `AutoScaleDimensions` 构造后仍是 `6×12`（**若读回 9×18 说明被固化了，就是 SuspendLayout 缺失**）。96 DPI 下缩放因子=1、保持原尺寸，由公式保证，无需专门模拟。

pmv2.manifest 模板（放临时目录，harness 编译用）：
```xml
<?xml version="1.0" encoding="utf-8"?>
<assembly manifestVersion="1.0" xmlns="urn:schemas-microsoft-com:asm.v1">
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true</dpiAware>
      <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">PerMonitorV2</dpiAwareness>
    </windowsSettings>
  </application>
</assembly>
```
exe.config 模板：
```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <runtime>
    <AppContextSwitchOverrides value="Switch.System.Windows.Forms.DpiAwareness=PerMonitorV2" />
  </runtime>
</configuration>
```

### 自绘控件性能优化（V1.57.3 血泪教训，AGENTS.md 强制红线）
排查"自绘控件卡顿/掉帧/每秒卡死"时，先背这几条，别走弯路：

- **禁止"离屏 Bitmap 整幅预渲染 + OnPaint DrawImage 拷贝"**：实测离屏大图（2040×2025）上 `TextRenderer.DrawText` 每处约 **2.2ms**（屏幕 DC 上近 0ms），全量渲染 72 面板一次高达 **2247ms**；若再配"每秒全量刷新"，整个软件每 1 秒卡死一次。且 `g.Clear(白色)` 会把面板间隙刷白，导致"面板连成一片"的视觉 bug。
- **正确做法**：OnPaint 只重绘**可见区**面板——用 `e.ClipRectangle` 反推行列范围，循环里跳过 `!rect.IntersectsWith(e.ClipRectangle)` 的面板；数据/选中变化只 `Invalidate()`（让系统按需合并重绘）；滚动卡顿用 **16ms 定时器节流 AutoScrollPosition + 画刷/画笔缓存字段**，不要每次 OnPaint 现造 Brush/Pen。
- **连线类图元判交用控制点包围盒，不用两端点**（V1.81.4 跨项目通用教训）：贝塞尔中段穿屏、两端屏外的长线，"两端点相交才画"会整条裁掉——滚屏后新露出的条带只有底没有线（平时有线、一滚就断）。曲线必落在控制点包围盒内，用包围盒判交保守但无漏网；箭头仍只在端点可见时画。修裁剪类 bug 配"两端出屏+中段穿屏"场景，正反两面断言（旧条件必须精准 FAIL）。
- **性能判断必须用真实屏幕 DC**：用 `CreateGraphics()` 拿屏幕 DC 测帧速/耗时。**离屏 Graphics 上的 TextRenderer 慢是 GDI+ 固有行为，不代表真实帧速**——在离屏 Bitmap 上测得慢不等于真实渲染慢，反之亦然。
- **改自绘坐标前先查配置模型**：自绘控件的坐标/颜色/字号常量一律**外部化**到配置模型（AgingTestSystem 做法：`Models/PanelLayoutConfig.cs`，可被 `PanelLayout.json` 覆盖；其他项目见附录 A），**禁止写死像素常量**。改布局先在配置文件里找对应项。

### 改界面代码前必读头部 ASCII 图（项目约定，防改错布局）
- 各项目界面文件类 XML 注释里都有一张用 `┌─┐│└┘` 画的界面布局图，**框内标注控件名与关键交互点**。AI 无法看图，改界面全靠这张图（AgingTestSystem：`Views/*.cs`、`Dialogs/*.cs`，参考 `RecipeManagerForm.cs` / `WorkstationGridView.cs` 头部；HuaJiVision：`SubForm/mForm*.cs`）。
- 改布局前先读目标窗体的 ASCII 图，确认控件名/坐标；**改完必须同步更新该图**（坐标、控件名、按钮文字都要和实际一致），否则下次维护的 AI 拿到错图会改错布局。

## 十、深色模式换肤专项（新界面一步到位清单）

做"新增窗体/页面深色适配"或"深色漏网补漏"时，按本节清单走一遍再交工——HuaJiVision
V4.4.13→V4.4.16 四轮返工的全部教训已收拢，逐条对照就不用反复改。通用坑见§五
32〜38，HuaJiVision 完整样板是 `SubClass/AppTheme.cs`（文件头注释即用法）。

### 一步到位 10 条

1. **接入只走三行**：`OnShown` 里 `ApplyTo + 订阅 Changed`，`OnFormClosed` 退订（静态事件不退订=窗体泄漏），私有转发方法判 `IsDisposed`。常驻窗体（主窗）无需退订。
2. **颜色只用既定色板，不自创第 N 种灰**：按钮底对齐所在容器/菜单栏主体色，字只用前景色；新色=下次补漏的源头。
3. **自绘区/图像区/看图区按名跳过**：黑底看图、第三方图像控件不换肤（换了也看不清，还可能破坏渲染）。
4. **禁用态不用整组 `Enabled=false`**（坑 33）：组框/容器本身恒启用，只禁里面子控件；标题/文字保持换肤色。
5. **带图按钮先分类再动手**（坑 35）：单色字形挂 Tag 走"容器底+转白"；彩色图标/照片按钮不动底不动图；纯文字按钮正常刷底；菜单条字形项用同名标记的 ToolStripItem 版（坑 35b）。
6. **表格/输入/下拉/菜单走既定分支**：表头先关 `EnableHeadersVisualStyles`（坑 30）；语义色（红/绿/黄底）赋值处直接钉死文字色，别指望递归（坑 34）；下拉菜单暗底走全局渲染器接管+本单白字（坑 35c）；状态字"停止/运行"这类双态文字，赋值处与主题切换处同步判色（一切换主题旧字色就错）。
7. **快照/换肤/恢复三处同步加行**（坑 32）：改换肤动了哪个属性，快照遍与恢复遍各加一行；浅色必须像素级还原设计稿，不设"近似浅色"。
8. **Sunny 控件认自绘属性**（坑 37）：组框体 `FillColor`/`RectColor`，输入框 `FillColor`/`ForeColor`/`RectColor`；蓝色按钮组深浅通吃，保持不动。
9. **探针=功能断言+反向验证**（坑 38）：每条修复配一条能触达链路的像素/反射断言，落地后改坏源码重跑必须 FAIL；静态文本探针先剥注释再匹配。
10. **双版截图目检**：深/浅各截一帧（PrintWindow 能渲染全的直接用；WPF 混合窗用 `f=2`，Sunny 自绘渲染不全的上真实截图，见§四.1 与§十一末尾对照表）。

### HuaJiVision 落点对照（在本项目做深色改造时直接取用）

| 项 | 值 |
|---|---|
| 样板/色板 | `GYZVision/SubClass/AppTheme.cs`（深 `#1E1E1E/#252526/#2D2D30/#3E3E42/#D4D4D4`，浅=系统色零偏差） |
| 三个 Tag | `NoTheme` 整棵跳过 / `NoThemeSelf` 只跳自身 / `DarkGlyph` 字形转白（构造期挂） |
| 功能探针 | I14 主题开关 / I15 Sunny 组框 / I16 字形按钮 / I17 禁用组标题（`DeviceFrameworkProbe.cs`） |
| 结构守护 | SG22 开关在位 / SG23 语义色配黑字 / SG24 字形三件套+底色 / SG24b Tag 计数 / SG25 组内禁用（`StartupGuardProbe.cs`） |
| 项目红线 | 授权码只存 `HslLicense.dat`（禁入库）；`MainSetting.ini` 的探针副作用提交前 revert；详见该项目 AGENTS |

## 十一、矩形枚举与真实截图工具（Kaleidoscope 沉淀，本目录 scripts/）

harness 适合"直启目标窗体做像素探针"；**布局错位/遮挡类问题**（显示不全、控件被盖、Bottom 对不齐）另有专用工具：不启动调试器，直接对目标 exe 跑脚本拿**全部子窗口实际屏幕矩形**（决定性证据）+ 真实截图（视觉证据）。脚本 Python 与 PowerShell 双版本同功能，Python 版需 pywin32（截图另需 Pillow），PS 版零依赖（现场无 Python 时用；**.ps1 必须 UTF-8 带 BOM**，PS 5.1 无 BOM 按 ANSI 解析中文会语法错误）。

| 脚本 | 用途 |
|---|---|
| `scripts/Get-ControlTree.py` / `.ps1` | 枚举主窗体全部子窗口实际屏幕矩形，按 Y 排序输出 |
| `scripts/Get-WindowShot.py` / `.ps1` | 置顶窗口 + 可选点击 + 真实屏幕截图存 PNG |

```powershell
# 枚举子窗口矩形（必须显式给 --exe 或 --attach --process）
python scripts/Get-ControlTree.py --exe "<bin>\<主exe>" --click <X> <Y> --topmost
python scripts/Get-ControlTree.py --attach --process <进程名>

# 真实屏幕截图
python scripts/Get-WindowShot.py --exe "<bin>\<主exe>" --click <X> <Y> --out shot.png

# PowerShell 版（参数为 -ExePath / -ClickX / -ClickY / -Topmost / -Attach / -ProcessName / -OutFile）
.\scripts\Get-ControlTree.ps1 -ExePath "<bin>\<主exe>" -ClickX <X> -ClickY <Y> -Topmost
```

参数说明：`--exe/-ExePath` 要启动的 exe（启动模式必填）；`--process/-ProcessName` 进程名（`--attach` 模式必填）；`--click/-ClickX,-ClickY` 窗体内相对坐标（换算 `screen=矩形.Left+X`，让条件显示容器先出现用）；`--topmost/-Topmost` 置顶；`--out/-OutFile` 截图保存路径（默认当前目录 `window_shot.png`）。启动模式结束时只杀自己启动的进程，`--attach` 永不杀进程。

### 决定性判据（拿到矩形数据后怎么看）
- **Dock=Fill 的容器底边 == 其父容器底边 = 没让位 = Controls 添加顺序错误**。
- Dock 引擎按 Controls 集合 **index 从大到小**依次扣减：**Fill 容器必须最先 Add（index 最小）**，Top/Bottom/Left/Right 边缘条后 Add（先处理、先扣边）。
- 顺序反了的症状极具迷惑性：**视觉可能完全正常**（边缘条靠 z-order 恰好盖在 Fill 上面），但 Fill 实际占满全客户区、内部全按全尺寸布局——底部内容被边缘条静默遮挡（Kaleidoscope 实测：split 后 Add 导致内容被状态条遮 30px 达数个版本，直到贴底的新条出现才暴露）。

### 截图验证两不要（Kaleidoscope 血泪）
- 不要用 PrintWindow——SunnyUI 自绘控件在 WM_PRINT 下渲染不全（只画顶部一条），会产生"控件被裁"的假象；必须 TOPMOST 置顶 + CopyFromScreen/ImageGrab 真实屏幕截图。
- 不要用 SetForegroundWindow——会被系统前台锁静默拒绝（截到别的窗口），用 SetWindowPos(HWND_TOPMOST)。

### 三种取证手段的选用
| 手段 | 适用 | 注意 |
|---|---|---|
| PrintWindow（§四.1） | 默认：像素级找线/叠色，坐标稳定可复现 | 超画布只截可见区；SunnyUI 自绘 WM_PRINT 不全、WPF 须 `f=2` |
| 矩形枚举（本节脚本） | 布局错位/遮挡：拿精确矩形对照 Dock 判据 | SunnyUI 控件不进 UIAutomation，一律 Win32 EnumChildWindows |
| 真实截图（本节脚本） | PrintWindow 渲染不全时的视觉证据 | 先 TOPMOST 置顶再截，否则截到别的窗口 |

### Kaleidoscope 案例（同类布局保留对照）
- **SunnyUI 布局坑**：UIPanel 嵌套 UIPanel 时子控件定位可能偏移——**纯背景容器（工具条/状态条/预设条/中间白色层）一律用原生 Panel**；条内 SunnyUI 控件自绘不受父容器影响。
- **条件显示容器（Visible 切换）的布局时序**：Visible=false 期间不参与 Dock 布局，早期对其子控件的定位是错的且 Resize 补偿不保证触发——**每次 Visible=true 后必须显式重排一次**。
- **脚本本身的坑**：tasklist 会把长映像名截断到 25 字符——启动模式用 Popen/Start-Process 返回的 PID，attach 用前缀匹配；主窗体句柄可能延迟就绪（MainWindowHandle=0）——必须轮询等待，不能取一次就用。

### 无边框小弹窗宽度被钳到 136（AgingTestSystem V1.88.25）
- 现象：`FormBorderStyle=None` + `ClientSize=(114,66)` 显示出来 136x66，且与内容无关（裸窗二分实锤）。
- 根因：Windows 最小跟踪宽度 min-track 136px；从未设过 `MinimumSize` 时 WinForms 不碰 MINMAXINFO，系统钳制生效。
- 修法：`MinimumSize = new Size(1, 1)` 让 WinForms 接管（`(0,0)` 不接管照样被钳）。附带：运行时物理像素定尺寸的纯代码弹窗一律 `AutoScaleMode=None`，否则再跟缩一次。
- 教训：尺寸对不上先二分到空窗，别在业务代码里打转。
### 小字"糊"先证伪再动手（同上，工作站 4.8pt）
- 怀疑 `DoubleBuffered` 逼文字走离屏灰度 AA：A/B 开关截图＋像素指标（黑像素占比 coreFrac＋平均边缘梯度 meanEdge）逐字相同→证伪，不碰。
- 加粗 A/B：黑像素 +34% 且同屏对比明显更清楚→落改（省略号/截断兜底不盖框）。
- 教训：渲染质量猜想必须配"同坐标双截图＋像素指标"，目测像≠真因；证伪结论本身也要记（防后人重踩）。
### Sunny UILabel 缺省 AutoSize=false（同上，顶栏 9 列案）
- 原生 Label 缺省 true，Sunny 反直觉缺省 false：Fill 的项目名只报 0 首选宽，AutoSize 列被压成固定前缀宽、内容看不见。
- 排查先 dump 各控件 `AutoSize` 属性值；AutoSize 列的填充子必须显式开。
### 标准排查流程（布局错位类）
1. 跑 `Get-ControlTree`（必要时 `--click` 让条件显示容器先出现），拿全部矩形；
2. 对照判据找异常：Fill 底边==父底边？控件矩形超出父容器？与兄弟控件矩形重叠？
3. 定位到具体控件后，查它的**父容器 Controls 添加顺序**与 **Visible 切换后的重排调用**；
4. 改完用 `Get-WindowShot` 截图 + 再跑一次 `Get-ControlTree` 双重验证（Bounds 与渲染都要对）。

## 十二、验证与收尾（必做）

- 构建通过（MSBuild 输出 exe、无 error）。
- harness 复跑，对比修复前/后同坐标像素颜色，确认目标线/色消失且不引入新问题。
- 冒烟测试主程序：`Start-Process` 启动 exe，等几秒确认进程存活再 `Stop-Process`。
- 更新本项目 `CHANGELOG.md`（写清改动范围/为什么/优化点），必要时更新项目文档、`README.md`（各项目文档名见附录 A）。
- 删除 bin/输出目录下生成的 harness exe；源文件在临时目录不提交。
- UTF-8 自检：`[IO.File]::ReadAllText(path, [Text.Encoding]::UTF8).Contains("预期中文")`。
- 调试完有可复用的新套路/新踩坑：回写到本 skill（新增/补充小节、追加踩坑条目），并给来源项目记一笔。

## 十三、附录 A：项目档案（开工先查表）

> 保鲜约定：本项目改构建输出（csproj 路径/输出目录/主 exe 名）时同步改对应行
> （各项目 AGENTS 里有同样一句话，双保险）；附录 A 没有本项目时，按表头补一行再开工。

| 项目 | 仓库根 | 构建（MSBuild） | 输出目录 | 主 exe |
|---|---|---|---|---|
| AgingTestSystem | `E:\Project\AgingTestSystem` | `AgingTestSystem/AgingTestSystem.csproj` | `AgingTestSystem\bin\Debug\` | `烧屏测试控制中心.exe`（V1.106 起中文名；AssemblyName 中文，命名空间仍 `AgingTestSystem`） |
| CommandCenter | `E:\Project\CommandCenter` | `CommandCenter/CommandCenter.csproj` | `CommandCenter\bin\Debug\` | `CommandCenter.exe` |
| HuaJiVision | `E:\Project\HJVision` | `GYZVision/HuaJiVision.csproj` | `00_ExeBuild\`（运行目录） | `HuaJiVision.exe`（另有提权帮手 `Tools/NetAdminHelper/NetAdminHelper.csproj` → 同目录 `NetAdminHelper.exe`，改网口 IP/改名用，随主 exe 部署） |
| Kaleidoscope | `E:\Project\kaleidoscope` | `ConfigEditor/KaleidoscopeConfigEditor.csproj` | `ConfigEditor\bin\Debug\` | `KaleidoscopeConfigEditor.exe` |

- **AgingTestSystem**：harness 依赖 `SunnyUI.dll` / `SunnyUI.Common.dll` / `NModbus.dll` / `NModbus.Serial.dll` / `Newtonsoft.Json.dll` / `DocumentFormat.OpenXml.dll` / `DocumentFormat.OpenXml.Framework.dll`；对照窗体 `SettingsForm(DeviceConfig)` / `RecipeManagerForm()` / `WorkstationGridView`；文档 `docs/通讯接入.md`；坐标配置模型 `Models/PanelLayoutConfig.cs`（可被 `PanelLayout.json` 覆盖）。
- **CommandCenter**：对照 `Controls/CameraDisplayControl.cs`（双击案例）/ `dgvPrograms`（ComboBox 案例）；文档 `docs/CommandCenter.md`；另有 `commandcenter-test` skill（回归测试，UI 视觉类问题不归它，归本 skill）。
- **HuaJiVision**：对照 `mFormScriptEdit`（ElementHost）/ `mFormLaserMark` / `mFormDevPanel`；界面文件头 ASCII 图约定见该项目 AGENTS；注意运行目录现场文件与授权码红线（只读该项目 AGENTS，不在本 skill 展开）。
- **Kaleidoscope**：本 skill `scripts/` 原型来源项目；对照 `ConfigEditor MainForm`（`UpdateBrandCombo` / `LayoutPresetBar`）；界面布局关键点见该项目 AGENTS。

## 十四、来源

本 skill 由 4 个项目 skill 合并而成，完整来源、合并修坑与版本历史见本目录
`CHANGELOG.md`（v1.0.0 节）。四处源 skill 已删除，后续沉淀统一回写到本 skill。
