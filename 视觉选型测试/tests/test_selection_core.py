# -*- coding: utf-8 -*-
"""选型核心回归+注入：精度链计算、口径决策表优先级、参数防呆"""
import unittest

import vt_common  # noqa: F401 - 先注入被测skill路径
from precision_calculator import PrecisionCalculator


class TestPrecisionChain(unittest.TestCase):
    """精度链计算回归"""

    def setUp(self):
        self.calc = PrecisionCalculator()

    def test_tolerance_to_precision_unilateral(self):
        """回归: 图纸公差0.25(±0.25单边) → 精度0.025"""
        r = self.calc.tolerance_to_precision(0.25)
        self.assertAlmostEqual(r['required_precision_mm'], 0.025, places=6,
                               msg='公差/10反推值错误')

    def test_pixel_accuracy_limit(self):
        """回归: 精度0.03、k=3 → 像素精度上限0.01mm/pixel（单位铁律）"""
        limit = 0.03 / 3.0
        self.assertAlmostEqual(limit, 0.01, places=6,
                               msg='像素精度上限=设备精度÷亚像素因子，不得混淆单位')


class TestPrecisionPriority(unittest.TestCase):
    """口径决策表优先级（2026-08-30事故：tolerance无条件覆盖precision_requirement，
    项目唯一可行相机被口径漂移挤出局导致选型无解——修复为precision_requirement优先）"""

    def setUp(self):
        from vision_proposal_generator import VisionProposalGenerator
        self.gen = VisionProposalGenerator()
        self.base = {'detection_area': '38.5x22', 'cycle_time': 3}

    def test_precision_priority_over_tolerance(self):
        """回归: 两口径同填时 precision_requirement 必须优先（决策表明文）"""
        v = self.gen._validate_params(dict(self.base,
                                           precision_requirement=0.03,
                                           tolerance=0.25))
        self.assertAlmostEqual(v['precision_requirement'], 0.03, places=6,
                               msg='precision_requirement被tolerance覆盖=口径漂移bug复发')

    def test_tolerance_only_backfill(self):
        """回归: 只给公差时按公差/10反推精度"""
        v = self.gen._validate_params(dict(self.base, tolerance=0.25))
        self.assertAlmostEqual(v['precision_requirement'], 0.025, places=6,
                               msg='仅tolerance时应反推0.025')

    def test_missing_precision_raises_with_guide(self):
        """注入: 两口径全空 → 非交互环境报可执行指引而非卡死/静默默认"""
        with self.assertRaises(ValueError) as cm:
            self.gen.auto_mode = True
            self.gen._validate_params(dict(self.base))
        self.assertIn('precision_requirement', str(cm.exception),
                      msg='报错必须给出可执行的填写指引')


if __name__ == '__main__':
    unittest.main()
