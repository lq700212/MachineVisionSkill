# -*- coding: utf-8 -*-
"""工控行业规范复核回归（2026-11-21）

覆盖本轮对照行业规范补齐的硬约束：
  1. 光学质量：景深/MTF30/衍射（厂家值优先，缺失用公式估算，无法判定 INFO）
  2. 接口带宽：需求帧率下数据率 ≤ 接口有效带宽（GigE 有效约 110MB/s）
  3. 快门类型：运动/飞拍必须全局快门（卷帘→FAIL）
  4. 飞拍频闪：strobe 三态（True/False/None），"未核验"不得当"不支持"
  5. 选型链与预算同口径：direct_measurement 不再二次除亚像素因子
"""
import unittest

import vt_common  # noqa: F401 - 注入被测skill路径

from precision_calculator import (
    parse_depth_of_field_half_mm, parse_mtf30_lpmm, nyquist_lpmm,
    airy_disk_um, estimate_object_dof_half_mm, is_moving_scene,
    shutter_kind, camera_interface_status, required_fps,
    resolve_precision_budget,
)
from camera_selector import CameraSelector
from light_selector import select_light_source
from validate_selection import SelectionValidator, CheckResult


CAM_BASE = {
    'brand': '测试', 'model': 'CAM-5MP', 'sensor_size': '2/3"',
    'resolution': {'width': 2448, 'height': 2048}, 'pixel_size': 3.45,
    'lens_mount': 'C', 'interface': 'GigE', 'max_fps': 24.2,
    'shutter': '全局快门',
}

LENS_BASE = {
    'brand': '测试', 'model': 'LENS-0.32X', 'magnification': 0.32,
    'working_distance': 320, 'mount': 'C', 'f_number': 'F3.8',
    'supported_sensor_diameter': 11.0,
}


def result_of(checks, name):
    return [c for c in checks if c.name == name]


class TestOpticsHelpers(unittest.TestCase):
    """光学估算函数：单位/语义必须明确，不得把未知当 0"""

    def test_dof_requires_pm_marker(self):
        self.assertAlmostEqual(parse_depth_of_field_half_mm('±0.35mm'), 0.35)
        self.assertAlmostEqual(parse_depth_of_field_half_mm('±2.5mm@F5.6'), 2.5)
        # 纯数字语义不明（可能是总景深），必须返回 None 交核验标未核验
        self.assertIsNone(parse_depth_of_field_half_mm('0.7'))
        self.assertIsNone(parse_depth_of_field_half_mm(0.7))
        self.assertIsNone(parse_depth_of_field_half_mm(None))

    def test_mtf30_parse(self):
        self.assertEqual(parse_mtf30_lpmm(170), 170)
        self.assertEqual(parse_mtf30_lpmm('≥124lp/mm@全视场'), 124)
        self.assertIsNone(parse_mtf30_lpmm(None))
        self.assertIsNone(parse_mtf30_lpmm('未提供'))

    def test_nyquist(self):
        # 3.45μm 像元 → 1000/(2×3.45)=144.9 lp/mm
        self.assertAlmostEqual(nyquist_lpmm(3.45), 144.93, places=1)

    def test_airy_disk(self):
        # 2.44 × 0.55μm × 3.8 ≈ 5.1μm
        self.assertAlmostEqual(airy_disk_um(3.8), 5.10, places=2)
        self.assertIsNone(airy_disk_um(None))

    def test_dof_estimate(self):
        # F3.8 / 3.45μm / β0.3216 → 约 ±0.168mm
        v = estimate_object_dof_half_mm(3.8, 3.45, 0.3216)
        self.assertIsNotNone(v)
        self.assertAlmostEqual(v, 0.168, places=3)
        self.assertIsNone(estimate_object_dof_half_mm(None, 3.45, 0.32))
        self.assertIsNone(estimate_object_dof_half_mm(3.8, 0, 0.32))


class TestSceneHelpers(unittest.TestCase):
    def test_is_moving_scene(self):
        self.assertTrue(is_moving_scene({'is_fly_shooting': True}))
        self.assertTrue(is_moving_scene({'conveyor_speed': 200}))
        self.assertTrue(is_moving_scene({'detection_type': '流水线飞拍定位'}))
        self.assertFalse(is_moving_scene({'detection_type': '静态工位定位'}))

    def test_shutter_kind(self):
        self.assertEqual(shutter_kind({'shutter': '全局快门'}), 'global')
        self.assertEqual(shutter_kind({'shutter': 'Global Shutter'}), 'global')
        self.assertEqual(shutter_kind({'shutter': '卷帘快门'}), 'rolling')
        self.assertEqual(shutter_kind({'shutter': 'Rolling'}), 'rolling')
        self.assertEqual(shutter_kind({}), 'unknown')


class TestInterfaceBandwidth(unittest.TestCase):
    """GigE 满帧 5MP×24fps 超有效带宽；需求帧率下必须重算"""

    def test_gige_full_rate_over(self):
        st = camera_interface_status(CAM_BASE, 24.2)
        self.assertEqual(st['status'], 'over')
        self.assertGreater(st['data_rate_mbps'], 110)

    def test_gige_required_rate_ok(self):
        # 本项目 1s 节拍 → 需求 1.5fps → 约 7.5MB/s
        st = camera_interface_status(CAM_BASE, 1.5)
        self.assertEqual(st['status'], 'ok')
        self.assertAlmostEqual(st['data_rate_mbps'], 7.52, places=1)

    def test_unknown_interface(self):
        cam = dict(CAM_BASE, interface='某私有接口')
        self.assertEqual(camera_interface_status(cam, 1.5)['status'], 'unknown')

    def test_required_fps(self):
        self.assertAlmostEqual(required_fps({'cycle_time': 1}), 1.5)
        self.assertIsNone(required_fps({}))
        self.assertIsNone(required_fps({'cycle_time': 0}))


class TestValidatorOptics(unittest.TestCase):
    def setUp(self):
        self.v = SelectionValidator()

    def test_dof_insufficient_fail(self):
        lens = dict(LENS_BASE, depth_of_field='±0.10mm')
        self.v._check_optics_quality(CAM_BASE, lens,
                                     {'part_height_variation_mm': 0.2})
        items = result_of(self.v.checks, '景深')
        self.assertEqual(items[0].result, CheckResult.FAIL)

    def test_dof_no_height_variation_info(self):
        self.v._check_optics_quality(CAM_BASE, LENS_BASE, {})
        items = result_of(self.v.checks, '景深')
        self.assertEqual(items[0].result, CheckResult.INFO)
        self.assertIn('未提供工件高度波动', items[0].message)

    def test_mtf_below_nyquist_warn(self):
        lens = dict(LENS_BASE, mtf30=80)
        self.v._check_optics_quality(CAM_BASE, lens, {})
        items = result_of(self.v.checks, '镜头解析力')
        self.assertEqual(items[0].result, CheckResult.WARNING)

    def test_mtf_above_nyquist_pass(self):
        lens = dict(LENS_BASE, mtf30=170)
        self.v._check_optics_quality(CAM_BASE, lens, {})
        items = result_of(self.v.checks, '镜头解析力')
        self.assertEqual(items[0].result, CheckResult.PASS)

    def test_diffraction_small_aperture_warn(self):
        # F16 → 艾里斑 21.5μm ≈ 6.2×像元，衍射成为瓶颈
        lens = dict(LENS_BASE, f_number='F16')
        self.v._check_optics_quality(CAM_BASE, lens, {})
        items = result_of(self.v.checks, '光圈衍射')
        self.assertEqual(items[0].result, CheckResult.WARNING)


class TestValidatorBandwidth(unittest.TestCase):
    def setUp(self):
        self.v = SelectionValidator()

    def test_bandwidth_over_fail(self):
        self.v._check_interface_bandwidth(CAM_BASE, {'cycle_time': 0.01})
        items = result_of(self.v.checks, '接口带宽')
        self.assertEqual(items[0].result, CheckResult.FAIL)

    def test_bandwidth_ok(self):
        self.v._check_interface_bandwidth(CAM_BASE, {'cycle_time': 1})
        items = result_of(self.v.checks, '接口带宽')
        self.assertEqual(items[0].result, CheckResult.PASS)

    def test_bandwidth_no_cycle_info(self):
        self.v._check_interface_bandwidth(CAM_BASE, {})
        items = result_of(self.v.checks, '接口带宽')
        self.assertEqual(items[0].result, CheckResult.INFO)


class TestValidatorShutter(unittest.TestCase):
    def setUp(self):
        self.v = SelectionValidator()

    def test_rolling_in_moving_scene_fail(self):
        cam = dict(CAM_BASE, shutter='卷帘快门')
        self.v._check_shutter(cam, {'is_fly_shooting': True})
        items = result_of(self.v.checks, '快门类型')
        self.assertEqual(items[0].result, CheckResult.FAIL)

    def test_global_in_moving_scene_pass(self):
        self.v._check_shutter(CAM_BASE, {'is_fly_shooting': True})
        items = result_of(self.v.checks, '快门类型')
        self.assertEqual(items[0].result, CheckResult.PASS)

    def test_rolling_static_pass(self):
        cam = dict(CAM_BASE, shutter='卷帘快门')
        self.v._check_shutter(cam, {'detection_type': '静态定位'})
        items = result_of(self.v.checks, '快门类型')
        self.assertEqual(items[0].result, CheckResult.PASS)

    def test_unknown_shutter_warn(self):
        cam = dict(CAM_BASE)
        cam.pop('shutter')
        self.v._check_shutter(cam, {})
        items = result_of(self.v.checks, '快门类型')
        self.assertEqual(items[0].result, CheckResult.WARNING)


class TestFlyLightStrobe(unittest.TestCase):
    """飞拍光源：未核验(None)不是不支持(False)"""

    def _fly_checks(self, light):
        params = {'is_fly_shooting': True, 'conveyor_speed': 100,
                  'precision_requirement': 0.03}
        v = SelectionValidator()
        v._check_fly_shooting(CAM_BASE, LENS_BASE, params, light)
        return result_of(v.checks, '飞拍光源') or \
            result_of(v.checks, '飞拍曝光时间')

    def test_strobe_unknown_warn(self):
        items = self._fly_checks({'model': 'L1', 'strobe': None})
        self.assertTrue(items)
        self.assertEqual(items[0].result, CheckResult.WARNING)
        self.assertIn('未核验', items[0].message)

    def test_strobe_false_fail(self):
        items = self._fly_checks({'model': 'L1', 'strobe': False})
        self.assertTrue(items)
        self.assertEqual(items[0].result, CheckResult.FAIL)

    def test_strobe_true_checked_exposure(self):
        items = self._fly_checks({'model': 'L1', 'strobe': True,
                                  'min_exposure_us': 5})
        self.assertTrue(items)
        self.assertEqual(items[0].result, CheckResult.PASS)

    def test_light_selector_keeps_unverified_strobe(self):
        lights = [
            {'model': 'UNVERIFIED', 'type': '环形光', 'angle': 60,
             'outer_diameter': 200, 'inner_diameter': 100, 'brand': 'A'},
            {'model': 'NO-STROBE', 'type': '环形光', 'angle': 60,
             'strobe': False, 'outer_diameter': 200, 'inner_diameter': 100,
             'brand': 'A'},
        ]
        got = select_light_source(60, 200, light_type='环形光',
                                  is_fly_shooting=True, lights=lights,
                                  angle=60)
        models = [g['model'] for g in got]
        self.assertIn('UNVERIFIED', models, '未核验频闪能力不得被静默丢弃')
        self.assertNotIn('NO-STROBE', models, '明确不支持频闪必须排除')
        row = [g for g in got if g['model'] == 'UNVERIFIED'][0]
        self.assertTrue(row['strobe_unverified'])


class TestSelectionUsesBudget(unittest.TestCase):
    """选型链必须用预算模型的像素当量上限，不得二次除亚像素因子"""

    def test_direct_measurement_not_divided_twice(self):
        cfg = {
            'tolerance': 0.5,
            'precision_model': {'mode': 'direct_measurement',
                                'application': 'measurement',
                                'tolerance_type': 'total'},
            'field_of_view': {'width': 24.0, 'height': 19.2},
        }
        budget = resolve_precision_budget(cfg)
        # 直测口径：公差带 0.5mm ÷ 10 = 50μm/px
        self.assertAlmostEqual(budget['pixel_precision_max_um'], 50.0, places=3)

        selector = CameraSelector()
        cams = selector.select_cameras_for_fov(
            fov={'width': 24.0, 'height': 19.2},
            required_precision_mm=budget['allowed_error_mm'],
            pixel_per_precision=3.0,
            pixel_precision_max_mm=budget['pixel_precision_max_mm'],
        )
        self.assertTrue(cams)
        # 选型器回传的上限必须与预算一致（不是 50/3=16.7）
        self.assertAlmostEqual(cams[0]['pixel_precision_max_mm'],
                               budget['pixel_precision_max_mm'], places=9)
        # 所需像素：24/0.05=480 宽
        self.assertEqual(cams[0]['required_pixels']['x'], 480)


if __name__ == '__main__':
    unittest.main(verbosity=2)
