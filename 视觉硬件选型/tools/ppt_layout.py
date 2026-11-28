# -*- coding: utf-8 -*-
"""视觉方案 PPT 统一版式构件库（2D / 3D / 线扫方案共用）。

统一的是「怎么排」：页面骨架、字号、间距、配色、构件样式。
不统一的是「排什么」：技术内容由各 build_*.py 提供。

为什么要有这个库
----------------
2D 贴片方案与 3D 引导抓取方案是同一家公司递给同一批客户的文档。
若两份 PPT 的封面、目录、结论条、流程卡各写一套，客户会感觉出自两个团队；
后续做线扫、测量方案又要再抄一遍。因此把版式沉淀为构件，脚本只描述内容。

标准页序（12 页，2D / 3D 共用一份定义，见 STANDARD_PAGES）
------------------------------------------------------------
  1  封面         Deck.cover()
  2  目录         Deck.toc()
  3  项目需求     示意图 + bullet_rows（客户需求）+ callout
  4  系统方案     布局示意图 + bullet_rows（系统组成）+ callout
  5  工作流程     step_cards + callout（节拍分解）
  6  硬件选型     母版硬件页替换（2D）/ 参数表（3D）
  7  专项 A       2D 选型计算链 / 3D 点云成像
  8  专项 B       2D 视觉算法 / 3D 6D 位姿
  9  专项 C       2D 精度分析 / 3D 视野校核
  10 系统架构     arch_row（感知 / 处理 / 决策 / 执行）
  11 实施与验收   col_cards（三栏）+ 说明条
  12 谢谢         Deck.thanks()

用法
----
    from ppt_layout import Deck
    deck = Deck(TPL)
    s = deck.new_slide("项目需求")
    deck.section_label(s, 7.0, 1.00, "客户需求")
    deck.bullet_rows(s, 7.0, 1.45, 5.70,
                     [("产品外形", "300 × 300 mm 方形件"),
                      ("安装方式", "ETH 眼在手外")])
    deck.callout(s, 7.0, 6.20, 5.70, 0.70, "核心目标：……", kind="warn")
    deck.save(OUT)

排版约定（改版式只改这里，不要在 build 脚本里手写坐标）
------------------------------------------------------
  版心      左 0.62，右 12.72，宽 12.10
  内容顶    1.02（母版标题占 0.12–0.62）
  结论条    6.30–7.00（页脚 7.09 以上）
  标题      28pt 粗体（母版占位符）
  小标题    13pt 粗体 BLUE_D
  正文      10.5pt
  辅助说明  9.5–10pt GRAY
"""

import os
import subprocess
import sys
from lxml import etree
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.oxml.ns import qn

# ---------- 配色（与母版一致，勿在 build 脚本里另立色值） ----------
BLUE_D = RGBColor(0x1F, 0x4E, 0x79)   # 深蓝：标题、强调
BLUE = RGBColor(0x2E, 0x75, 0xB6)     # 主蓝：竖条、图形
BLUE_L = RGBColor(0xDC, 0xE6, 0xF1)   # 浅蓝：信息条底
BLUE_LL = RGBColor(0xEE, 0xF4, 0xFA)  # 极浅蓝：卡片底 / 表格隔行
RED = RGBColor(0xC0, 0x00, 0x00)      # 红：警示、结论
RED_L = RGBColor(0xFD, 0xEC, 0xEA)    # 浅红：警示条底
ORANGE = RGBColor(0xC5, 0x5A, 0x11)
GREEN = RGBColor(0x37, 0x7E, 0x22)
GRAY = RGBColor(0x59, 0x59, 0x59)
GRAY_L = RGBColor(0xD9, 0xD9, 0xD9)
BLACK = RGBColor(0x00, 0x00, 0x00)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "微软雅黑"

# ---------- 版心常量 ----------
MARGIN_L = 0.62
MARGIN_R = 12.72
CONTENT_W = MARGIN_R - MARGIN_L      # 12.10
TOP = 1.02                            # 内容起始 y
BOTTOM = 7.00                         # 内容底线（页脚 7.09）

# ---------- 标准章节骨架（2D / 3D / 线扫共用，唯一一份定义） ----------
# 页序固定；改页序只改这里，生成器与 SKILL.md 都引用它。
# 每页的标题 / 目录文案由各方案用 SECTION_TEXT 填（见 toc_items）。
STANDARD_PAGES = [
    "cover",          # 1 封面
    "toc",            # 2 目录
    "requirements",   # 3 项目需求
    "system",         # 4 系统方案
    "workflow",       # 5 工作流程
    "hardware",       # 6 硬件选型
    "special_a",      # 7 专项 A：2D 选型计算链 / 3D 点云成像
    "special_b",      # 8 专项 B：2D 视觉算法 / 3D 6D 位姿
    "special_c",      # 9 专项 C：2D 精度分析 / 3D 视野校核
    "architecture",   # 10 系统架构
    "delivery",       # 11 实施与验收
    "thanks",         # 12 谢谢
]

# 目录只列 6 个章节（专项页归入 04/05），编号与页序一一对应。
STANDARD_SECTIONS = [
    {"key": "requirements", "no": "01"},
    {"key": "system",       "no": "02"},
    {"key": "hardware",     "no": "03"},
    {"key": "special_b",    "no": "04"},
    {"key": "special_c",    "no": "05"},
    {"key": "delivery",     "no": "06"},
]


def toc_items(section_text):
    """按标准章节顺序生成目录项。

    section_text: {key: (目录名称, 一句说明)}，各方案自己填。
    """
    return [(sec["no"], *section_text[sec["key"]]) for sec in STANDARD_SECTIONS]


def page_title(section_text, key):
    """取某章节的页面标题（目录名称即页面标题）。"""
    return section_text[key][0]


class Deck:
    """一份 PPT = 一个 Deck；页面构件都是 Deck 方法，共享配色与版心。"""

    def __init__(self, template, layout_index=2):
        self.prs = Presentation(template)
        self.layout = self.prs.slide_layouts[layout_index]

    # ================= 底层：文字 / 形状 / 线 / 表 / 图 =================
    @staticmethod
    def set_run(r, size=None, bold=None, color=None, font=FONT, italic=None):
        if size is not None:
            r.font.size = Pt(size)
        if bold is not None:
            r.font.bold = bold
        if color is not None:
            r.font.color.rgb = color
        if font:
            r.font.name = font
            rPr = r._r.get_or_add_rPr()
            for tag in ("a:latin", "a:ea", "a:cs"):
                el = rPr.find(qn(tag))
                if el is None:
                    el = etree.SubElement(rPr, qn(tag))
                el.set("typeface", font)
        if italic is not None:
            r.font.italic = italic

    def text(self, slide, x, y, w, h, paras, align=PP_ALIGN.LEFT,
             anchor=MSO_ANCHOR.TOP, line_spacing=1.15, space_after=0,
             margins=(0, 0, 0, 0)):
        """paras: dict 列表（text/size/bold/color/runs）或 (text,size,bold,color) 元组。"""
        tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left, tf.margin_top, tf.margin_right, tf.margin_bottom = \
            [Inches(v) for v in margins]
        tf.vertical_anchor = anchor
        for i, p in enumerate(paras):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            para.alignment = align
            para.line_spacing = line_spacing
            if space_after:
                para.space_after = Pt(space_after)
            if isinstance(p, dict):
                text = p.get("text", "")
                size = p.get("size", 16)
                bold = p.get("bold", False)
                color = p.get("color", BLACK)
                runs = p.get("runs")
            else:
                text, size, bold, color = (list(p) + [None] * 4)[:4]
                size = 16 if size is None else size
                bold = False if bold is None else bold
                color = BLACK if color is None else color
                runs = None
            if runs:
                for rt, rs, rb, rc in runs:
                    r = para.add_run()
                    r.text = rt
                    self.set_run(r, rs, rb, rc)
            else:
                r = para.add_run()
                r.text = text
                self.set_run(r, size, bold, color)
        return tb

    def box(self, slide, x, y, w, h, fill=None, line=None, line_w=1.0,
            shape=MSO_SHAPE.RECTANGLE, radius=None, shadow=False):
        sp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
        if fill is None:
            sp.fill.background()
        else:
            sp.fill.solid()
            sp.fill.fore_color.rgb = fill
        if line is None:
            sp.line.fill.background()
        else:
            sp.line.color.rgb = line
            sp.line.width = Pt(line_w)
        if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
            sp.adjustments[0] = radius
        if not shadow:
            spPr = sp._element.spPr
            if spPr.find(qn('a:effectLst')) is None:
                etree.SubElement(spPr, qn('a:effectLst'))
        return sp

    def line(self, slide, x1, y1, x2, y2, color=BLACK, width=1.25,
             dash=None, arrow=False):
        ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                        Inches(x1), Inches(y1), Inches(x2), Inches(y2))
        ln.line.color.rgb = color
        ln.line.width = Pt(width)
        if dash:
            ln.line.dash_style = dash
        if arrow:
            lnel = ln.line._get_or_add_ln()
            tail = etree.SubElement(lnel, qn('a:tailEnd'))
            tail.set('type', 'triangle')
            tail.set('w', 'med')
            tail.set('len', 'med')
        return ln

    def picture(self, slide, path, x, y, w, h):
        return slide.shapes.add_picture(path, Inches(x), Inches(y),
                                        Inches(w), Inches(h))

    def table(self, slide, x, y, w, col_w, rows, row_h=0.40, font=11,
              head_fill=BLUE_D, head_color=WHITE, first_col_bold=False,
              align=None):
        """rows[0] 为表头。col_w 各列宽（英寸），总和应等于 w。

        注意：row_h 是最小行高，LibreOffice 渲染中文会略压缩，
        目检留余量时按实际渲染估算（约 0.85×row_h）。
        """
        n_row, n_col = len(rows), len(rows[0])
        shape = slide.shapes.add_table(n_row, n_col, Inches(x), Inches(y),
                                       Inches(w), Inches(row_h * n_row))
        tbl = shape.table
        for ci, cw in enumerate(col_w):
            tbl.columns[ci].width = Inches(cw)
        for ri, row in enumerate(rows):
            tbl.rows[ri].height = Inches(row_h)
            for ci, text in enumerate(row):
                cell = tbl.cell(ri, ci)
                cell.text = ""
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell.margin_left = Inches(0.07)
                cell.margin_right = Inches(0.05)
                cell.margin_top = Inches(0.02)
                cell.margin_bottom = Inches(0.02)
                cell.fill.solid()
                if ri == 0:
                    cell.fill.fore_color.rgb = head_fill
                else:
                    cell.fill.fore_color.rgb = BLUE_LL if ri % 2 == 0 else WHITE
                p = cell.text_frame.paragraphs[0]
                r = p.add_run()
                r.text = str(text)
                bold = (ri == 0) or (first_col_bold and ci == 0)
                self.set_run(r, font, bold, head_color if ri == 0 else BLACK)
                p.alignment = (align[ci] if align else PP_ALIGN.LEFT)
        return tbl

    # ================= 页面 =================
    def new_slide(self, title=None):
        s = self.prs.slides.add_slide(self.layout)
        t = s.shapes.title
        if title is None:
            if t is not None:
                t._element.getparent().remove(t._element)
        else:
            # 必须显式给全 left/top/width/height：slide 层继承 layout 时
            # shape.height 会读到 0，只改 width 会写出 cy="0" 的 xfrm，
            # 渲染时标题被裁切（已踩过）。
            t.left = Inches(0.84)
            t.top = Inches(0.12)
            t.width = Inches(11.60)
            t.height = Inches(0.50)
            t.text = title
            for p in t.text_frame.paragraphs:
                for r in p.runs:
                    self.set_run(r, 28, True, RGBColor(0x1A, 0x1A, 0x1A))
        return s

    @staticmethod
    def kill_slide(prs, index):
        lst = prs.slides._sldIdLst
        sldId = list(lst)[index]
        rId = sldId.get(qn('r:id'))
        prs.part.drop_rel(rId)
        lst.remove(sldId)

    # ================= 高层构件（统一版式的核心） =================
    def section_label(self, s, x, y, text, w=6.0, size=13):
        """栏目标题：13pt 深蓝粗体。返回下一行 y。"""
        self.text(s, x, y, w, 0.32, [{"text": text, "size": size, "bold": True, "color": BLUE_D}])
        return y + 0.38

    def bullet_rows(self, s, x, y, w, rows, gap=0.72, label_w=1.55,
                    size=10.5, bar=True):
        """条目列表：蓝色竖条 + 加粗标签 + 说明。rows = [(label, desc), ...]。"""
        for i, (label, desc) in enumerate(rows):
            yy = y + i * gap
            if bar:
                self.box(s, x, yy + 0.05, 0.09, 0.30, fill=BLUE)
            tx = x + 0.24 if bar else x
            self.text(s, tx, yy, label_w, 0.30,
                      [{"text": label, "size": size, "bold": True, "color": BLUE_D}])
            self.text(s, tx + label_w, yy - 0.02, w - label_w - (tx - x), 0.60,
                      [{"text": desc, "size": size, "color": BLACK}], line_spacing=1.08)
        return y + len(rows) * gap

    def callout(self, s, x, y, w, h, text, kind="info", size=10.5, bold=True):
        """结论条。kind: info=浅蓝底深蓝字 / warn=浅红底红字 / plain=无底色。"""
        if kind == "info":
            self.box(s, x, y, w, h, fill=BLUE_L, line=None)
            color = BLUE_D
        elif kind == "warn":
            self.box(s, x, y, w, h, fill=RED_L, line=None)
            color = RED
        else:
            color = BLACK
        self.text(s, x + 0.16, y + 0.06, w - 0.32, h - 0.12,
                  [{"text": text, "size": size, "bold": bold, "color": color}],
                  line_spacing=1.12, anchor=MSO_ANCHOR.MIDDLE)

    def step_cards(self, s, y, steps, card_h=2.45, x0=MARGIN_L, gap=0.20,
                   total_w=CONTENT_W, desc_size=9.5):
        """横向流程卡：[(no, title, desc, time), ...]，自动均分宽度并画箭头。"""
        n = len(steps)
        cw = (total_w - gap * (n - 1)) / n
        for i, (no, name, desc, t) in enumerate(steps):
            x = x0 + i * (cw + gap)
            self.box(s, x, y, cw, card_h, fill=BLUE_LL, line=BLUE_L, line_w=1.0,
                     shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
            self.box(s, x + 0.14, y + 0.14, 0.46, 0.46, fill=BLUE, line=None,
                     shape=MSO_SHAPE.OVAL)
            self.text(s, x + 0.14, y + 0.21, 0.46, 0.28,
                      [{"text": no, "size": 11, "bold": True, "color": WHITE}],
                      align=PP_ALIGN.CENTER)
            self.text(s, x + 0.66, y + 0.20, cw - 0.72, 0.35,
                      [{"text": name, "size": 12, "bold": True, "color": BLUE_D}])
            self.text(s, x + 0.14, y + 0.92, cw - 0.28, 0.65,
                      [{"text": desc, "size": desc_size, "color": BLACK}],
                      line_spacing=1.1)
            self.box(s, x + 0.14, y + card_h - 0.60, cw - 0.28, 0.42,
                     fill=WHITE, line=None)
            self.text(s, x + 0.14, y + card_h - 0.54, cw - 0.28, 0.30,
                      [{"text": t, "size": 10, "bold": True, "color": RED}],
                      align=PP_ALIGN.CENTER)
            if i < n - 1:
                self.line(s, x + cw + 0.02, y + card_h / 2 - 0.25,
                          x + cw + gap - 0.02, y + card_h / 2 - 0.25,
                          color=BLUE, width=1.2, arrow=True)
        return y + card_h

    def col_cards(self, s, y, cols, h=4.55, gap=0.22, head_h=0.55,
                  item_size=10.5, total_w=CONTENT_W, x0=MARGIN_L,
                  line_spacing=1.5, space_after=0):
        """三栏卡片：[(栏头, [条目...]), ...]，蓝底白字栏头 + 浅底正文。

        条目铺满卡片优先用 space_after（pt），line_spacing 会把首行也推开。
        """
        n = len(cols)
        cw = (total_w - gap * (n - 1)) / n
        for i, (head, items) in enumerate(cols):
            x = x0 + i * (cw + gap)
            self.box(s, x, y, cw, h, fill=BLUE_LL, line=None,
                     shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.04)
            self.box(s, x, y, cw, head_h, fill=BLUE, line=None,
                     shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
            self.text(s, x, y + 0.12, cw, 0.32,
                      [{"text": head, "size": 12.5, "bold": True, "color": WHITE}],
                      align=PP_ALIGN.CENTER)
            paras = [{"text": "· " + it, "size": item_size, "color": BLACK} for it in items]
            self.text(s, x + 0.22, y + head_h + 0.22, cw - 0.40, h - head_h - 0.30,
                      paras, line_spacing=line_spacing, space_after=space_after)
        return y + h

    def arch_row(self, s, y, layers, h=1.75, gap=0.22, total_w=CONTENT_W,
                 x0=MARGIN_L):
        """分层架构：[(层名, 模块名, 说明), ...]，层名在上、圆角框在下、箭头连接。"""
        n = len(layers)
        cw = (total_w - gap * (n - 1)) / n
        for i, (layer, name, desc) in enumerate(layers):
            x = x0 + i * (cw + gap)
            self.text(s, x, y, cw, 0.32,
                      [{"text": layer, "size": 12, "bold": True, "color": BLUE}],
                      align=PP_ALIGN.CENTER)
            self.box(s, x, y + 0.36, cw, h, fill=WHITE, line=BLUE, line_w=2.0,
                     shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
            self.text(s, x, y + 0.50, cw, 0.32,
                      [{"text": name, "size": 13, "bold": True, "color": BLUE_D}],
                      align=PP_ALIGN.CENTER)
            self.text(s, x + 0.20, y + 0.80, cw - 0.40, h - 0.90,
                      [{"text": desc, "size": 10, "color": BLACK}],
                      align=PP_ALIGN.CENTER, line_spacing=1.15,
                      anchor=MSO_ANCHOR.MIDDLE)
            if i < n - 1:
                self.line(s, x + cw + 0.02, y + 0.36 + h / 2,
                          x + cw + gap - 0.02, y + 0.36 + h / 2,
                          color=BLUE, width=2.0, arrow=True)
        return y + 0.36 + h

    def toc(self, s, items, y0=1.55, row_gap=1.62, col_gap=5.85,
            per_col=3, x0=1.05):
        """目录：[(编号, 名称, 说明), ...]，两列排布。"""
        for i, (no, name, desc) in enumerate(items):
            col, row = i // per_col, i % per_col
            x = x0 + col * col_gap
            y = y0 + row * row_gap
            self.text(s, x, y, 0.85, 0.60,
                      [{"text": no, "size": 26, "bold": True, "color": BLUE_L}])
            self.text(s, x + 0.85, y - 0.02, 4.40, 0.40,
                      [{"text": name, "size": 17, "bold": True, "color": BLUE_D}])
            self.text(s, x + 0.85, y + 0.40, 4.50, 0.45,
                      [{"text": desc, "size": 11.5, "color": GRAY}])

    def cover(self, s, title, subtitle, metrics, company, date_txt):
        """封面：标题 + 一行副标题 + 红色短线 + 一行指标 + 底部公司/日期。"""
        self.text(s, 0.90, 1.80, 11.53, 0.95,
                  [{"text": title, "size": 40, "bold": True, "color": BLUE_D}],
                  align=PP_ALIGN.CENTER)
        self.text(s, 0.90, 2.95, 11.53, 0.50,
                  [{"text": subtitle, "size": 18, "color": GRAY}],
                  align=PP_ALIGN.CENTER)
        self.box(s, 5.57, 3.62, 2.20, 0.04, fill=RED)
        self.text(s, 0.90, 4.05, 11.53, 0.40,
                  [{"text": metrics, "size": 16, "color": GRAY}],
                  align=PP_ALIGN.CENTER)
        self.text(s, 0.90, 6.45, 11.53, 0.35,
                  [{"text": f"{company}　　{date_txt}", "size": 13, "color": GRAY}],
                  align=PP_ALIGN.CENTER)

    def thanks(self, s, company):
        """谢谢页：谢 谢！+ 红色短线 + 公司名。"""
        self.text(s, 0.90, 2.45, 11.53, 1.00,
                  [{"text": "谢 谢！", "size": 44, "bold": True, "color": BLUE_D}],
                  align=PP_ALIGN.CENTER)
        self.box(s, 5.57, 3.70, 2.20, 0.04, fill=RED)
        self.text(s, 0.90, 4.10, 11.53, 0.45,
                  [{"text": company, "size": 18, "color": GRAY}],
                  align=PP_ALIGN.CENTER)

    # ================= 收尾 =================
    def finalize(self, footer_text, first_page_no=1, footer_from=2):
        """补页码与页脚：页码从 first_page_no 起；页脚从 footer_from 起，末页不加。"""
        n = len(self.prs.slides)
        for i, sl in enumerate(self.prs.slides, 1):
            for sh in list(sl.shapes):
                if sh.is_placeholder and sh.placeholder_format.type == 13:
                    sh._element.getparent().remove(sh._element)
            if i >= first_page_no:
                self.text(sl, 10.03, 7.10, 3.0, 0.32,
                          [{"text": str(i), "size": 11, "color": GRAY}],
                          align=PP_ALIGN.RIGHT)
            has_footer = any(sh.is_placeholder and sh.placeholder_format.type == 15
                             for sh in sl.shapes)
            if not has_footer and footer_from <= i < n:
                self.text(sl, 4.41, 7.09, 4.5, 0.35,
                          [{"text": footer_text, "size": 10, "color": GRAY}],
                          align=PP_ALIGN.CENTER)

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.prs.save(path)
        print(f"[输出] {path}  共 {len(self.prs.slides)} 页")


def fmt(v, nd=0):
    return "-" if v is None else f"{v:.{nd}f}"


def discover_template(search_dir, prefer=("视觉检测方案", "模板", "template"),
                      parents=1):
    """在工作目录发现母版 pptx（重建式生成器共用，如 two_d_ppt / three_d_ppt）。

    优先文件名含 prefer 关键词的（取最新），否则取最新的 pptx。
    只扫顶层不递归；本目录没有时向上找 parents 层（项目 config 常在子目录，
    母版放在工作区根目录）。生成的 PPT 在项目子目录里，不会被当成母版。
    """
    if not search_dir:
        return None
    dirs = [os.path.abspath(search_dir)]
    p = dirs[0]
    for _ in range(parents):
        p = os.path.dirname(p)
        if not p or p == os.path.dirname(p) or p in dirs:
            break
        dirs.append(p)
    for d in dirs:
        hit = _discover_in_dir(d, prefer)
        if hit:
            return hit
    return None


def _discover_in_dir(search_dir, prefer):
    if not os.path.isdir(search_dir):
        return None
    cands = [os.path.join(search_dir, f) for f in os.listdir(search_dir)
             if f.lower().endswith(".pptx") and not f.startswith("~$")]
    if not cands:
        return None
    for kw in prefer:
        hit = [p for p in cands if kw.lower() in os.path.basename(p).lower()]
        if hit:
            hit.sort(key=os.path.getmtime, reverse=True)
            return hit[0]
    cands.sort(key=os.path.getmtime, reverse=True)
    return cands[0]


# ==================== 收尾：机检 + 预览（2D / 3D 共用） ====================
def run_quality_check(pptx_path, selection=None):
    """调用 check_ppt_quality.py 做规则自查；返回是否通过（FAIL=0）。

    selection 必须显式传入：2D 的 selection 常与 PPT 不同目录（output_dir 与
    <project_name> 分叉），不传会漏掉型号白名单，把正确的追光者光源误判成
    "FL-R- 旧型号残留"（2026-11-28 实测）。
    """
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "check_ppt_quality.py")
    cmd = [sys.executable, script, "--pptx", pptx_path]
    if selection and os.path.exists(selection):
        cmd += ["--selection", selection]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    print(r.stdout.strip())
    if r.stderr.strip():
        print(r.stderr.strip())
    return r.returncode == 0


def export_preview(pptx_path, outdir, width=1600):
    """调用 export_ppt_images.py 导出逐页 PNG + 总览 + index.html。

    先清空旧 png：页数变少时残留文件会让总览图张数对不上。
    """
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "export_ppt_images.py")
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.lower().endswith(".png"):
            try:
                os.remove(os.path.join(outdir, f))
            except OSError:
                pass
    r = subprocess.run([sys.executable, script, pptx_path,
                        "--outdir", outdir, "--width", str(width)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    print(r.stdout.strip() or r.stderr.strip())
    return r.returncode == 0
