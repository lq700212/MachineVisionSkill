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


if __name__ == '__main__':
    unittest.main()
