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
                        'working_distance', 'resolution_requirement',
                        'pixel_precision')
        leaked = [k for k in numeric_keys if d.get(k) is not None]
        self.assertFalse(leaked, msg=f'无数字文本竟解析出数值参数（疑似编造）: {leaked}')

    def test_parse_pixel_precision_text(self):
        """回归(像素精度死循环bug): 用户明说"像素精度0.01mm/pixel" →
        必须解析出 pixel_precision（像素级口径），且不得误抓进 precision_requirement。
        历史bug：旧正则把"像素精度：0.01mm"抓成设备精度再÷3 → 无解 → 弱模型调参死循环"""
        d = self.parser._extract_params_from_text(
            '像素精度：0.01mm/pixel，生产节拍3秒，检测区域38.5x22mm')
        self.assertAlmostEqual(d.get('pixel_precision'), 0.01, places=6,
                               msg=f'像素精度未解析出: {d}')
        self.assertIsNone(d.get('precision_requirement'),
                          msg=f'像素精度被误抓成设备精度（差3倍无解死循环根因）: {d}')

    def test_parse_pixel_precision_without_slash(self):
        """回归: "像素精度0.01mm"（不带/pixel后缀）也按像素级口径解析"""
        d = self.parser._extract_params_from_text(
            '要求像素精度0.02mm，检测区域38.5x22mm')
        self.assertAlmostEqual(d.get('pixel_precision'), 0.02, places=6,
                               msg=f'像素精度未解析出: {d}')
        self.assertIsNone(d.get('precision_requirement'),
                          msg=f'像素精度被误抓成设备精度: {d}')

    def test_device_precision_not_hijacked(self):
        """回归: 设备精度口径不被像素精度通道劫持（两口径各走各路）"""
        d = self.parser._extract_params_from_text(
            '设备精度≤0.03mm，检测区域38.5x22mm')
        self.assertAlmostEqual(d.get('precision_requirement'), 0.03, places=6,
                               msg=f'设备精度解析错误: {d}')
        self.assertIsNone(d.get('pixel_precision'),
                          msg=f'设备精度被误抓成像素精度: {d}')


class TestPixelPrecisionConfigChain(unittest.TestCase):
    """config 像素级口径链路（pixel_precision 字段 → 等效设备精度）"""

    def test_pixel_precision_converts_to_device_precision(self):
        """回归(像素精度死循环bug): pixel_precision=0.01 → 等效设备精度0.03，
        不再报【缺少精度口径】；历史bug：脚本无像素级口径入口，弱模型无合法路径可走"""
        from vision_proposal_generator import VisionProposalGenerator
        gen = VisionProposalGenerator()
        gen.auto_mode = True
        validated = gen._validate_params({
            'pixel_precision': 0.01,
            'detection_area': '38.5x22',
        })
        self.assertAlmostEqual(validated['precision_requirement'], 0.03, places=6,
                               msg=f"等效设备精度换算错误: {validated['precision_requirement']}")
        self.assertAlmostEqual(validated['pixel_precision_max_mm'], 0.01, places=6,
                               msg=f"像素精度上限应原样等于用户口径: "
                                   f"{validated.get('pixel_precision_max_mm')}")
        self.assertEqual(validated.get('precision_source'), 'pixel_precision')

    def test_pixel_precision_conflict_warns_and_wins(self):
        """回归: pixel_precision 与 precision_requirement 同时给 →
        采用用户明说的像素级口径（冲突警告，不静默用设备精度）"""
        from vision_proposal_generator import VisionProposalGenerator
        gen = VisionProposalGenerator()
        gen.auto_mode = True
        validated = gen._validate_params({
            'pixel_precision': 0.01,
            'precision_requirement': 0.05,
            'detection_area': '38.5x22',
        })
        self.assertAlmostEqual(validated['precision_requirement'], 0.03, places=6,
                               msg=f"口径冲突时应采用像素级口径: "
                                   f"{validated['precision_requirement']}")


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


class TestFlyShootingParsing(unittest.TestCase):
    """飞拍关键词匹配回归（此前用子串 in 匹配 keywords 表：
    正则式 fly.*shot 永远命中不了，且大小写敏感漏掉 Conveyor）"""

    def setUp(self):
        self.parser = UserDataParser()

    def test_regex_keyword_fly_shot(self):
        """回归: 英文 fly shot 必须命中飞拍（正则分支）"""
        d = self.parser._extract_params_from_text(
            'system uses fly shot on the line, 检测区域38.5x22mm')
        self.assertTrue(d.get('is_fly_shooting'),
                       msg=f'fly.*shot 正则未命中: {d}')

    def test_case_insensitive_conveyor(self):
        """回归: Conveyor 首字母大写也必须命中（大小写不敏感）"""
        d = self.parser._extract_params_from_text(
            'Conveyor speed 100mm/s, 检测区域38.5x22mm')
        self.assertTrue(d.get('is_fly_shooting'),
                       msg=f'大写 Conveyor 未命中: {d}')

    def test_chinese_still_works(self):
        """回归: 中文"流水线上不停"照常命中（不因改正则误伤中文）"""
        d = self.parser._extract_params_from_text(
            '零件在流水线上不停，检测区域38.5x22mm')
        self.assertTrue(d.get('is_fly_shooting'),
                       msg=f'中文飞拍关键词未命中: {d}')


if __name__ == '__main__':
    unittest.main()
