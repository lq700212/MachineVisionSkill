# -*- coding: utf-8 -*-
"""PPT 示意图竖直尺寸标注（视觉硬件选型 skill 内置模块）。

2026-11-23 客户退回事故固化
---------------------------
示意图上 `320mm` / `220mm` 的标注端点被写死成 1.72/4.67，而相机顶面实际
1.40、工件表面 4.55：上端悬在空气里、下端扎进工件；`220mm` 还只有一条光秃
竖线，没有两端刻度横线。客户一眼就看出"标注没贴到实体"。

第二次退回（同日）：坐标贴对了实体，但**物理语义错了**——`320mm` 工作距离
从相机顶面起算，把整个机身高度算进了 WD。工业视觉里 WD 是**镜头前端面到
检测面**的距离，相机机身不计入。所以本模块提供专用入口 `add_wd_dim()`，
强制 `optic.bottom → target.top`，不要再用 `add_dim_v` 手拼工作距离。

根因不是"某一次算错"，而是**标注坐标靠手写**——布局一改就必然脱节。
所以正确画法不能停留在文档里，必须做成唯一入口：

* 端点优先直接传实体 shape，由本模块读 `top/height` 计算边界，物理上无法写错；
* 退一步也要传"从实体坐标派生出来的变量"（CAM_TOP / WORK_TOP），不许传字面量；
* 刻度、尺寸界线、文字居中全部内置，杜绝"漏画刻度"。

用法（推荐：绑定实体对象，边界自动读取）::

    import sys
    sys.path.insert(0, r'C:\\Users\\Administrator\\.config\\opencode\\skills\\视觉硬件选型\\tools')
    from ppt_diagram import add_wd_dim

    cam  = add_box(s, 2.25, 1.40, 1.05, 0.62, ...)   # 项目自己的 add_box 必须 return shape
    lens = add_box(s, 2.55, 2.02, 0.45, 0.55, ...)
    work = add_box(s, 1.55, 4.55, 2.45, 0.28, ...)
    light = add_box(s, 1.85, 2.62, 1.85, 0.28, ...)

    # 工作距离 = 光学件前端面 → 检测面（禁止从相机顶面起算！）
    add_wd_dim(s, x=0.80, label='320mm', optic=lens, target=work)
    add_wd_dim(s, x=1.30, label='220mm', optic=light, target=work,
               text_side='right')

用法（已有实体派生变量，同样合法）::

    add_wd_dim(s, x=0.80, label=f'{wd:.0f}mm', optic=LENS_BOT, target=WORK_TOP)

构建期自检（可选，把问题挡在交付前）::

    issues = self_check(slide)
    if issues:
        raise SystemExit('尺寸标注不合格: ' + '; '.join(issues))

`check_ppt_quality.py` 的 C8 会对成品再做一次机检（端点对齐实体边界 + 两端有刻度）。
"""
from __future__ import annotations

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

__all__ = ['add_dim_v', 'add_wd_dim', 'edge_y', 'self_check', 'DEFAULT_COLOR']

DEFAULT_COLOR = RGBColor(0x40, 0x40, 0x40)
DEFAULT_FONT = '微软雅黑'

_TOP_ALIASES = ('top', 'upper', 't')
_BOTTOM_ALIASES = ('bottom', 'lower', 'b')
_CENTER_ALIASES = ('center', 'centre', 'middle', 'c')


def _to_inches(value, name='value'):
    """Length / Emu / 数值（默认英寸）→ 英寸 float。

    注意：pptx 的 Length 是 int 子类，必须先看 .inches 属性再判数值类型，
    否则会把 1280160 EMU 当成 1280160 英寸。
    """
    if value is None:
        raise ValueError(f'ppt_diagram: {name} 为 None，形状缺少尺寸信息')
    if isinstance(value, bool):
        raise TypeError(f'ppt_diagram: {name} 不能是 bool')
    inches = getattr(value, 'inches', None)
    if inches is not None:
        return float(inches)
    if isinstance(value, (int, float)):
        return float(value)
    raise TypeError(f'ppt_diagram: {name} 不是长度或数值（{type(value).__name__}）')


def edge_y(target, which='top'):
    """取实体的边界 y 坐标（英寸）。

    Parameters
    ----------
    target : pptx shape 或 数值
        传 shape 时按 `which` 读取上/下/中边界；传数值时视为已是英寸边界值。
    which : {'top', 'bottom', 'center'}
    """
    if not hasattr(target, 'top'):
        return _to_inches(target, 'y')
    if target is None:
        raise ValueError('ppt_diagram: edge_y 收到 None，检查实体变量是否已赋值')
    top = _to_inches(target.top, 'shape.top')
    height = _to_inches(target.height, 'shape.height')
    w = str(which).strip().lower()
    if w in _TOP_ALIASES:
        return top
    if w in _BOTTOM_ALIASES:
        return top + height
    if w in _CENTER_ALIASES:
        return top + height / 2.0
    raise ValueError(f'ppt_diagram: 不支持的边界 {which!r}（top / bottom / center）')


def _ext_end(start, target, direction, default_len, gap):
    """计算尺寸界线的终点 x：自动伸到实体边缘外侧 gap 处，取不到就用默认长度。"""
    if hasattr(target, 'left') and hasattr(target, 'width'):
        try:
            left = _to_inches(target.left, 'shape.left')
            width = _to_inches(target.width, 'shape.width')
        except (ValueError, TypeError):
            left = width = None
        if left is not None and width is not None:
            if direction == 'right':
                stop = left - gap
                if stop > start + 0.02:
                    return stop
            else:
                stop = left + width + gap
                if stop < start - 0.02:
                    return stop
    return start + default_len if direction == 'right' else start - default_len


def add_dim_v(slide, x, label, top, bottom, *,
              top_edge='top', bottom_edge='top',
              ext_dir='right', ext_len=0.35, ext_gap=0.03,
              tick=0.10, text_side='auto', text_gap=0.08,
              box_w=0.90, box_h=0.30,
              font_size=10, bold=True, font_name=DEFAULT_FONT,
              color=None, line_w=0.75):
    """画一条竖直尺寸标注：竖线 + 两端刻度 + 尺寸界线 + 居中文字。

    Parameters
    ----------
    slide : pptx slide
    x : float
        标注线水平位置（英寸）。
    label : str
        标注文字，如 '320mm'。
    top, bottom : shape 或 float
        两端被标注的实体。**优先传 shape**（边界自动读取），
        也可传由实体派生出的英寸变量（如 CAM_TOP）。
    top_edge, bottom_edge : {'top', 'bottom', 'center'}
        取实体的哪条边。例：相机顶 `top_edge='top'`；光源底 `top_edge='bottom'`。
    ext_dir : {'right', 'left', 'both', None}
        尺寸界线方向（指向实体）；None 表示只画刻度不画界线。
    tick : float
        刻度横线半长（英寸），默认 0.10（全长 0.20，满足 C8 的 >0.12 判据）。
    text_side : {'auto', 'left', 'right'}
        文字在标注线左侧还是右侧；auto = 界线的反方向。

    Returns
    -------
    dict
        {'line': 竖线形状, 'text': 文本框, 'y_top': 顶端y, 'y_bot': 底端y}

    Raises
    ------
    ValueError
        端点顺序传反（top 不在 bottom 上方）时立即报错，避免画出"零高度/倒置"标注。
    """
    y_top = edge_y(top, top_edge)
    y_bot = edge_y(bottom, bottom_edge)
    if y_top >= y_bot - 1e-6:
        raise ValueError(
            f'ppt_diagram: 顶端 y={y_top:.2f}in 不在底端 y={y_bot:.2f}in 上方，'
            f'检查 top/bottom 是否传反、或 top_edge/bottom_edge 是否取错边')

    rgb = color if color is not None else DEFAULT_COLOR

    def _line(x1, y1, x2, y2, width):
        conn = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
        conn.line.color.rgb = rgb
        conn.line.width = Pt(width)
        return conn

    # 1) 主竖线
    vline = _line(x, y_top, x, y_bot, line_w)
    # 2) 两端刻度横线
    for y in (y_top, y_bot):
        _line(x - tick, y, x + tick, y, line_w)
    # 3) 尺寸界线：从刻度外端水平伸向实体边缘
    if ext_dir in ('right', 'left', 'both'):
        dirs = ['right', 'left'] if ext_dir == 'both' else [ext_dir]
        for y, ref in ((y_top, top), (y_bot, bottom)):
            for direction in dirs:
                start = x + tick if direction == 'right' else x - tick
                end = _ext_end(start, ref, direction, ext_len, ext_gap)
                _line(start, y, end, y, line_w * 0.7)

    # 4) 文字：纵向居中，放在界线反方向
    side = text_side
    if side == 'auto':
        side = 'right' if ext_dir == 'left' else 'left'
    mid_y = (y_top + y_bot) / 2.0
    if side == 'left':
        left = x - text_gap - box_w
        align = PP_ALIGN.RIGHT
    else:
        left = x + text_gap
        align = PP_ALIGN.LEFT

    tb = slide.shapes.add_textbox(Inches(left), Inches(mid_y - box_h / 2.0),
                                  Inches(box_w), Inches(box_h))
    tf = tb.text_frame
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    para = tf.paragraphs[0]
    para.alignment = align
    run = para.add_run()
    run.text = str(label)
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.name = font_name
    run.font.color.rgb = rgb

    return {'line': vline, 'text': tb, 'y_top': y_top, 'y_bot': y_bot}


def add_wd_dim(slide, x, label, optic, target, **kwargs):
    """工作距离（WD）标注：光学件前端面 → 检测面。

    工业视觉的 WD 定义是**镜头/光源最前端面到被检测表面**的距离，
    相机机身高度、镜头法兰到机身那段都不计入。2026-11-23 事故就是把
    `320mm` 从相机顶面起算，多算了整个机身——坐标贴对了实体，物理含义
    仍然是错的，客户一眼看出。

    本函数把语义写进签名：`optic` 一律取**底面**，`target` 一律取**顶面**，
    调用方不需要（也不允许）自己指定边。

    Parameters
    ----------
    optic : shape 或 float
        镜头、光源等光学件。传 shape 时取其 `bottom`；传数值时视为前端面 y。
    target : shape 或 float
        检测面（工件表面）。传 shape 时取其 `top`；传数值时视为检测面 y。
    **kwargs
        透传给 add_dim_v（color / text_side / tick / font_size 等）。

    Examples
    --------
    >>> add_wd_dim(s, 0.80, '320mm', optic=lens, target=work)
    >>> add_wd_dim(s, 1.30, '220mm', optic=light, target=work, text_side='right')
    """
    return add_dim_v(slide, x, label, optic, target,
                     top_edge='bottom', bottom_edge='top', **kwargs)


def self_check(slide):
    """用 check_ppt_quality 的 C8 规则自检该页，返回问题字符串列表（空 = 合格）。"""
    try:
        from check_ppt_quality import check_dimension_annotations
    except Exception as exc:  # 模块被单独拷走时可跳过
        return [f'[INFO] 无法加载 C8 自检（{exc}）']
    return check_dimension_annotations([slide])
