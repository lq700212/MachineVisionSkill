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
    slide.shapes.add_textbox(Mm(10), Mm(30), Mm(200), Mm(20)).text_frame.text = text
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


if __name__ == '__main__':
    unittest.main()
