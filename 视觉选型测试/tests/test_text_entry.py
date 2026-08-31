# -*- coding: utf-8 -*-
"""--text 从0入口回归+注入：需求文本解析、缺参数防呆"""
import unittest

import vt_common  # noqa: F401
from parse_user_data import UserDataParser


class TestTextParsing(unittest.TestCase):
    """需求文本解析回归（模型原样抄字，解析判断全在脚本）"""

    def setUp(self):
        self.parser = UserDataParser()

    def test_parse_standard_text(self):
        """回归: 标准需求文本解析出精度/节拍/检测区域"""
        d = self.parser._extract_params_from_text(
            '设备精度≤0.03mm，生产节拍3秒，检测区域38.5x22mm')
        self.assertAlmostEqual(d.get('precision_requirement'), 0.03, places=6,
                               msg=f'精度解析错误: {d}')
        self.assertAlmostEqual(float(d.get('cycle_time')), 3.0, places=6,
                               msg=f'节拍解析错误: {d}')
        self.assertIn('38.5', str(d.get('detection_area')),
                      msg=f'检测区域解析错误: {d}')

    def test_parse_tolerance_text(self):
        """回归: 公差口径文本解析出tolerance"""
        d = self.parser._extract_params_from_text(
            '检测CD尺寸38.50±0.25，检测区域38.5x22mm')
        self.assertIsNotNone(d.get('tolerance'),
                             msg=f'公差未解析出: {d}')

    def test_parse_no_numbers_returns_empty(self):
        """注入: 无数字信息的文本 → 不产出任何数值口径参数（不猜数字）；
        定性字段（如检测项目"外观检测"）允许提取"""
        d = self.parser._extract_params_from_text('帮我做个外观检测方案')
        numeric_keys = ('precision_requirement', 'tolerance', 'cycle_time',
                        'detection_area', 'part_size', 'field_of_view',
                        'working_distance', 'resolution_requirement')
        leaked = [k for k in numeric_keys if d.get(k) is not None]
        self.assertFalse(leaked, msg=f'无数字文本竟解析出数值参数（疑似编造）: {leaked}')


class TestNonInteractiveGuard(unittest.TestCase):
    """非交互防呆（弱模型调用不卡死在input()）"""

    def test_missing_size_raises_with_guide(self):
        """注入: 缺尺寸 → 非交互报【缺少尺寸信息】+ 三选一指引，不静默默认"""
        from vision_proposal_generator import VisionProposalGenerator
        gen = VisionProposalGenerator()
        gen.auto_mode = True
        with self.assertRaises(ValueError) as cm:
            gen._validate_params({'precision_requirement': 0.03})
        self.assertIn('缺少尺寸信息', str(cm.exception),
                      msg='缺尺寸必须报可执行指引')


if __name__ == '__main__':
    unittest.main()
