# -*- coding: utf-8 -*-
"""L1 PPT 质检规则契约：check_ppt_quality 的判定不能误杀/漏放。

背景：追光者真实型号本身以 ``FL-R-`` 开头，与"模板旧型号残留"触发词
重叠——2026-11-20 实测正确交付被判 FAIL。本文件锁死"白名单放行 +
旧型号/假型号拦截"的边界。
运行：python run_all.py --layer ppt
"""
import json
import os
import subprocess
import sys
import unittest

import vt_common

CHECK = os.path.join(vt_common.TOOLS_DIR, 'check_ppt_quality.py')
CUR_LIGHT = 'FL-R-10045-W'


def make_ppt(path, text):
    from pptx import Presentation
    from pptx.util import Mm
    prs = Presentation()
    prs.slide_width, prs.slide_height = Mm(254), Mm(142)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_textbox(Mm(10), Mm(5), Mm(200), Mm(12)).text_frame.text = \
        '硬件选型'
    # 硬件标注框：新判定要求 ≥2 个，否则不视为硬件展示页
    slide.shapes.add_textbox(Mm(10), Mm(20), Mm(40), Mm(10)).text_frame.text = '相机'
    slide.shapes.add_textbox(Mm(10), Mm(34), Mm(40), Mm(10)).text_frame.text = '环形光'
    slide.shapes.add_textbox(Mm(10), Mm(48), Mm(200), Mm(20)).text_frame.text = text
    prs.save(path)


def make_selection(path, light_model):
    data = {'hardware_selection': {
        'camera': {'model': 'MV-CS050-10GM'},
        'lens': {'model': 'WWK05-110-111V3'},
        'light_source': {'model': light_model, 'type': 'LED环形光光源'},
    }}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def run_check(tmp):
    return subprocess.run(
        [sys.executable, CHECK, '--pptx', os.path.join(tmp, 't.pptx')],
        capture_output=True, text=True, encoding='utf-8', errors='replace')


class TestStaleModelWhitelist(unittest.TestCase):
    """C1 旧型号残留的边界"""

    def _case(self, light_text, selected_model, expect_fail):
        tmp = vt_common.temp_dir('vt_stale_')
        try:
            make_ppt(os.path.join(tmp, 't.pptx'), light_text)
            make_selection(os.path.join(tmp, 'selection_result.json'),
                           selected_model)
            r = run_check(tmp)
            out = (r.stdout or '') + (r.stderr or '')
            if expect_fail:
                self.assertNotEqual(r.returncode, 0,
                                    f'应拦截却通过: {light_text}\n{out[-600:]}')
                self.assertIn('残留', out)
            else:
                self.assertEqual(r.returncode, 0,
                                 f'应放行却FAIL: {light_text}\n{out[-600:]}')
        finally:
            vt_common.rmtree(tmp)

    def test_current_light_model_allowed(self):
        """当前选中的追光者型号必须放行（FL-R- 与残留前缀重叠）"""
        self._case(f'追光者 {CUR_LIGHT}', CUR_LIGHT, expect_fail=False)

    def test_old_light_model_blocked(self):
        """旧追光者型号（非本次选中）仍必须拦截"""
        self._case('环光： FL-R-7090W', CUR_LIGHT, expect_fail=True)

    def test_fake_opt_model_blocked(self):
        """历史假型号 OPT RL-150-120-W 必须拦截"""
        self._case('OPT RL-150-120-W', CUR_LIGHT, expect_fail=True)

    def test_needs_expansion_leftover_blocked(self):
        """待选型时模板里的旧光源型号必须拦截（不能假装已替换）"""
        self._case('环光： FL-R-10045-W', '', expect_fail=True)

    def test_correct_camera_model_allowed(self):
        """相机型号同样走白名单，不得因为出现在模板里被误判"""
        self._case('相机： MV-CS050-10GM', CUR_LIGHT, expect_fail=False)


class TestCheckContract(unittest.TestCase):
    """退出码语义：0=FAIL0可交付，1=有FAIL，2=无法自查"""

    def test_no_hardware_slide_exits_2(self):
        tmp = vt_common.temp_dir('vt_nohw_')
        try:
            from pptx import Presentation
            from pptx.util import Mm
            prs = Presentation()
            prs.slide_width, prs.slide_height = Mm(254), Mm(142)
            s = prs.slides.add_slide(prs.slide_layouts[6])
            s.shapes.add_textbox(Mm(10), Mm(10), Mm(200), Mm(20)).text_frame.text = \
                '这是一页普通内容页，没有硬件选型标题'
            prs.save(os.path.join(tmp, 't.pptx'))
            r = run_check(tmp)
            self.assertEqual(r.returncode, 2,
                             (r.stdout or '')[-600:])
            self.assertIn('未识别到硬件选型页', (r.stdout or ''))
        finally:
            vt_common.rmtree(tmp)


class TestDimensionAnnotation(unittest.TestCase):
    """C8 尺寸标注对齐（2026-11-23 事故：标注端点与实体脱节）。

    真实事故：320mm 竖线写死 1.72→4.67，而相机顶 1.40、工件面 4.55，
    上端悬空、下端扎进工件；220mm 只有竖线没有刻度横线。
    判定必须抓得住，同时不能误伤硬件页的普通数据标注（如 WD 320mm）。
    """

    def _build(self, tmp, top_mm, bottom_mm, with_ticks=True, text_has_line=True):
        from pptx import Presentation
        from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
        from pptx.util import Mm
        prs = Presentation()
        prs.slide_width, prs.slide_height = Mm(254), Mm(142)
        s = prs.slides.add_slide(prs.slide_layouts[6])
        # 让 check_ppt_quality 识别为硬件页（否则 exit 2 不进入检查）
        s.shapes.add_textbox(Mm(10), Mm(5), Mm(200), Mm(12)).text_frame.text = '硬件选型'
        s.shapes.add_textbox(Mm(10), Mm(20), Mm(40), Mm(10)).text_frame.text = '相机'
        s.shapes.add_textbox(Mm(10), Mm(32), Mm(40), Mm(10)).text_frame.text = '环形光'
        # 实体：上块 top=40mm/bottom=60mm，下块 top=100mm/bottom=110mm
        s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Mm(80), Mm(40), Mm(40), Mm(20))
        s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Mm(80), Mm(100), Mm(40), Mm(10))
        # 标注竖线：正确版应 40→100，错误版故意偏 5mm
        if text_has_line:
            s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                   Mm(50), Mm(top_mm), Mm(50), Mm(bottom_mm))
            if with_ticks:
                s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                       Mm(45), Mm(top_mm), Mm(55), Mm(top_mm))
                s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                       Mm(45), Mm(bottom_mm), Mm(55), Mm(bottom_mm))
        s.shapes.add_textbox(Mm(20), Mm((top_mm + bottom_mm) / 2 - 4),
                             Mm(28), Mm(8)).text_frame.text = '320mm'
        prs.save(os.path.join(tmp, 't.pptx'))
        return run_check(tmp)

    def test_misaligned_ends_warns(self):
        """端点悬空 5mm（>0.08in 容差）→ WARN，且指出具体标注"""
        tmp = vt_common.temp_dir('vt_dim1_')
        try:
            r = self._build(tmp, 45, 95)
            out = (r.stdout or '')
            self.assertIn('[WARN]', out)
            self.assertIn('320mm', out)
            self.assertIn('未对齐实体边界', out)
        finally:
            vt_common.rmtree(tmp)

    def test_missing_tick_warns(self):
        """有竖线但两端无刻度横线 → WARN"""
        tmp = vt_common.temp_dir('vt_dim2_')
        try:
            r = self._build(tmp, 40, 100, with_ticks=False)
            out = (r.stdout or '')
            self.assertIn('320mm', out)
            self.assertIn('缺刻度横线', out)
        finally:
            vt_common.rmtree(tmp)

    def test_aligned_passes(self):
        """端点对齐实体上/下边界且有刻度 → 不得出现该标注的 WARN"""
        tmp = vt_common.temp_dir('vt_dim3_')
        try:
            r = self._build(tmp, 40, 100)
            self.assertNotIn('320mm', (r.stdout or ''))
        finally:
            vt_common.rmtree(tmp)

    def test_plain_data_label_not_flagged(self):
        """无竖线的纯数字标注（硬件页 WD 320mm 之类）不触发 C8"""
        tmp = vt_common.temp_dir('vt_dim4_')
        try:
            r = self._build(tmp, 40, 100, text_has_line=False)
            self.assertNotIn('320mm', (r.stdout or ''))
        finally:
            vt_common.rmtree(tmp)


class TestPptDiagramModule(unittest.TestCase):
    """skill 内置画法模块 ppt_diagram 的契约。

    2026-11-23 事故的真正教训：只改项目里的 build_ppt.py 没用——换工作区
    会重新生成脚本，手写坐标的错误会复现。正确画法必须由 skill 提供模块，
    项目只 import。这里锁死"模块可用 + 边界自动读取 + 单位正确"。
    """

    def _slide(self):
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches, Mm
        prs = Presentation()
        prs.slide_width, prs.slide_height = Mm(254), Mm(142)
        s = prs.slides.add_slide(prs.slide_layouts[6])
        cam = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(2.25), Inches(1.40),
                                 Inches(1.05), Inches(0.62))
        light = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.85), Inches(2.62),
                                   Inches(1.85), Inches(0.28))
        work = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.55), Inches(4.55),
                                  Inches(2.45), Inches(0.28))
        return prs, s, cam, work, light

    def test_module_exists_in_skill(self):
        """模块必须在 skill tools 下（换工作区也能 import）"""
        self.assertTrue(os.path.isfile(os.path.join(vt_common.TOOLS_DIR,
                                                    'ppt_diagram.py')))

    def test_shape_binding_reads_edges(self):
        """传实体 shape → 边界自动读取，不依赖调用方写坐标"""
        from ppt_diagram import add_dim_v
        prs, s, cam, work, light = self._slide()
        r = add_dim_v(s, 0.80, '320mm', cam, work)
        self.assertAlmostEqual(r['y_top'], 1.40, places=3)
        self.assertAlmostEqual(r['y_bot'], 4.55, places=3)

    def test_light_bottom_edge(self):
        """top_edge='bottom' 取光源底面（220mm 的正确起点）"""
        from ppt_diagram import add_dim_v
        prs, s, cam, work, light = self._slide()
        r = add_dim_v(s, 1.30, '220mm', light, work, top_edge='bottom')
        self.assertAlmostEqual(r['y_top'], 2.90, places=3)

    def test_length_argument_treated_as_inches(self):
        """pptx Length 是 int 子类，必须按 .inches 解析而不是当数值"""
        from pptx.util import Inches
        from ppt_diagram import edge_y
        self.assertAlmostEqual(edge_y(Inches(1.4)), 1.4, places=3)
        self.assertAlmostEqual(edge_y(Inches(2.9)), 2.9, places=3)

    def test_generated_annotation_passes_c8(self):
        """模块画出来的标注必须直接满足 C8（否则等于把错误固化了）"""
        from ppt_diagram import add_dim_v, self_check
        prs, s, cam, work, light = self._slide()
        add_dim_v(s, 0.80, '320mm', cam, work)
        add_dim_v(s, 1.30, '220mm', light, work,
                  top_edge='bottom', text_side='right')
        self.assertEqual(self_check(s), [])

    def test_reversed_endpoints_raise(self):
        """端点传反（top 在下）必须立即报错，画不出倒置标注"""
        from ppt_diagram import add_dim_v
        prs, s, cam, work, light = self._slide()
        with self.assertRaises(ValueError):
            add_dim_v(s, 0.80, '320mm', work, cam)

    def test_none_endpoint_raise(self):
        """实体变量漏赋值（None）必须立即报错，而不是画出 y=0 的线"""
        from ppt_diagram import add_dim_v
        prs, s, cam, work, light = self._slide()
        with self.assertRaises(ValueError):
            add_dim_v(s, 0.80, '320mm', None, work)

    # ---------- 工作距离语义（2026-11-23 第二次客户退回） ----------

    def _slide_wd(self):
        """带镜头实体的页面：相机 / 镜头 / 光源 / 工件四件齐备"""
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches, Mm
        prs = Presentation()
        prs.slide_width, prs.slide_height = Mm(254), Mm(142)
        s = prs.slides.add_slide(prs.slide_layouts[6])
        cam = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(2.25), Inches(1.40),
                                 Inches(1.05), Inches(0.62))
        lens = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(2.55), Inches(2.02),
                                  Inches(0.45), Inches(0.55))
        light = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.85), Inches(2.74),
                                   Inches(1.85), Inches(0.28))
        work = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.55), Inches(4.55),
                                  Inches(2.45), Inches(0.28))
        return prs, s, cam, lens, light, work

    def test_wd_dim_starts_at_lens_bottom(self):
        """工作距离必须从镜头前端面起算，禁止相机顶面（多算机身高度）"""
        from ppt_diagram import add_wd_dim
        prs, s, cam, lens, light, work = self._slide_wd()
        r = add_wd_dim(s, 0.80, '320mm', lens, work)
        self.assertAlmostEqual(r['y_top'], 2.57, places=3)   # 镜头底 = 2.02 + 0.55
        self.assertNotAlmostEqual(r['y_top'], cam.top.inches, places=2)

    def test_wd_dim_light_bottom(self):
        """光源工作距离从发光面（底面）起算"""
        from ppt_diagram import add_wd_dim
        prs, s, cam, lens, light, work = self._slide_wd()
        r = add_wd_dim(s, 1.30, '220mm', light, work, text_side='right')
        self.assertAlmostEqual(r['y_top'], 3.02, places=3)   # 光源底 = 2.74 + 0.28

    def test_wd_dim_generated_passes_c8(self):
        """WD 标注生成后必须直接满足 C8"""
        from ppt_diagram import add_wd_dim, self_check
        prs, s, cam, lens, light, work = self._slide_wd()
        add_wd_dim(s, 0.80, '320mm', lens, work)
        add_wd_dim(s, 1.30, '220mm', light, work, text_side='right')
        self.assertEqual(self_check(s), [])

    def test_wd_dim_rejects_edge_override(self):
        """不允许通过 top_edge 把 WD 起点改回相机顶（重复关键字直接 TypeError）"""
        from ppt_diagram import add_wd_dim
        prs, s, cam, lens, light, work = self._slide_wd()
        with self.assertRaises(TypeError):
            add_wd_dim(s, 0.80, '320mm', lens, work, top_edge='top')


class TestHardwareSlideDetection(unittest.TestCase):
    """硬件页识别边界（2026-11-20 事故：目录页被误当硬件页）"""

    def _build(self, tmp, *, has_toc, has_calc):
        from pptx import Presentation
        from pptx.util import Mm
        prs = Presentation()
        prs.slide_width, prs.slide_height = Mm(254), Mm(142)
        if has_toc:
            s = prs.slides.add_slide(prs.slide_layouts[6])
            s.shapes.add_textbox(Mm(10), Mm(5), Mm(80), Mm(12)).text_frame.text = '目录'
            s.shapes.add_textbox(Mm(10), Mm(30), Mm(120), Mm(12)).text_frame.text = \
                '三：硬件选型'
        if has_calc:
            s = prs.slides.add_slide(prs.slide_layouts[6])
            s.shapes.add_textbox(Mm(10), Mm(5), Mm(80), Mm(12)).text_frame.text = \
                '硬件选型'
            s.shapes.add_textbox(Mm(10), Mm(20), Mm(100), Mm(12)).text_frame.text = \
                '选型计算链'
            # 参数表格（相机/镜头/光源是单元格，不是硬件标注框）
            tbl = s.shapes.add_table(3, 2, Mm(10), Mm(40), Mm(120), Mm(30)).table
            for ri, (k, v) in enumerate((('相机', 'MV-CS050-10GM'),
                                         ('镜头', 'MVL-MF7538M-MV'),
                                         ('光源', f'追光者 {CUR_LIGHT}'))):
                tbl.cell(ri, 0).text = k
                tbl.cell(ri, 1).text = v
            # 真实计算页必有参数文字（分辨率/像素精度），据此识别为硬件页
            s.shapes.add_textbox(Mm(10), Mm(80), Mm(160), Mm(12)).text_frame.text = \
                '分辨率 2448 × 2048，像素精度 0.0104 mm/pixel'
        prs.save(os.path.join(tmp, 't.pptx'))

    def _run(self, **flags):
        tmp = vt_common.temp_dir('vt_hwdetect_')
        try:
            self._build(tmp, **flags)
            make_selection(os.path.join(tmp, 'selection_result.json'), CUR_LIGHT)
            return run_check(tmp), tmp
        finally:
            vt_common.rmtree(tmp)

    def test_toc_page_not_hardware(self):
        """目录页里的"三：硬件选型"只是一行目录，不是硬件页"""
        r, _ = self._run(has_toc=True, has_calc=False)
        self.assertEqual(r.returncode, 2, (r.stdout or '')[-600:])
        self.assertIn('未识别到硬件选型页', (r.stdout or ''))

    def test_calc_page_is_checked_but_no_showcase_warns(self):
        """计算页是硬件页（查旧型号/溢出），但不该报缺光源标注或缺产品图"""
        r, _ = self._run(has_toc=False, has_calc=True)
        out = r.stdout or ''
        self.assertEqual(r.returncode, 0, out[-600:])
        self.assertNotIn('未识别到光源类型标注', out)
        self.assertNotIn('未发现产品图片', out)

    def test_toc_plus_calc(self):
        r, _ = self._run(has_toc=True, has_calc=True)
        out = r.stdout or ''
        self.assertEqual(r.returncode, 0, out[-600:])
        self.assertNotIn('未识别到光源类型标注', out)


class TestOverflowMultiline(unittest.TestCase):
    """C4 多行正文豁免（2026-11-27：3D 方案说明段落整页误报 FAIL）。

    规则：长正文（>20 字）且框高足够容纳估算行数 → 正常多行排版，不报；
    短标注（≤20 字）或框高不足 → 仍按原规则抓断行/溢出。
    """

    def _slide(self, text, w_in, h_in, fs=10.5):
        from pptx import Presentation
        from pptx.util import Inches, Pt
        prs = Presentation()
        prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
        s = prs.slides.add_slide(prs.slide_layouts[6])
        tb = s.shapes.add_textbox(Inches(0.5), Inches(0.5),
                                  Inches(w_in), Inches(h_in))
        tb.text_frame.word_wrap = True
        p = tb.text_frame.paragraphs[0]
        r = p.add_run()
        r.text = text
        r.font.size = Pt(fs)
        return prs, s

    def test_long_body_with_tall_box_not_flagged(self):
        """整段说明文字 + 框高足够 → 不得报断行"""
        from check_ppt_quality import check_overflow
        text = ('RSS 为统计合成，不是最坏情况相加；验收按 3σ 或双方约定口径执行。'
                '现场某一项超预算时，优先压缩该项而不是换相机。')
        prs, s = self._slide(text, 5.15, 1.15)
        self.assertEqual(check_overflow([(1, s)]), [])

    def test_long_body_with_short_box_flagged(self):
        """框高只够一行却塞长正文 → 仍须报"""
        from check_ppt_quality import check_overflow
        text = ('这是一段很长的说明文字，用来验证框高不足时仍然会报断行风险，'
                '不能被豁免逻辑放过。')
        prs, s = self._slide(text, 1.2, 0.18)
        self.assertTrue(check_overflow([(1, s)]))

    def test_short_label_still_flagged(self):
        """短标注（≤20 字）不受多行豁免影响"""
        from check_ppt_quality import check_overflow
        prs, s = self._slide('LED环形光光源', 0.9, 0.4, fs=11)
        self.assertTrue(check_overflow([(1, s)]))


if __name__ == '__main__':
    unittest.main()
