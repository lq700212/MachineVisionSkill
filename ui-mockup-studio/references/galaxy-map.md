# galaxy 分类地图 + WinForms / WPF 双栈映射

> galaxy 是 **视觉语言库**，不是代码库。你从里面拿的是：主色组合、圆角尺度、渐变方向、
> 阴影浓度、悬停反馈、动画节奏——**不是把 CSS 抄进项目**。
> 本文给两张落地地图：`CSS → WinForms（GDI+/SunnyUI）` 与 `CSS → WPF（XAML）`。

---

## 一、galaxy 结构与检索

### 1.1 目录

```
D:\galaxy\           （或 E:\Project\galaxy，以 resolve_galaxy.py 缓存为准）
├── Buttons/             1231 个 .html
├── Cards/                726
├── Checkboxes/           171
├── Forms/                180
├── Inputs/               226
├── Notifications/         23
├── Patterns/             103
├── Radio-buttons/        102
├── Toggle-switches/      260
├── Tooltips/              62
└── loaders/              718
```

每个 `.html` 是**一个独立组件**：HTML 片段 + `<style>`，头部第一行注释就是元数据：

```html
<!-- From Uiverse.io by 0x-Sarthak - Tags: button, hover, rounded, animated, hover button -->
```

`galaxy_search.py` 只读每个文件前 4KB 抽 tags，所以检索很快（3800+ 文件 < 2 秒）。
文件名格式：`<作者>_<名字>-<序号>.html`。

### 1.2 分类用途（选型时按这个找）

| 分类 | 主要用途 | 提取什么 |
| --- | --- | --- |
| **Buttons** | 主/次/图标/危险按钮 | 圆角、渐变方向、悬停位移/发光、按下缩放比例 |
| **Cards** | 业务卡片、KPI 容器 | 边框浓度、内外阴影、玻璃拟态、标题与内容的间距 |
| **Forms** | 整组表单（登录/配置） | 字段纵向节奏、标签位置、分组方式、按钮区位置 |
| **Inputs** | 单输入框/搜索框 | 聚焦描边、占位色、图标位置、圆角 |
| **Toggle-switches** | 开关 | 轨道尺寸比、圆点行程、开/关颜色、过渡时长 |
| **Checkboxes** | 多选/同意项 | 勾选动效、选中填充方式 |
| **Radio-buttons** | 互斥选择 | 选中环、卡片式单选 |
| **Notifications** | Toast/提示条/徽标 | 状态色、图标、圆角、进出场 |
| **Tooltips** | 悬停说明 | 箭头、延迟、最大宽度 |
| **loaders** | 加载环/条/骨架 | 线宽、转速、渐变扫光 |
| **Patterns** | 背景纹理/网格/光斑 | 低对比纹理、径向光晕（只用于登录页/空态） |

### 1.3 检索词表（中 → 英，直接喂 `--q`）

| 想要的感觉 | 检索词 |
| --- | --- |
| 渐变按钮 | `gradient` `animated gradient` `colorful` |
| 胶囊/圆角 | `pill` `rounded` `radius` |
| 描边/幽灵 | `outline` `ghost` `border` |
| 发光/霓虹 | `neon` `glow` `light` |
| 玻璃拟态 | `glass` `glassmorphism` `blur` |
| 新拟态 | `neumorphism` `soft` `3d` |
| 极简 | `minimal` `clean` `simple` `flat` |
| 工业/硬朗 | `brutalist` `sharp` `dark` `tech` |
| 悬停反馈 | `hover` `hover effect` `lift` |
| 加载 | `spinner` `loader` `skeleton` `pulse` |
| 开关 | `toggle` `switch` `theme-switch` |
| 卡片 | `card` `glass card` `profile card` `stat card` |

```powershell
$G = "C:\Users\Administrator\.config\opencode\skills\ui-mockup-studio\scripts\galaxy_search.py"
python $G --category Buttons --q gradient --limit 8
python $G --category Cards --q glass --limit 6
python $G --q neon --any --limit 10          # 跨分类
python $G --show "Buttons/0x-Sarthak_hungry-penguin-30.html"
```

### 1.4 选型产出（不是代码，是 6 个决策）

1. 主色 + 辅色（各给 hex）
2. 圆角尺度（卡片 / 按钮 / 输入框三档）
3. 密度（表格行高、卡片内边距）
4. 阴影策略（平面无阴影 / 仅浮层 / 全局柔和）
5. 强调手法（渐变胶囊 / 发光边 / 细边框大留白 / 玻璃）
6. 动效节奏（悬停 x ms、入场 y ms、循环 z s）

这 6 个决策直接写进 CSS Token，再映射到两栈。

---

## 二、CSS → WPF 映射（XAML）

### 2.1 属性对照表

| CSS | WPF | 注意 |
| --- | --- | --- |
| `background:#3e8bff` | `Background="{DynamicResource PrimaryBrush}"` | **换肤必须 DynamicResource** |
| `background:linear-gradient(135deg,a,b)` | `<LinearGradientBrush StartPoint="0,0" EndPoint="1,1">` | CSS 角度换算：135deg ≈ (0,0)→(1,1) |
| `border:1px solid #2a3546` | `BorderBrush` + `BorderThickness="1"` | 1px = 1 DIP，高 DPI 自动缩放 |
| `border-radius:10px` | `CornerRadius="10"` | 只能用在 Border/ControlTemplate |
| `padding:16px` | `Padding="16"` | Thickness 顺序：左,上,右,下 |
| `margin:14px` | `Margin="14"` | 同上 |
| `gap:14px` | `Margin` 或 `StackPanel.Spacing`（.NET 6+） | .NET Framework 用 Margin |
| `box-shadow:0 8px 24px rgba(0,0,0,.35)` | `<DropShadowEffect BlurRadius="24" ShadowDepth="8" Opacity="0.35"/>` | **只给浮层**，大列表掉帧 |
| `color:#e6edf7` | `Foreground="{DynamicResource TextBrush}"` | |
| `font-size:13px` | `FontSize="13"` | WPF 单位是 DIP，1:1 |
| `font-weight:700` | `FontWeight="Bold"` | 600 用 `SemiBold` |
| `letter-spacing:.05em` | `Typography` 不直接支持 | 用 `TextBlock` + 自定义，或忽略 |
| `transition:all .2s ease` | `DoubleAnimation Duration="0:0:0.2"` + `CubicEase` | 放 Storyboard/Trigger |
| `transform:translateY(-2px)` | `TranslateTransform.Y` + `DoubleAnimation` | |
| `transform:scale(.95)` | `ScaleTransform` + 动画 | 中心点 `RenderTransformOrigin=".5,.5"` |
| `opacity:.4` | `Opacity="0.4"` | |
| `cursor:pointer` | `Cursor="Hand"` | |
| `:hover` | `Trigger Property="IsMouseOver" Value="True"` | 放 ControlTemplate.Triggers |
| `:active` | `Trigger Property="IsPressed"` | |
| `:disabled` | `Trigger Property="IsEnabled" Value="False"` | |
| `::before/::after` | 额外 `Border`/`Path` 图层 | WPF 无伪元素 |
| `backdrop-filter:blur()` | 无原生；用半透明色 + 模糊位图（昂贵） | 工业软件**不建议** |

### 2.2 Token 字典（App.xaml）

```xml
<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <!-- 方案 A 深夜中控：改这一块就能换整套视觉 -->
  <SolidColorBrush x:Key="PrimaryBrush"      Color="#3E8BFF"/>
  <SolidColorBrush x:Key="PrimaryDimBrush"   Color="#1E3A5F"/>
  <SolidColorBrush x:Key="BgBrush"           Color="#0B1017"/>
  <SolidColorBrush x:Key="PanelBrush"        Color="#111A24"/>
  <SolidColorBrush x:Key="Panel2Brush"       Color="#16212E"/>
  <SolidColorBrush x:Key="BorderBrush"       Color="#233044"/>
  <SolidColorBrush x:Key="TextBrush"         Color="#E6EDF7"/>
  <SolidColorBrush x:Key="MutedBrush"        Color="#8A9BB0"/>
  <SolidColorBrush x:Key="OkBrush"           Color="#22C55E"/>
  <SolidColorBrush x:Key="WarnBrush"         Color="#F59E0B"/>
  <SolidColorBrush x:Key="NgBrush"           Color="#EF4444"/>

  <CornerRadius x:Key="CardRadius">10</CornerRadius>
  <CornerRadius x:Key="ButtonRadius">8</CornerRadius>
  <sys:Double xmlns:sys="clr-namespace:System;assembly=mscorlib" x:Key="GapSize">14</sys:Double>
</ResourceDictionary>
```

> 换肤落地：`Application.Current.Resources.MergedDictionaries[0] = new ResourceDictionary { Source = ... }`，
> 所有引用必须 `{DynamicResource}`，否则切了不刷新。

### 2.3 主按钮（圆角 + 渐变 + 悬停/按下/禁用）

```xml
<Style x:Key="PrimaryButton" TargetType="Button">
  <Setter Property="Foreground" Value="White"/>
  <Setter Property="FontSize" Value="13"/>
  <Setter Property="FontWeight" Value="SemiBold"/>
  <Setter Property="Padding" Value="18,8"/>
  <Setter Property="Cursor" Value="Hand"/>
  <Setter Property="SnapsToDevicePixels" Value="True"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="Button">
        <Border x:Name="bd" CornerRadius="{DynamicResource ButtonRadius}" Padding="{TemplateBinding Padding}">
          <Border.Background>
            <LinearGradientBrush StartPoint="0,0" EndPoint="1,1">
              <GradientStop Color="#3E8BFF" Offset="0"/>
              <GradientStop Color="#22D3EE" Offset="1"/>
            </LinearGradientBrush>
          </Border.Background>
          <Border.RenderTransform>
            <ScaleTransform x:Name="sc" ScaleX="1" ScaleY="1"/>
          </Border.RenderTransform>
          <Border.RenderTransformOrigin>0.5,0.5</Border.RenderTransformOrigin>
          <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
        </Border>
        <ControlTemplate.Triggers>
          <Trigger Property="IsMouseOver" Value="True">
            <Setter TargetName="bd" Property="Effect">
              <Setter.Value>
                <DropShadowEffect BlurRadius="18" ShadowDepth="0" Opacity="0.45" Color="#3E8BFF"/>
              </Setter.Value>
            </Setter>
          </Trigger>
          <Trigger Property="IsPressed" Value="True">
            <Setter TargetName="sc" Property="ScaleX" Value="0.96"/>
            <Setter TargetName="sc" Property="ScaleY" Value="0.96"/>
          </Trigger>
          <Trigger Property="IsEnabled" Value="False">
            <Setter TargetName="bd" Property="Opacity" Value="0.4"/>
            <Setter Property="Cursor" Value="Arrow"/>
          </Trigger>
        </ControlTemplate.Triggers>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>
```

### 2.4 卡片

```xml
<Style x:Key="Card" TargetType="Border">
  <Setter Property="Background" Value="{DynamicResource PanelBrush}"/>
  <Setter Property="BorderBrush" Value="{DynamicResource BorderBrush}"/>
  <Setter Property="BorderThickness" Value="1"/>
  <Setter Property="CornerRadius" Value="{DynamicResource CardRadius}"/>
  <Setter Property="Padding" Value="16"/>
</Style>
```

> 阴影只在**浮层**用 `DropShadowEffect`；页面里的卡片用 1px 边框区分层级即可
> （工业软件几十张卡片都加阴影 = 滚动掉帧）。

### 2.5 开关（ToggleSwitch）

```xml
<Style x:Key="ToggleSwitch" TargetType="ToggleButton">
  <Setter Property="Width" Value="40"/>
  <Setter Property="Height" Value="22"/>
  <Setter Property="Cursor" Value="Hand"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="ToggleButton">
        <Border x:Name="track" CornerRadius="11" Background="{DynamicResource BorderBrush}">
          <Ellipse x:Name="knob" Width="16" Height="16" Fill="White"
                   HorizontalAlignment="Left" Margin="3,0,0,0">
            <Ellipse.RenderTransform>
              <TranslateTransform x:Name="tt" X="0"/>
            </Ellipse.RenderTransform>
          </Ellipse>
        </Border>
        <ControlTemplate.Triggers>
          <Trigger Property="IsChecked" Value="True">
            <Setter TargetName="track" Property="Background" Value="{DynamicResource PrimaryBrush}"/>
            <Trigger.EnterActions>
              <BeginStoryboard>
                <Storyboard>
                  <DoubleAnimation Storyboard.TargetName="tt" Storyboard.TargetProperty="X"
                                   To="18" Duration="0:0:0.18">
                    <DoubleAnimation.EasingFunction><CubicEase EasingMode="EaseOut"/></DoubleAnimation.EasingFunction>
                  </DoubleAnimation>
                </Storyboard>
              </BeginStoryboard>
            </Trigger.EnterActions>
            <Trigger.ExitActions>
              <BeginStoryboard>
                <Storyboard>
                  <DoubleAnimation Storyboard.TargetName="tt" Storyboard.TargetProperty="X"
                                   To="0" Duration="0:0:0.18"/>
                </Storyboard>
              </BeginStoryboard>
            </Trigger.ExitActions>
          </Trigger>
        </ControlTemplate.Triggers>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>
```

### 2.6 弹窗入场

```xml
<Window.Triggers>
  <EventTrigger RoutedEvent="Window.Loaded">
    <BeginStoryboard>
      <Storyboard>
        <DoubleAnimation Storyboard.TargetProperty="Opacity" From="0" To="1" Duration="0:0:0.16"/>
        <DoubleAnimation Storyboard.TargetProperty="(UIElement.RenderTransform).(TranslateTransform.Y)"
                         From="10" To="0" Duration="0:0:0.2">
          <DoubleAnimation.EasingFunction><CubicEase EasingMode="EaseOut"/></DoubleAnimation.EasingFunction>
        </DoubleAnimation>
      </Storyboard>
    </BeginStoryboard>
  </EventTrigger>
</Window.Triggers>
<Window.RenderTransform><TranslateTransform/></Window.RenderTransform>
```

### 2.7 WPF 落地坑（漏一条就返工）

1. **触发器死区**：要被 Trigger 切换的属性（尤其 Visibility），缺省值必须写在 `Style.Setter`；
   写在元素标签上是本地值，优先级更高，触发器永远不生效。
2. **换肤必须 DynamicResource**，StaticResource 切主题不刷新。
3. **互斥 RadioButton 只让一只双向绑 bool**，另一只 `Mode=OneWay` + 取反转换器只做显示。
4. **独立 Grid 的 Auto 列互不对齐**：标签列统一固定宽，或 `SharedSizeGroup`。
5. **Expander 折叠内容绑定仍有效**（值照常保存），低频参数收进去安全。
6. **PasswordBox 不可绑定**：事件转交 + "值不同才回写"。
7. **高 DPI 天然适配**，但图片/图标要用矢量或 `UseLayoutRounding="True"` 防半像素模糊。

---

## 三、CSS → WinForms 映射（GDI+ / SunnyUI）

### 3.1 属性对照表

| CSS | WinForms | 注意 |
| --- | --- | --- |
| `background:#3e8bff` | `BackColor = Color.FromArgb(0x3E,0x8B,0xFF)` | 统一走 Theme 静态类 |
| `linear-gradient` | `new LinearGradientBrush(rect, c1, c2, 45f)` | 必须 `using` 释放 |
| `border:1px solid` | `Pen` + `DrawRectangle` / `UIPanel.RectColor` | 1px 在 125% DPI 会变 1.25px |
| `border-radius:10px` | 自绘 `GraphicsPath.AddArc` | 见 3.2 |
| `padding:16px` | `Padding = new Padding(16)` | 用布局，不要手算坐标 |
| `margin` | `Margin` + `TableLayoutPanel` | |
| `box-shadow` | 双层 Panel（偏移 2px + 黑 35%）；或 `CS_DROPSHADOW` | 无原生阴影 |
| `color:#e6edf7` | `ForeColor` | |
| `font-size:13px` | `Font("Microsoft YaHei UI", 9.75F)` | **px × 0.75 = pt** |
| `font-weight:700` | `FontStyle.Bold` | |
| `transition` | `Timer`（≥30ms）+ 双缓冲 | 无内建动画 |
| `:hover` | `MouseEnter/Leave` + `Invalidate()` | |
| `:active` | `MouseDown/Up` | |
| `::before/::after` | 自绘时多画一层 | |
| `opacity` | `Color.FromArgb(alpha, r, g, b)` | 控件整体透明度需 layered window |

### 3.2 自绘圆角：标准配方（四角不脏边的关键）

```csharp
/// <summary>
/// 生成圆角矩形路径。r 为圆角半径（像素）。
/// 关键点：① AntiAlias 必须开；② 矩形向内收 0.5px 做半像素补偿；
/// ③ 圆角半径必须 <= min(w,h)/2，否则 AddArc 会画歪。
/// </summary>
public static GraphicsPath RoundedRect(RectangleF r, float radius)
{
    var p = new GraphicsPath();
    float d = Math.Min(radius * 2f, Math.Min(r.Width, r.Height));
    if (d <= 0f) { p.AddRectangle(r); return p; }
    p.AddArc(r.X, r.Y, d, d, 180, 90);                 // 左上
    p.AddArc(r.Right - d, r.Y, d, d, 270, 90);          // 右上
    p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);   // 右下
    p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);          // 左下
    p.CloseFigure();
    return p;
}
```

自绘按钮（**不设 Region**，靠自绘背景防脏边）：

```csharp
public sealed class ThemeButton : Button
{
    public int Radius { get; set; } = 8;
    public Color Fill1 { get; set; } = Color.FromArgb(0x3E, 0x8B, 0xFF);
    public Color Fill2 { get; set; } = Color.FromArgb(0x22, 0xD3, 0xEE);
    public bool Primary { get; set; } = true;

    private bool _hover, _down;

    public ThemeButton()
    {
        // 双缓冲三件套：不写会闪烁
        SetStyle(ControlStyles.OptimizedDoubleBuffer |
                 ControlStyles.AllPaintingInWmPaint |
                 ControlStyles.UserPaint |
                 ControlStyles.ResizeRedraw, true);
        FlatStyle = FlatStyle.Flat;
        FlatAppearance.BorderSize = 0;
        Cursor = Cursors.Hand;
    }

    protected override void OnMouseEnter(EventArgs e) { _hover = true; Invalidate(); base.OnMouseEnter(e); }
    protected override void OnMouseLeave(EventArgs e) { _hover = false; _down = false; Invalidate(); base.OnMouseLeave(e); }
    protected override void OnMouseDown(MouseEventArgs e) { _down = true; Invalidate(); base.OnMouseDown(e); }
    protected override void OnMouseUp(MouseEventArgs e) { _down = false; Invalidate(); base.OnMouseUp(e); }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.PixelOffsetMode = PixelOffsetMode.HighQuality;

        // 半像素补偿：1px 边框才不会糊成 2px
        var rect = new RectangleF(0.5f, 0.5f, Width - 1f, Height - 1f);
        using (var path = RoundedRect(rect, Radius))
        {
            if (Primary && Enabled)
            {
                using (var brush = new LinearGradientBrush(rect, Fill1, Fill2, 45f))
                    g.FillPath(brush, path);
            }
            else
            {
                using (var brush = new SolidBrush(_hover ? Color.FromArgb(30, Fill1) : Color.Transparent))
                    g.FillPath(brush, path);
                using (var pen = new Pen(Color.FromArgb(120, Fill1), 1f))
                    g.DrawPath(pen, path);
            }

            if (_hover && Primary)
            {
                // 悬停：外圈淡光（不改变尺寸，避免布局跳动）
                using (var pen = new Pen(Color.FromArgb(70, Fill2), 2f))
                    g.DrawPath(pen, path);
            }
        }

        var textRect = ClientRectangle;
        if (_down) textRect.Offset(0, 1);   // 按下位移 1px，模拟 scale(.96)
        TextRenderer.DrawText(g, Text, Font, textRect, ForeColor,
            TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter |
            TextFormatFlags.EndEllipsis);

        if (!Enabled)   // 禁用：整体压暗，不要隐藏
        {
            using (var b = new SolidBrush(Color.FromArgb(110, BackColor)))
            using (var p2 = RoundedRect(rect, Radius))
                g.FillPath(b, p2);
        }
    }
}
```

> **四角脏边十坑的根因**：`Region` 是硬裁剪（不抗锯齿），圆角处必有锯齿/黑边。
> 治本 = 自绘背景 + `AntiAlias` + 半像素补偿，**且不设 Region**；
> 若父容器背景不是纯色，让自绘控件先填父色（`BackColor = Parent.BackColor`）。
> 只有当控件必须"真正挖空"（如叠在图片上）时才用 Region，并接受锯齿。

### 3.3 圆角卡片 / 面板

```csharp
public sealed class ThemeCard : Panel
{
    public int Radius { get; set; } = 10;
    public Color BorderColor { get; set; } = Color.FromArgb(0x23, 0x30, 0x44);

    public ThemeCard()
    {
        SetStyle(ControlStyles.OptimizedDoubleBuffer |
                 ControlStyles.AllPaintingInWmPaint |
                 ControlStyles.UserPaint |
                 ControlStyles.ResizeRedraw, true);
        BackColor = Color.FromArgb(0x11, 0x1A, 0x24);   // 或 Theme.Panel
        Padding = new Padding(16);
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        var rect = new RectangleF(0.5f, 0.5f, Width - 1f, Height - 1f);
        using (var path = RoundedRect(rect, Radius))
        using (var fill = new SolidBrush(BackColor))
        using (var pen = new Pen(BorderColor, 1f))
        {
            g.FillPath(fill, path);
            g.DrawPath(pen, path);
        }
        base.OnPaint(e);   // 子控件由 WinForms 自己画
    }
}
```

### 3.4 开关（自绘 CheckBox）

```csharp
public sealed class ThemeSwitch : CheckBox
{
    public ThemeSwitch()
    {
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint |
                 ControlStyles.AllPaintingInWmPaint, true);
        Size = new Size(40, 22);
        Cursor = Cursors.Hand;
        Text = string.Empty;
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        var track = new RectangleF(0.5f, 0.5f, Width - 1f, Height - 1f);
        float r = track.Height / 2f;

        using (var path = RoundedRect(track, r))
        using (var b = new SolidBrush(Checked ? Theme.Primary : Theme.Border))
            g.FillPath(b, path);

        float d = track.Height - 6f;
        float x = Checked ? track.Right - d - 3f : track.X + 3f;
        using (var b = new SolidBrush(Color.White))
            g.FillEllipse(b, x, track.Y + 3f, d, d);
    }
}
```

> 要"滑动"动画就用 `Timer` 插值 x（30ms/帧，180ms 到位），
> 每帧只 `Invalidate()` 开关自身，不要整窗重绘。

### 3.5 阴影（无原生方案）

- **卡片**：不加阴影，用 1px 边框（工业风首选，性能最好）。
- **浮层**（弹窗/下拉）：`FormBorderStyle.None` + 双层 Panel：
  底层 Panel 偏移 (0,2)、`BackColor = Color.FromArgb(60, 0, 0, 0)`、同圆角；
  上层 Panel 画内容。或用 `CreateParams.ClassStyle |= 0x20000 (CS_DROPSHADOW)`。
- **禁止**给 `DataGridView`/滚动列表里的每张卡加阴影——重绘成本爆炸。

### 3.6 动效

```csharp
// 180ms 淡入 + 上移 8px：用 Timer 插值，30ms/帧
private readonly Timer _anim = new Timer { Interval = 30 };
private int _elapsed;

private void StartEnterAnim()
{
    _elapsed = 0;
    _anim.Tick += (s, e) =>
    {
        _elapsed += _anim.Interval;
        float t = Math.Min(1f, _elapsed / 180f);
        float eased = 1f - (float)Math.Pow(1 - t, 3);   // CubicEaseOut
        Opacity = eased;                                 // 窗体级
        Top = _targetTop + (int)(8 * (1 - eased));       // 控件级用 Location
        if (t >= 1f) { _anim.Stop(); Top = _targetTop; Opacity = 1; }
    };
    _anim.Start();
}
```

> `Form.Opacity` 是窗体级；控件级透明度要用 `Color.FromArgb(alpha,...)` 逐次重绘，
> 或干脆只做位移（更省、更像工业软件）。

### 3.7 WinForms 落地坑（漏一条就返工）

1. **高 DPI 三要素**：`AutoScaleMode = AutoScaleMode.Dpi` +
   `AutoScaleDimensions = new SizeF(96F, 96F)`（与设计时一致）+ 布局用容器。
   纯代码建窗体这三样都要手写，不会自动生成。
2. **绝对坐标 + 高 DPI = 逐像素偏移**：用 `TableLayoutPanel` / `FlowLayoutPanel` / `Dock`。
3. **自绘必开双缓冲**（三件套），否则滚动闪烁。
4. **DataGridView 双缓冲要反射**（protected 属性）；列宽用 `FillWeight`；
   `CellFormatting` 里缓存 Brush/Font，不要每次 new。
5. **字体换算 px × 0.75 = pt**；微软雅黑 UI 9pt ≈ 12px @96DPI。
6. **动画 Timer ≥ 30ms**，只 `Invalidate(变化区域)`。
7. **换肤统一入口**：`IThemeAware.ApplyTheme()` 递归遍历，不要在 `Paint` 里读 ini。
8. **无边框窗体拖动/圆角**：`WndProc` 处理 `WM_NCHITTEST`；圆角走"自绘 + 不设 Region"。
9. **弹窗**：`ShowDialog()` 前设 `StartPosition = CenterParent`；`AutoScaleMode` 与主窗一致。
10. **不用"隐藏"表达"不可用"**：置灰只读 + ToolTip 说明原因，比消失更好懂。

---

## 四、两栈选择速查

| 维度 | WinForms | WPF |
| --- | --- | --- |
| 圆角 | 自绘 GraphicsPath（不设 Region） | `CornerRadius` 原生 |
| 渐变 | `LinearGradientBrush` | `LinearGradientBrush` |
| 阴影 | 双层 Panel / CS_DROPSHADOW | `DropShadowEffect`（仅浮层） |
| 动画 | Timer 插值 + 双缓冲 | `DoubleAnimation` + `CubicEase` |
| 换肤 | 递归遍历 + `IThemeAware` | `DynamicResource` 字典切换 |
| 高 DPI | 三要素 + 容器布局 | 天然 DIP |
| 矢量图标 | 字体图标 / 位图 | `Path` / `Geometry` |
| 大列表性能 | DataGridView 虚拟模式 | VirtualizingStackPanel |
| 设计稿→代码工作量 | 高（一切自绘） | 低（模板化） |

**结论**：同一套设计稿在 WPF 里落地成本约为 WinForms 的 60%；
WinForms 项目要预留"自绘控件库"（ThemeButton/ThemeCard/ThemeSwitch）的工期。

---

## 五、落地检查清单

- [ ] 主色/辅色/状态色全部进 Theme 类或资源字典，**页面里没有 hex**
- [ ] 圆角三档（卡片/按钮/输入框）与设计稿一致
- [ ] 字体按 px×0.75 换算，行高与设计稿密度一致
- [ ] 主操作按钮全项目只有一个样式（Primary），次操作统一 ghost
- [ ] 悬停/按下反馈存在且 ≤200ms
- [ ] 禁用态是置灰不是隐藏，ToolTip 说明原因
- [ ] 高 DPI 在 125%/150% 下截图不错位
- [ ] 浮层有阴影、平面无阴影
- [ ] 动效可被"关闭动效"配置整体关掉
- [ ] 换肤后所有控件都变（没有漏掉写死色的）
