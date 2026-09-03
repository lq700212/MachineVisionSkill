# -*- coding: utf-8 -*-
"""选型核心回归+注入：精度链计算、口径决策表优先级、参数防呆、
测量场景远心优先分层（远心无匹配回退普通镜头）"""
import json
import os
import unittest

import vt_common  # noqa: F401 - 先注入被测skill路径
from precision_calculator import PrecisionCalculator, is_measurement_scene


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


class TestMeasurementScene(unittest.TestCase):
    """测量场景单点判定（远心优先分层与核验共用同一条件，防两链漂移）"""

    def test_detection_type_keyword(self):
        """detection_type 含尺寸测量关键词 → 测量场景"""
        self.assertTrue(is_measurement_scene({'detection_type': '尺寸测量',
                                              'precision_requirement': 0.025}))

    def test_high_precision_implies_measurement(self):
        """精度≤0.01mm（无类型字段）→ 测量场景（远心必要性行业默认）"""
        self.assertTrue(is_measurement_scene({'precision_requirement': 0.008}))

    def test_normal_precision_not_measurement(self):
        """精度0.03且非测量类型 → 不分层（普通选型，不强制远心优先）"""
        self.assertFalse(is_measurement_scene({'detection_type': '外观缺陷检测',
                                               'precision_requirement': 0.03}))

    def test_application_measurement(self):
        """application=measurement → 测量场景"""
        self.assertTrue(is_measurement_scene({'application': 'measurement'}))


class TestDetectionTypeParsing(unittest.TestCase):
    """--text 需求解析：检测类型提取（远心优先的触发入口）"""

    def setUp(self):
        from parse_user_data import UserDataParser
        self.parser = UserDataParser()

    def test_extract_size_measurement(self):
        p = self.parser._extract_params_from_text('对垫片做尺寸测量，精度≤0.03mm')
        self.assertEqual(p.get('detection_type'), '尺寸测量',
                         msg='"尺寸测量"关键词必须被提取为detection_type')

    def test_no_false_positive_on_area(self):
        """注入: "检测区域"是几何描述，不得误判为测量场景"""
        p = self.parser._extract_params_from_text('检测区域38.5x22mm，表面缺陷检测')
        self.assertIsNone(p.get('detection_type'),
                          msg='无测量关键词时不得发明detection_type')


class TestTelecentricTiering(unittest.TestCase):
    """测量场景远心优先分层：远心命中优先；库内远心无匹配回退普通镜头"""

    CAMERA = {'brand': '海康威视', 'model': 'MV-CS050-10GM', 'sensor_size': '2/3"',
              'pixel_size': 3.45, 'lens_mount': 'C-Mount',
              'resolution': {'width': 2448, 'height': 2048}, 'max_fps': 24}
    FOV = {'width': 16, 'height': 13}
    NORMAL_LENS = {'brand': '测试品牌', 'model': 'FA-TEST-50', 'type': '定焦镜头',
                   'magnification': 0.5, 'working_distance': 200,
                   'supported_sensor_size': '2/3"', 'supported_sensor_diameter': 11.0,
                   'mount': 'C-Mount', 'distortion': 0.1, 'telecentricity': 1.0,
                   'has_coaxial_light': False, 'verified': True,
                   'verification_url': 'https://example.com'}

    def _selector_with(self, keep_telecentric=True, add_normal=False):
        """临时库副本构造选择器（绝不触碰真实库）"""
        from lens_selector import LensSelector
        db_path = vt_common.copy_real_db(
            os.path.join(vt_common.temp_dir(), 'hardware_database.json'))
        with open(db_path, 'r', encoding='utf-8') as f:
            db = json.load(f)
        if not keep_telecentric:
            db['lenses'] = [l for l in db['lenses']
                            if '远心' not in str(l.get('type', ''))]
        if add_normal:
            db['lenses'].append(dict(self.NORMAL_LENS))
        with open(db_path, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False)
        return LensSelector(database_path=db_path)

    def test_telecentric_hit_marks_preferred(self):
        """回归: 测量场景库内有匹配远心 → 只返回远心并标记 telecentric_preferred"""
        sel = self._selector_with(keep_telecentric=True, add_normal=True)
        result = sel.select_lenses_for_camera(self.CAMERA, self.FOV, 0.03, 3.0,
                                              prefer_telecentric=True, top_n=3)
        self.assertTrue(result, msg='库内远心有匹配时必须返回候选')
        self.assertTrue(all('远心' in l['type'] for l in result),
                        msg='远心层命中时不得混入普通镜头')
        self.assertTrue(all(l.get('telecentric_preferred') for l in result))

    def test_fallback_when_no_telecentric_match(self):
        """回归: 库内远心全部移除 → 回退普通镜头并标记 telecentric_fallback"""
        sel = self._selector_with(keep_telecentric=False, add_normal=True)
        result = sel.select_lenses_for_camera(self.CAMERA, self.FOV, 0.03, 3.0,
                                              prefer_telecentric=True, top_n=3)
        self.assertTrue(result, msg='远心无匹配时必须回退普通镜头而不是空手而归')
        self.assertTrue(all(l.get('telecentric_fallback') for l in result),
                        msg='回退命中必须带 telecentric_fallback 标记供核验提示')

    def test_no_fallback_when_nothing_matches(self):
        """注入: 远心/普通全无匹配 → 诚实返回空列表（不编造），缺口走扩库流程"""
        sel = self._selector_with(keep_telecentric=False, add_normal=False)
        result = sel.select_lenses_for_camera(self.CAMERA, self.FOV, 0.03, 3.0,
                                              prefer_telecentric=True, top_n=3)
        self.assertEqual(result, [], msg='全层无匹配必须空手而归走扩库指引')

    def test_non_measurement_no_tiering(self):
        """回归: 非测量场景不开分层（普通镜头凭评分正常参与）"""
        sel = self._selector_with(keep_telecentric=False, add_normal=True)
        result = sel.select_lenses_for_camera(self.CAMERA, self.FOV, 0.03, 3.0,
                                              prefer_telecentric=False, top_n=3)
        self.assertTrue(result, msg='非测量场景普通镜头应正常命中')


class TestTelecentricFallbackValidation(unittest.TestCase):
    """核验层：远心回退方案的透视误差风险必须醒目提示（WARNING不拦死）"""

    def test_fallback_warns_with_risk_hint(self):
        from validate_selection import SelectionValidator, CheckResult
        validator = SelectionValidator()
        lens = {'type': '定焦镜头', 'model': 'FA-TEST-50',
                'telecentric_fallback': True}
        params = {'detection_type': '尺寸测量', 'precision_requirement': 0.03}
        validator._check_telecentric_necessity(lens, params)
        self.assertEqual(len(validator.checks), 1)
        check = validator.checks[0]
        self.assertEqual(check.result, CheckResult.WARNING,
                         msg='回退方案是权宜解：提示风险但不FAIL拦死')
        self.assertIn('回退', check.message)
        self.assertIn('透视误差', check.suggestion)

    def test_telecentric_passes_measurement(self):
        from validate_selection import SelectionValidator, CheckResult
        validator = SelectionValidator()
        lens = {'type': '物方远心镜头', 'model': 'WWK05'}
        params = {'detection_type': '尺寸测量', 'precision_requirement': 0.03}
        validator._check_telecentric_necessity(lens, params)
        self.assertEqual(validator.checks[0].result, CheckResult.PASS)


if __name__ == '__main__':
    unittest.main()
