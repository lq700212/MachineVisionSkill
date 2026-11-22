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
        """只给公差时按默认整机分配（0.25×30%=0.075mm 视觉允许误差）"""
        v = self.gen._validate_params(dict(self.base, tolerance=0.25))
        self.assertAlmostEqual(v['precision_requirement'], 0.075, places=6,
                               msg='仅tolerance时应按 30% 分配得 0.075mm')
        self.assertAlmostEqual(
            v['precision_budget']['pixel_precision_max_mm'], 0.025, places=6,
            msg='像素当量上限应为 0.075÷3=0.025mm')

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

    # 2026-09-03 实际项目（视野128mm）：窗口上限0.103x < 库内远心最低0.259x，
    # 日志先空搜远心层再打"无匹配根因"才回退——大视野远心物理不可行应直接短路
    BIG_CAM = {'brand': '海康威视', 'model': 'MV-CS200-10GM', 'sensor_size': '1"',
               'pixel_size': 2.4, 'lens_mount': 'C-Mount',
               'resolution': {'width': 5472, 'height': 3648}, 'max_fps': 16.8}
    BIG_FOV = {'width': 128, 'height': 22.5}

    def test_large_fov_skips_telecentric_layer(self):
        """回归: 窗口上限<库内远心最低倍率 → 跳过远心层直接回退普通镜头"""
        import contextlib, io
        sel = self._selector_with(keep_telecentric=True, add_normal=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = sel.select_lenses_for_camera(self.BIG_CAM, self.BIG_FOV,
                                                  0.093, 3.0,
                                                  prefer_telecentric=True, top_n=3)
        out = buf.getvalue()
        self.assertIn('跳过远心层', out,
                      msg='大视野短路必须输出明确原因（远心物理做不了大视野）')
        self.assertNotIn('搜索范围: 远心镜头', out,
                         msg='远心层注定为空时不得再空搜一遍')
        self.assertTrue(result, msg='库内有FA镜头（v1.10.0入库），回退必须命中')
        self.assertTrue(all(l.get('telecentric_fallback') for l in result),
                        msg='短路回退命中必须带 telecentric_fallback 标记供核验提示')

    def test_small_fov_no_shortcut(self):
        """注入防误伤: 窗口覆盖远心倍率时不得短路（远心层照常先搜）"""
        import contextlib, io
        sel = self._selector_with(keep_telecentric=True, add_normal=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = sel.select_lenses_for_camera(self.CAMERA, self.FOV, 0.03, 3.0,
                                                  prefer_telecentric=True, top_n=3)
        out = buf.getvalue()
        self.assertNotIn('跳过远心层', out,
                         msg='小视野场景误触发短路会架空远心优先策略')
        self.assertTrue(result and all('远心' in l['type'] for l in result),
                        msg='小视野测量场景远心层命中必须优先返回远心')


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


class TestLogicBugfixRangeAndCeil(unittest.TestCase):
    """数值计算回归（2026-09-03 全链审查，执行复现确认后修复）"""

    def test_precision_range_labels_ordered(self):
        """回归: 保守口径必须更严（更小）、放松口径必须更松（更大）；
        历史bug：两者写反（conservative×1.5 更松、relaxed×0.7 更严）"""
        r = PrecisionCalculator().recommend_precision_from_tolerance(0.25)
        pr = r['precision_range']
        self.assertLess(pr['conservative'], r['required_precision_mm'],
                        msg=f"保守口径必须更严: {pr}")
        self.assertGreater(pr['relaxed'], r['required_precision_mm'],
                           msg=f"放松口径必须更松: {pr}")

    def test_required_pixels_true_ceil(self):
        """回归: 向上取整必须真进位；历史bug：int(x+0.999) 在小数部分
        <0.001 时少进一位（2.0000001→2，相机分辨率算小导致选型偏小）"""
        r = PrecisionCalculator().required_pixels(
            {'width': 2.0000001, 'height': 1}, 1.0)
        self.assertEqual(r['x'], 3, msg=f'2.0000001 必须进位到3: {r}')

    def test_exposure_rejects_nonpositive_pixel(self):
        """回归: 像素精度≤0 时曝光计算必须抛错；
        历史bug：返回 0μs 无意义结果，下游按"允许曝光0"误判"""
        with self.assertRaises(ValueError):
            PrecisionCalculator().calculate_max_exposure_time(0, 100)


class TestCameraBestPixelTighterAxis(unittest.TestCase):
    """相机余量比回归：最佳可达像素精度必须取双轴最大值。
    历史bug：只算宽轴，高向受限时余量比虚高（例中虚高约8倍），
    --auto 可能选中实际余量不足的相机"""

    def test_height_limited_reports_max(self):
        from camera_selector import CameraSelector
        sel = CameraSelector()
        sel.cameras = [{'brand': 'T', 'model': 'M', 'sensor_size': '2/3"',
                        'resolution': {'width': 6000, 'height': 4100},
                        'pixel_size': 5.0, 'interface': 'GigE',
                        'max_fps': 30, 'lens_mount': 'C'}]
        cands = sel.select_cameras_for_fov({'width': 50, 'height': 40},
                                           0.03, 3.0, top_n=3)
        self.assertTrue(cands, msg='该相机分辨率满足双轴需求，必须有候选')
        # 高向更紧：max(50/6000, 40/4100)=40/4100；只算宽轴会得到 50/6000
        self.assertAlmostEqual(cands[0]['best_pixel_precision_mm'], 40 / 4100,
                               places=6,
                               msg=f"最佳像素精度必须取受限轴: {cands[0]}")


class TestLegacyLensAperture(unittest.TestCase):
    """旧镜头接口口径回归：判据必须与主流程一致（像素精度 ≤ 精度/k）。
    历史bug：旧接口传整精度不除k，宽松3倍——0.3x镜头物方11.5μm>
    上限10μm，主流程判FAIL，旧接口却判PASS"""

    def test_sub_limit_lens_excluded(self):
        from lens_selector import LensSelector
        db_path = vt_common.copy_real_db(
            os.path.join(vt_common.temp_dir(), 'hardware_database.json'))
        sel = LensSelector(database_path=db_path)
        res = sel.select_lenses(camera_sensor_size='2/3"',
                                camera_pixel_size=3.45,
                                required_precision_mm=0.03, top_n=50)
        bad = [l for l in res if l.get('safety_factor', 99) < 1.0]
        self.assertFalse(bad, msg=f'结果中不得有精度链不满足的镜头: {bad}')
        mags03 = [l.get('model') for l in res
                  if abs(l.get('magnification', 0) - 0.3) < 1e-9]
        self.assertFalse(mags03, msg=f'0.3x物方11.5μm>上限10μm不得通过: {mags03}')


class TestValidateNoneCycle(unittest.TestCase):
    """核验防崩回归：cycle_time 显式 null（config 模板允许空）不得崩溃。
    历史bug：params.get('cycle_time', 3) 在显式 null 时返回 None，
    None>0 直接 TypeError 中断核验"""

    def test_none_cycle_time_no_crash(self):
        from validate_selection import SelectionValidator
        v = SelectionValidator()
        cam = {'brand': 'X', 'model': 'C', 'sensor_size': '2/3"',
               'resolution': {'width': 2448, 'height': 2048},
               'pixel_size': 3.45, 'lens_mount': 'C-Mount', 'max_fps': 24}
        lens = {'brand': 'Y', 'model': 'L', 'type': '物方远心镜头',
                'magnification': 0.5, 'working_distance': 110, 'mount': 'C-Mount',
                'supported_sensor_size': '1.1"'}
        params = {'precision_requirement': 0.03, 'pixel_per_precision': 3.0,
                  'field_of_view': {'width': 16, 'height': 13},
                  'cycle_time': None}
        v.validate(cam, lens, params, verbose=False)  # 不抛错即通过


class TestValidateToleranceOnly(unittest.TestCase):
    """核验防崩回归：只给图纸公差（precision_requirement 显式为 null）不得崩溃。
    历史bug：precision_requirement 为 None 时 None <= 0 抛 TypeError，
    CLI 直接核验会中断（2026-11-20 贴片方案重跑时实测）"""

    CAM = {'brand': '海康威视', 'model': 'MV-CS050-10GM', 'sensor_size': '2/3"',
           'resolution': {'width': 2448, 'height': 2048},
           'pixel_size': 3.45, 'lens_mount': 'C-Mount', 'max_fps': 24.2}
    LENS = {'brand': '海康威视', 'model': 'MVL-MF7538M-ML', 'type': '微距镜头',
            'magnification': 0.333, 'working_distance': 300, 'mount': 'C-Mount',
            'supported_sensor_size': '2/3"'}

    def test_tolerance_only_no_crash_and_passes(self):
        from validate_selection import SelectionValidator, CheckResult
        v = SelectionValidator()
        params = {'precision_requirement': None, 'tolerance': 0.5,
                  'pixel_per_precision': 3.0,
                  'field_of_view': {'width': 24.0, 'height': 19.2},
                  'cycle_time': 1}
        checks = v.validate(self.CAM, self.LENS, params, verbose=False)
        fails = [c for c in checks if c.result == CheckResult.FAIL]
        self.assertEqual(fails, [], f'公差口径不应判 FAIL: {[c.message for c in fails]}')
        chain = next(c for c in checks if c.name == '精度链')
        self.assertEqual(chain.result, CheckResult.PASS, chain.message)
        self.assertIn('公差', chain.message)

    def test_both_missing_still_reports_fail(self):
        """两个口径都缺失时必须明确 FAIL，而不是崩溃"""
        from validate_selection import SelectionValidator, CheckResult
        v = SelectionValidator()
        params = {'pixel_per_precision': 3.0}
        checks = v.validate(self.CAM, self.LENS, params, verbose=False)
        chain = next(c for c in checks if c.name == '精度链')
        self.assertEqual(chain.result, CheckResult.FAIL)
        self.assertIn('tolerance', chain.suggestion)


class TestFlyShootingLightChain(unittest.TestCase):
    """飞拍光源链回归（2026-09-03：三处断裂一次修通——类型过滤误杀频闪、
    曝光上限检查方向反了、主流程忽略飞拍且丢 strobe 标记）

    光源池一律显式注入：本组验的是过滤/透传逻辑，不能依赖真实库恰好有频闪
    型号（2026-11-20 光源库改为只收官网核验条目后，库内暂无频闪型号）。
    """

    @staticmethod
    def _strobe_pool():
        return [{
            'brand': 'CCS', 'model': 'LFV-300X10', 'type': '频闪光源',
            'angle': 45, 'outer_diameter': 150, 'inner_diameter': 120,
            'working_distance_range': [40, 120],
            'strobe': True, 'min_exposure_us': 10, 'max_exposure_us': 1000,
            'verified': True, 'verification_url': 'https://example.invalid/fly',
        }]

    def test_strobe_survives_default_type_filter(self):
        """回归: 飞拍+默认类型(环形光)不得把频闪光源提前滤空；
        历史bug：唯一频闪 type=频闪光源≠环形光，查询恒为空"""
        from light_selector import select_light_source
        r = select_light_source(100, 120, light_type='环形光',
                                is_fly_shooting=True, max_exposure_us=100,
                                lights=self._strobe_pool())
        self.assertTrue(r, msg='飞拍查询恒为空=频闪被类型过滤误杀')
        self.assertTrue(all(l.get('strobe') for l in r),
                        msg='飞拍结果必须全是频闪光源')

    def test_loose_exposure_not_filtered(self):
        """回归: 系统上限(2000μs)比光源max(1000μs)宽松是正常余量，
        不得过滤；历史bug：上确界检查方向反了，该过不过"""
        from light_selector import select_light_source
        r = select_light_source(100, 120, light_type='频闪光源',
                                is_fly_shooting=True, max_exposure_us=2000,
                                lights=self._strobe_pool())
        self.assertTrue(r, msg='宽松上限被过滤=上确界检查方向错误')

    def test_too_short_exposure_filtered(self):
        """注入防误伤: 系统要求5μs短于光源最短10μs，必须滤掉（下确界仍有效）"""
        from light_selector import select_light_source
        r = select_light_source(100, 120, light_type='频闪光源',
                                is_fly_shooting=True, max_exposure_us=5,
                                lights=self._strobe_pool())
        self.assertFalse(r, msg='光源打不到系统要求的短曝光，必须无候选')

    def test_main_flow_recommends_strobe(self):
        """回归: 主流程飞拍必须推荐频闪光源且透传 strobe 标记；
        历史bug：主流程忽略 is_fly_shooting，随机拿普通环形光→核验必FAIL"""
        from unittest import mock
        from vision_proposal_generator import VisionProposalGenerator
        g = VisionProposalGenerator()
        with mock.patch('light_selector.load_light_database',
                        return_value=self._strobe_pool()):
            light = g._recommend_light_source(
                {'field_of_view': {'width': 46.2, 'height': 26.4},
                 'is_fly_shooting': True, 'precision_requirement': 0.03,
                 'pixel_per_precision': 3.0},
                {'working_distance': 110})
        self.assertTrue(light.get('strobe'), msg=f'飞拍必须推荐频闪: {light}')
        self.assertNotIn('光源光源', light.get('type', ''),
                         msg=f"类型标签重复后缀: {light.get('type')}")

    def test_files_chain_no_template_selection_only(self):
        """回归: files链无模板此前 NameError(result_json 未定义)崩溃；
        应正常输出选型结果返回 SELECTION_ONLY"""
        from vision_proposal_generator import VisionProposalGenerator
        tmp = vt_common.temp_dir()
        try:
            txt = os.path.join(tmp, 'demand.txt')
            with open(txt, 'w', encoding='utf-8') as f:
                f.write('设备精度0.03mm, 生产节拍3秒, '
                        '检测区域38.5x22mm, 尺寸测量')
            out = os.path.join(tmp, 'out')
            g = VisionProposalGenerator()
            g.auto_mode = True
            self.assertEqual(g.generate_from_files([txt], out),
                             'SELECTION_ONLY')
            self.assertTrue(
                os.path.isfile(os.path.join(out, 'selection_result.json')),
                msg='无模板也必须落盘 selection_result.json')
        finally:
            vt_common.rmtree(tmp)


class TestConfigDirectHardwareValidation(unittest.TestCase):
    """config显式硬件核验回归：此前本分支跳过核验，
    validation_passed 恒 False，且无效硬件会带着生成PPT"""

    def _real_pair(self):
        with open(os.path.join(vt_common.SKILL_DIR, 'config',
                               'hardware_database.json'),
                  'r', encoding='utf-8') as f:
            db = json.load(f)
        cam = next(c for c in db['cameras']
                   if c.get('model') == 'MV-CS050-10GM')
        lens = next(l for l in db['lenses']
                    if l.get('model') == 'WWK05-110-111V3')
        return cam, lens

    def test_valid_pair_passes_and_saves(self):
        """回归: 有效显式硬件 → SELECTION_ONLY 且 validation_passed 为 True"""
        from vision_proposal_generator import VisionProposalGenerator
        cam, lens = self._real_pair()
        tmp = vt_common.temp_dir()
        try:
            out = os.path.join(tmp, 'out')
            g = VisionProposalGenerator()
            g.auto_mode = True
            r = g.generate_from_config_data(
                {'project_name': 't', 'precision_requirement': 0.03,
                 'cycle_time': 3, 'detection_area': '10x8',
                 'detection_type': '尺寸测量',
                 'camera': cam, 'lens': lens}, out)
            self.assertEqual(r, 'SELECTION_ONLY')
            with open(os.path.join(out, 'selection_result.json'),
                      'r', encoding='utf-8') as f:
                saved = json.load(f)
            self.assertTrue(saved.get('validation_passed'),
                            msg='有效显式硬件核验必须通过')
        finally:
            vt_common.rmtree(tmp)

    def test_invalid_pair_aborts(self):
        """注入: 显式镜头倍率离谱(5x不在窗口) → 核验FAIL中止，不生成PPT"""
        from vision_proposal_generator import VisionProposalGenerator
        cam, lens = self._real_pair()
        bad = dict(lens, magnification=5.0, model='FAKE-5X')
        tmp = vt_common.temp_dir()
        try:
            g = VisionProposalGenerator()
            g.auto_mode = True
            r = g.generate_from_config_data(
                {'project_name': 't', 'precision_requirement': 0.03,
                 'cycle_time': 3, 'detection_area': '10x8',
                 'camera': cam, 'lens': bad}, os.path.join(tmp, 'out'))
            self.assertIsNone(r, msg='无效显式硬件必须中止返回None')
        finally:
            vt_common.rmtree(tmp)

    def test_explicit_hardware_light_not_fabricated(self):
        """回归: 显式相机/镜头但未指定光源时，光源必须来自硬件库；
        历史bug：此处用硬编码 {'brand':'OPT','model':'RL-100-90-W'} 兜底，
        该型号官网无此命名，会绕过核验直接进 selection_result 与 PPT"""
        from vision_proposal_generator import VisionProposalGenerator
        cam, lens = self._real_pair()
        tmp = vt_common.temp_dir()
        try:
            out = os.path.join(tmp, 'out')
            g = VisionProposalGenerator()
            g.auto_mode = True
            r = g.generate_from_config_data(
                {'project_name': 't', 'precision_requirement': 0.03,
                 'cycle_time': 3, 'detection_area': '10x8',
                 'camera': cam, 'lens': lens}, out)
            self.assertIsNotNone(r, msg='合法显式硬件不应中止')
            with open(os.path.join(out, 'selection_result.json'),
                      encoding='utf-8') as f:
                saved = json.load(f)
            light = (saved.get('hardware_selection') or {}).get('light_source') or {}
            model = light.get('model') or ''
            self.assertNotEqual(model, 'RL-100-90-W',
                                msg='不得回退到历史硬编码光源型号')
            if model:
                with open(os.path.join(vt_common.SKILL_DIR, 'config',
                                       'hardware_database.json'),
                          encoding='utf-8') as f:
                    db = json.load(f)
                models = {l.get('model') for l in db['light_sources']}
                self.assertIn(model, models,
                              msg=f'光源 {model} 不在已核验硬件库中')
            else:
                self.assertTrue(light.get('needs_expansion'),
                                msg='无型号时必须标记 needs_expansion')
        finally:
            vt_common.rmtree(tmp)


class TestStringFovAccepted(unittest.TestCase):
    """视野字符串回归：config 手填 "60x40" 字符串此前穿透全部分支、
    误报【内部错误】；应与 field_of_view_input 同规则解析"""

    def test_string_fov_parsed(self):
        from vision_proposal_generator import VisionProposalGenerator
        g = VisionProposalGenerator()
        g.auto_mode = True
        v = g._validate_params({'precision_requirement': 0.03,
                                'cycle_time': 3,
                                'field_of_view': '60x40'})
        self.assertAlmostEqual(v['field_of_view']['width'], 60, places=6)
        self.assertAlmostEqual(v['field_of_view']['height'], 40, places=6)


class TestLightSourceHonesty(unittest.TestCase):
    """光源防幻觉回归（2026-11-20 事故：light_selector 硬编码 6 条由
    \"品牌+尺寸+角度+颜色\"拼造的光源型号，核验只查相机/镜头，不存在的
    OPT RL-150-120-W 一路进交付 PPT，报告仍显示全 PASS）
    """

    CAM = {'brand': 'X', 'model': 'C', 'sensor_size': '2/3"',
           'resolution': {'width': 2448, 'height': 2048},
           'pixel_size': 3.45, 'lens_mount': 'C-Mount', 'max_fps': 24}
    LENS = {'brand': 'Y', 'model': 'L', 'type': '物方远心镜头',
            'magnification': 0.5, 'working_distance': 110, 'mount': 'C-Mount',
            'supported_sensor_size': '1.1"'}
    PARAMS = {'precision_requirement': 0.03, 'pixel_per_precision': 3.0,
              'field_of_view': {'width': 16, 'height': 13}, 'cycle_time': 3}

    def test_empty_db_no_fabricated_model(self):
        """库空时主流程必须返回空型号 + needs_expansion，禁止兜底编造"""
        from unittest import mock
        from vision_proposal_generator import VisionProposalGenerator
        with mock.patch('light_selector.load_light_database', return_value=[]):
            light = VisionProposalGenerator()._recommend_light_source(
                {'field_of_view': {'width': 24, 'height': 19.2},
                 'detection_type': '定位引导'},
                {'working_distance': 300})
        self.assertEqual(light.get('model', ''), '', msg='库空却给出了型号')
        self.assertTrue(light.get('needs_expansion'), msg='库空必须标记需扩库')
        self.assertIn('已核验', light.get('expansion_note', ''))
        self.assertNotIn('RL-', light.get('model', ''),
                         msg='不得回退到历史硬编码型号')

    def test_load_empty_file_returns_empty(self):
        """库文件 light_sources=[] 时必须返回空列表并提示扩库，不得抛错/编造"""
        import io
        import json
        import contextlib
        from light_selector import load_light_database
        tmp = vt_common.temp_dir()
        try:
            path = os.path.join(tmp, 'db.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'light_sources': []}, f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                lights = load_light_database(path)
            self.assertEqual(lights, [])
            self.assertIn('光源库', buf.getvalue())
        finally:
            vt_common.rmtree(tmp)

    def _light_verifiability_check(self, light):
        from validate_selection import SelectionValidator
        checks = SelectionValidator().validate(
            self.CAM, self.LENS, self.PARAMS, light=light, verbose=False)
        return [c for c in checks if c.name == '光源可查证性']

    def test_unverified_light_warns(self):
        """库内 verified=false 条目必须出 WARNING（此前光源完全不进核验）"""
        items = self._light_verifiability_check({
            'brand': '孚根', 'model': 'FG-DR150-A30',
            'verified': False, 'verification_url': 'https://example.invalid/a'})
        self.assertEqual(len(items), 1, msg='光源可查证性检查未接入 validate')
        self.assertEqual(items[0].result.value, '[WARN]')

    def test_verified_without_url_warns(self):
        """标记已核验但缺官网链接 = 来源不可追溯，仍须 WARNING"""
        items = self._light_verifiability_check({
            'brand': '追光者', 'model': 'FL-R-9260-W',
            'verified': True, 'verification_url': ''})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].result.value, '[WARN]')
        self.assertIn('verification_url', items[0].message)

    def test_verified_light_passes(self):
        """完整核验信息的光源应 PASS"""
        items = self._light_verifiability_check({
            'brand': '追光者', 'model': 'FL-R-9260-W',
            'verified': True,
            'verification_url': 'http://f-lighting.cn/show.asp?id=34'})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].result.value, '[PASS]')

    def test_missing_light_warns(self):
        """未提供光源（库无匹配）不得静默——至少 WARNING 提示无法核验"""
        items = self._light_verifiability_check(None)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].result.value, '[WARN]')

    def test_missing_inner_diameter_warns_not_fabricated(self):
        """内径缺失（真实情况：孚根页面未给）→ WARNING，不得编一个数字"""
        from validate_selection import SelectionValidator
        checks = SelectionValidator().validate(
            self.CAM, self.LENS, self.PARAMS,
            light={'brand': '孚根', 'model': 'FG-DR150-A30',
                   'verified': False, 'inner_diameter': None},
            verbose=False)
        inner = [c for c in checks if c.name == '光源内径覆盖']
        self.assertEqual(len(inner), 1)
        self.assertEqual(inner[0].result.value, '[WARN]')


class TestLightAngleAndBrand(unittest.TestCase):
    """光源角度档位与品牌优先级（2026-11-20 用户要求：优先追光者/孚根，
    且环光必须区分高角度与低角度）"""

    def _light(self, brand, model, angle, outer=100, inner=60, verified=True):
        return {'brand': brand, 'model': model, 'type': '环形光',
                'angle': angle, 'outer_diameter': outer,
                'inner_diameter': inner,
                'working_distance_range': [40, 300],
                'verified': verified,
                'verification_url': 'https://example.invalid/x'}

    def test_positioning_prefers_high_angle(self):
        from light_selector import recommend_light_angle
        r = recommend_light_angle('定位引导')
        self.assertEqual(r['mode'], 'high')
        self.assertGreaterEqual(r['preferred'], 60)

    def test_surface_defect_prefers_low_angle(self):
        from light_selector import recommend_light_angle
        r = recommend_light_angle('外观缺陷检测', ['划痕', '毛刺'])
        self.assertEqual(r['mode'], 'low')
        self.assertLessEqual(r['preferred'], 30)

    def test_default_is_mid_angle(self):
        from light_selector import recommend_light_angle
        self.assertEqual(recommend_light_angle('').get('preferred'), 45)

    def test_brand_priority_first_brand_wins(self):
        from light_selector import select_light_source
        pool = [self._light('孚根', 'FG-DR150-A30', 60),
                self._light('追光者', 'FL-R-9260-W', 60)]
        r = select_light_source(30, 200, angle=60, lights=pool,
                                preferred_brands=['追光者', '孚根'])
        self.assertTrue(r)
        self.assertEqual(r[0]['brand'], '追光者',
                         msg='追光者层有合适型号时不得降级到孚根')

    def test_brand_falls_back_when_first_layer_unsuitable(self):
        from light_selector import select_light_source
        pool = [self._light('追光者', 'FL-R-9030-W', 30, outer=90, inner=57),
                self._light('孚根', 'FG-DR180-A60', 60, outer=180, inner=80)]
        # 请求高角度 60°：追光者只有低角度 → 整层无候选 → 降级到孚根高角度
        r = select_light_source(30, 200, angle=60, lights=pool,
                                preferred_brands=['追光者', '孚根'])
        self.assertTrue(r, msg='首品牌无合适型号时必须降级到下一品牌')
        self.assertEqual(r[0]['brand'], '孚根')

    def test_high_angle_request_excludes_low_angle_models(self):
        from light_selector import select_light_source
        pool = [self._light('追光者', 'FL-R-9030-W', 30),
                self._light('追光者', 'FL-R-9260-W', 60)]
        r = select_light_source(30, 200, angle=60, lights=pool)
        self.assertTrue(r)
        self.assertTrue(all(l['angle'] >= 60 for l in r),
                        msg='高角度请求不得返回低角度环光')

    def test_missing_fields_kept_and_flagged(self):
        """内径/WD区间缺失的条目保留但标记未核验（不得丢弃也不得编造）"""
        from light_selector import select_light_source
        pool = [{'brand': '孚根', 'model': 'FG-DR150-A30', 'type': '环形光',
                 'angle': 30, 'outer_diameter': 150, 'inner_diameter': None,
                 'working_distance_range': None, 'verified': False}]
        r = select_light_source(30, 200, angle=30, lights=pool)
        self.assertTrue(r, msg='缺内径/WD的条目不应被直接丢弃')
        self.assertFalse(r[0]['inner_diameter_verified'])
        self.assertFalse(r[0]['wd_range_verified'])
        self.assertIsNone(r[0]['inner_diameter'])


class TestPrecisionUnitHeuristic(unittest.TestCase):
    """口径复核回归（2026-11-20：客户\"偏差≤0.5mm\"被填成 precision_requirement，
    精度链松 10 倍，24mm 视野只需 144px 的荒谬结论）"""

    def _validate_capture(self, params):
        import io
        import contextlib
        from vision_proposal_generator import VisionProposalGenerator
        g = VisionProposalGenerator()
        g.auto_mode = True
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            g._validate_params(params)
        return buf.getvalue()

    def test_tolerance_scale_precision_aborts(self):
        """auto 模式必须硬阻断：弱模型不会读提示，只会把低配方案交付出去"""
        with self.assertRaises(ValueError) as cm:
            self._validate_capture(
                {'precision_requirement': 0.5, 'detection_type': '定位引导',
                 'field_of_view': {'width': 24, 'height': 19.2}, 'cycle_time': 1})
        msg = str(cm.exception)
        self.assertIn('口径复核', msg)
        self.assertIn('tolerance', msg)
        self.assertIn('bilateral', msg,
                      msg='应提示 ±X 用 bilateral（带宽×2）')
        self.assertIn('measurement_accuracy', msg,
                      msg='必须给出"确为测量精度"的显式声明出口')

    def test_measurement_accuracy_basis_passes(self):
        """2026-11-22：客户明确说"测量精度0.5mm" → 0.5 就是视觉指标，放行。

        这与"模糊的精度0.5mm"不同：后者仍要拦截问用户。
        """
        out = self._validate_capture(
            {'precision_requirement': 0.5,
             'precision_basis': 'measurement_accuracy',
             'detection_type': '定位引导',
             'field_of_view': {'width': 24, 'height': 19.2}, 'cycle_time': 1})
        self.assertNotIn('已中止', out)
        self.assertIn('测量精度', out)

    def test_confirmed_precision_passes(self):
        """用户拍板确为设备精度后，显式确认字段可放行"""
        out = self._validate_capture(
            {'precision_requirement': 0.5, 'detection_type': '定位引导',
             'field_of_view': {'width': 24, 'height': 19.2}, 'cycle_time': 1,
             'precision_basis_confirmed': True})
        self.assertNotIn('已中止', out)

    def test_tolerance_filled_no_hint(self):
        """已按 tolerance 填口径时不得再提示"""
        out = self._validate_capture(
            {'tolerance': 0.5, 'detection_type': '定位引导',
             'field_of_view': {'width': 24, 'height': 19.2}, 'cycle_time': 1})
        self.assertNotIn('口径复核', out)

    def test_small_precision_no_hint(self):
        out = self._validate_capture(
            {'precision_requirement': 0.05, 'detection_type': '定位引导',
             'field_of_view': {'width': 24, 'height': 19.2}, 'cycle_time': 1})
        self.assertNotIn('口径复核', out)


class TestWorkingDistanceContract(unittest.TestCase):
    """2026-11-20 事故：MOD=500mm 的镜头在 WD=300mm 项目里凭倍率/视野中选，
    装上去根本不合焦。WD 是硬约束，必须参与过滤与核验。"""

    @classmethod
    def setUpClass(cls):
        from lens_selector import LensSelector, lens_wd_status
        cls.sel = LensSelector()
        cls.wd_status = staticmethod(lens_wd_status)
        db_path = os.path.join(vt_common.SKILL_DIR, 'config', 'hardware_database.json')
        with open(db_path, encoding='utf-8') as f:
            db = json.load(f)
        cls.camera = [c for c in db['cameras'] if c['model'] == 'MV-CS050-10GM'][0]
        cls.fov = {'width': 24, 'height': 19.2}

    def _lens(self, model):
        return [l for l in self.sel.lenses if l['model'] == model][0]

    def test_fixed_wd_telecentric_rejected(self):
        """定工作距离 110/138mm 的远心镜头，不能进 WD=300mm 的候选"""
        for model in ('WWK03-110-230', 'DTCM110-56-AL', 'DTCM110-64H-AL'):
            status, _ = self.wd_status(self._lens(model), 300)
            self.assertEqual(status, 'too_far',
                             f'{model} 在 WD=300 应为 too_far，实际 {status}')

    def test_mod_above_requirement_rejected(self):
        """MOD=500mm 的海康 KF7528 在 WD=300 应为 too_close（核心回归）"""
        status, _ = self.wd_status(
            {'model': 'MVL-KF7528M-12MP', 'mod': 500, 'wd_range': [500, None]}, 300)
        self.assertEqual(status, 'too_close',
                         'MOD=500 在 WD=300 必须判 too_close，否则不合焦也能中选')

    def test_native_macro_kept(self):
        status, detail = self.wd_status(self._lens('MVL-MF7538M-ML'), 300)
        self.assertEqual(status, 'ok')
        self.assertEqual(detail, (250, 550))

    def test_selector_excludes_wd_mismatch(self):
        res = self.sel.select_lenses_for_camera(
            camera=self.camera, fov=self.fov, required_precision_mm=0.05,
            pixel_per_precision=3.0, required_working_distance=300, top_n=10)
        models = [r['model'] for r in res]
        self.assertIn('MVL-MF7538M-ML', models,
                      'WD=300 时微距 MF7538 必须保留')
        for bad in ('WWK03-110-230', 'DTCM110-56-AL', 'WWK10-110-111V3'):
            self.assertNotIn(bad, models,
                             f'WD 不符的 {bad} 不得出现在候选里')
        for r in res:
            self.assertEqual(r.get('wd_status'), 'ok')

    def test_selector_keeps_output_wd_status(self):
        res = self.sel.select_lenses_for_camera(
            camera=self.camera, fov=self.fov, required_precision_mm=0.05,
            pixel_per_precision=3.0, required_working_distance=300, top_n=5)
        self.assertTrue(res, 'WD=300 应有可用候选')
        for r in res:
            self.assertIn('wd_status', r)
            self.assertIn('wd_capability', r)

    def test_missing_wd_requirement_keeps_legacy_behavior(self):
        """不传 WD 时不得因 WD 过滤（兼容旧调用），但条目标记 unknown"""
        res = self.sel.select_lenses_for_camera(
            camera=self.camera, fov=self.fov, required_precision_mm=0.05,
            pixel_per_precision=3.0, top_n=10)
        self.assertTrue(res)
        for r in res:
            self.assertEqual(r.get('wd_status'), 'unknown')

    def test_unknown_capability_not_treated_as_ok(self):
        status, _ = self.wd_status({'model': 'X', 'magnification': 0.3}, 300)
        self.assertEqual(status, 'unknown',
                         '缺 mod/wd_range 必须是 unknown，不能默认 ok')


class TestValidateWorkingDistance(unittest.TestCase):
    """核验链必须与选型链同口径拦截 WD 不符"""

    def _check(self, lens, params):
        from validate_selection import SelectionValidator
        v = SelectionValidator()
        v.checks = []
        v._check_working_distance(lens, params)
        self.assertEqual(len(v.checks), 1)
        return v.checks[0]

    def test_mod_too_far_fails(self):
        c = self._check({'model': 'X', 'mod': 500, 'wd_range': [500, None]},
                        {'working_distance': 300})
        self.assertEqual(c.result.value, '[FAIL]')
        self.assertIn('500', c.message)

    def test_native_range_passes(self):
        c = self._check({'model': 'X', 'mod': 250, 'wd_range': [250, 550]},
                        {'working_distance': 300})
        self.assertEqual(c.result.value, '[PASS]')

    def test_missing_capability_warns(self):
        c = self._check({'model': 'X'}, {'working_distance': 300})
        self.assertEqual(c.result.value, '[WARN]')

    def test_config_wd_takes_priority(self):
        """配置 WD 是项目事实，不能被镜头标称值覆盖"""
        c = self._check({'model': 'X', 'working_distance': 300,
                         'mod': 500, 'wd_range': [500, None]},
                        {'working_distance': 300})
        self.assertEqual(c.result.value, '[FAIL]',
                         '镜头标称 WD=300 不能掩盖 MOD=500 的事实')


class TestMagnificationAtWorkingDistance(unittest.TestCase):
    """2026-11-20 第二轮事故：库内 ``magnification`` 只是某个 WD 下的单点值
    （MF7538 的 0.333 还是薄透镜估算）。选型拿它当任意 WD 都成立，会把
    实际视野算大。官方三点表：250→0.46x、400→0.24x、550→0.16x；
    拟合后 WD=300 实际约 0.352x → 视野 24.0mm，正好卡在需求线（余量≈0）。
    """

    @classmethod
    def setUpClass(cls):
        from lens_selector import LensSelector, magnification_at_wd
        cls.sel = LensSelector()
        cls.mag_at = staticmethod(magnification_at_wd)

    def _lens(self, model):
        return [l for l in self.sel.lenses if l['model'] == model][0]

    def test_official_points_reproduced(self):
        lens = self._lens('MVL-MF7538M-ML')
        for wd, expect in ((250, 0.46), (400, 0.24), (550, 0.16)):
            mag, src = self.mag_at(lens, wd)
            self.assertEqual(src, 'wd_mag_table_interp')
            self.assertAlmostEqual(
                mag, expect, delta=0.01,
                msg=f'WD={wd} 应复现官方 {expect}x，实际 {mag:.4f}')

    def test_wd300_is_at_fov_limit(self):
        lens = self._lens('MVL-MF7538M-ML')
        mag, _ = self.mag_at(lens, 300)
        self.assertAlmostEqual(mag, 0.352, delta=0.005)
        fov_w = 8.4457 / mag
        self.assertLess(fov_w, 24.2, 'WD300 视野不应再有 25.4mm 的乐观值')
        self.assertGreater(fov_w, 23.7)
        self.assertGreater(mag, 0.333,
                           '薄透镜 0.333 会高估视野，不能当官方值用')

    def test_wd330_has_margin(self):
        lens = self._lens('MVL-MF7538M-ML')
        mag, _ = self.mag_at(lens, 330)
        self.assertLess(mag, 0.352)
        self.assertGreater(8.4457 / mag, 24 * 1.1,
                           'WD330 视野余量应超过 10%')

    def test_thin_lens_fallback(self):
        mag, src = self.mag_at({'focal_length': 75, 'magnification': 0.3}, 300)
        self.assertEqual(src, 'thin_lens_estimate')
        self.assertAlmostEqual(mag, 75 / 225, places=4)

    def test_no_wd_uses_single_point(self):
        mag, src = self.mag_at({'focal_length': 75, 'magnification': 0.3}, None)
        self.assertEqual((mag, src), (0.3, 'single_point'))

    def test_selection_uses_effective_mag(self):
        db_path = os.path.join(vt_common.SKILL_DIR, 'config', 'hardware_database.json')
        with open(db_path, encoding='utf-8') as f:
            db = json.load(f)
        cam = [c for c in db['cameras'] if c['model'] == 'MV-CS050-10GM'][0]
        res = self.sel.select_lenses_for_camera(
            cam, {'width': 24, 'height': 19.2}, 0.05, 3.0,
            required_working_distance=300, top_n=5)
        lens = [r for r in res if r['model'] == 'MVL-MF7538M-ML'][0]
        self.assertEqual(lens['magnification_source'], 'wd_mag_table_interp')
        self.assertAlmostEqual(lens['magnification_at_wd'], 0.352, delta=0.005)
        self.assertLess(lens['actual_fov']['width'], 24.2)


class TestValidateFovMargin(unittest.TestCase):
    """视野余量分级：达标记 PASS；靠 2% 容差过线记 WARN（零余量）；盖不住 FAIL"""

    CAM = {'brand': '海康威视', 'model': 'MV-CS050-10GM', 'sensor_size': '2/3"',
           'resolution': {'width': 2448, 'height': 2048},
           'pixel_size': 3.45, 'lens_mount': 'C-Mount', 'max_fps': 24.2}
    PARAMS = {'tolerance': 0.5, 'pixel_per_precision': 3.0,
              'field_of_view': {'width': 24.0, 'height': 19.2},
              'working_distance': 300}

    def _check(self, mag):
        from validate_selection import SelectionValidator
        v = SelectionValidator()
        v.checks = []
        v._check_fov_coverage(self.CAM, {'magnification': mag}, self.PARAMS)
        self.assertEqual(len(v.checks), 1)
        return v.checks[0]

    def test_full_margin_passes(self):
        self.assertEqual(self._check(0.333).result.value, '[PASS]')

    def test_zero_margin_warns(self):
        c = self._check(0.3523)
        self.assertEqual(c.result.value, '[WARN]',
                         'WD300 视野 24.0mm 是零余量，必须 WARN 而不是 PASS')
        self.assertIn('上调', c.suggestion)

    def test_not_covering_fails(self):
        self.assertEqual(self._check(0.50).result.value, '[FAIL]')


class TestPrecisionBudget(unittest.TestCase):
    """2026-11-21 事故：业界两套精度口径被叠加。

    基恩士/HSM：尺寸测量 像素当量 = 公差带 ÷ 10（视觉直测）。
    整机分配：像素当量 = 视觉允许误差 ÷ 3。
    旧实现连用 /10 和 /3（等价公差/30），比行业常规严 3 倍，
    且把中间值叫"设备精度"。本组锁死两种 mode 各自的换算。
    """

    @classmethod
    def setUpClass(cls):
        from precision_calculator import resolve_precision_budget
        cls.resolve = staticmethod(resolve_precision_budget)

    def test_system_budget_1_5(self):
        b = self.resolve({
            'tolerance': 0.5,
            'precision_model': {'mode': 'system_budget',
                                'tolerance_type': 'unilateral',
                                'allocation_ratio': 0.2, 'pixel_factor': 3.0}})
        self.assertEqual(b['mode'], 'system_budget')
        self.assertAlmostEqual(b['tolerance_band_mm'], 0.5)
        self.assertAlmostEqual(b['allowed_error_mm'], 0.1)
        self.assertAlmostEqual(b['pixel_precision_max_um'], 33.33, delta=0.1)
        self.assertFalse(b['is_assumption'])

    def test_system_budget_not_double_divided(self):
        """回归：不得再出现 公差/10/3（0.5→16.7μm）的叠加口径"""
        b = self.resolve({
            'tolerance': 0.5,
            'precision_model': {'mode': 'system_budget',
                                'allocation_ratio': 0.2, 'pixel_factor': 3.0}})
        self.assertGreater(b['pixel_precision_max_um'], 30,
                           '1/5 分配应为 33μm，不能退化成 16.7μm')

    def test_bilateral_doubles_band(self):
        b = self.resolve({
            'tolerance': 0.5,
            'precision_model': {'mode': 'system_budget',
                                'tolerance_type': 'bilateral',
                                'allocation_ratio': 0.1, 'pixel_factor': 3.0}})
        self.assertAlmostEqual(b['tolerance_band_mm'], 1.0)
        self.assertAlmostEqual(b['allowed_error_mm'], 0.1)
        self.assertAlmostEqual(b['pixel_precision_max_um'], 33.33, delta=0.1)

    def test_direct_measurement_factor_10(self):
        b = self.resolve({
            'tolerance': 0.5,
            'precision_model': {'mode': 'direct_measurement',
                                'application': 'measurement'}})
        self.assertEqual(b['mode'], 'direct_measurement')
        self.assertAlmostEqual(b['pixel_precision_max_um'], 50.0)

    def test_direct_defect_factor_4(self):
        b = self.resolve({
            'tolerance': 0.5,
            'precision_model': {'mode': 'direct_measurement',
                                'application': 'defect'}})
        self.assertAlmostEqual(b['pixel_precision_max_um'], 125.0)

    def test_explicit_pixel_precision(self):
        b = self.resolve({'pixel_precision': 0.02})
        self.assertEqual(b['mode'], 'explicit_pixel')
        self.assertAlmostEqual(b['pixel_precision_max_um'], 20.0)

    def test_explicit_precision(self):
        b = self.resolve({'precision_requirement': 0.03})
        self.assertEqual(b['mode'], 'explicit_precision')
        self.assertAlmostEqual(b['pixel_precision_max_um'], 10.0)

    def test_measurement_accuracy_not_allocated(self):
        """2026-11-22：客户测量精度 0.5mm 直接÷3=166.7μm/px。

        行业里"测量精度"是视觉系统指标，不再乘整机分配比例；
        旧实现按整机公差 1/10 再÷3 会算成 16.7μm/px，严 10 倍。
        """
        b = self.resolve({'precision_requirement': 0.5,
                          'precision_basis': 'measurement_accuracy'})
        self.assertEqual(b['mode'], 'explicit_precision')
        self.assertAlmostEqual(b['allowed_error_mm'], 0.5)
        self.assertAlmostEqual(b['pixel_precision_max_um'], 166.67, delta=0.1)
        self.assertIn('客户测量精度', b['basis_text'])

    def test_precision_requirement_beats_tolerance_with_model(self):
        """回归：即使 precision_model 已声明，precision_requirement 也优先。

        旧实现 model_declared=True 时让 tolerance 压过 precision_requirement，
        日志说"精度优先"、预算却按公差算，选型链与核验链口径分裂。
        """
        b = self.resolve({
            'precision_requirement': 0.5,
            'precision_basis': 'measurement_accuracy',
            'tolerance': 0.05,
            'precision_model': {'mode': 'system_budget',
                                'tolerance_type': 'bilateral',
                                'allocation_ratio': 0.3, 'pixel_factor': 3.0}})
        self.assertEqual(b['mode'], 'explicit_precision')
        self.assertAlmostEqual(b['allowed_error_mm'], 0.5)
        self.assertAlmostEqual(b['pixel_precision_max_um'], 166.67, delta=0.1)

    def test_tolerance_only_defaults_to_industry_budget(self):
        """未声明模型时按行业常规 30% 分配：0.5×0.3÷3=50μm，等效公差÷10。

        2026-11-22 前默认 1/10 再÷3=16.7μm（公差÷30），比基恩士/HSM
        的"像素当量=公差带÷10"严 3 倍，属于过度保守。
        """
        b = self.resolve({'tolerance': 0.5})
        self.assertEqual(b['mode'], 'system_budget')
        self.assertTrue(b['is_assumption'], '未声明模型必须标记为假设')
        self.assertAlmostEqual(b['pixel_precision_max_um'], 50.0, delta=0.1)

    def test_all_missing_returns_none(self):
        self.assertIsNone(self.resolve({}))


class TestValidatePrecisionBasis(unittest.TestCase):
    """精度口径必须在核验报告里显性化：声明了 model=PASS，默认兜底=WARN"""

    CAM = {'brand': '海康威视', 'model': 'MV-CS050-10GM', 'sensor_size': '2/3"',
           'resolution': {'width': 2448, 'height': 2048},
           'pixel_size': 3.45, 'lens_mount': 'C-Mount', 'max_fps': 24.2}
    LENS = {'brand': '海康威视', 'model': 'MVL-MF7538M-ML', 'type': '微距镜头',
            'magnification': 0.333, 'working_distance': 320, 'mount': 'C-Mount',
            'supported_sensor_size': '2/3"'}
    BASE = {'tolerance': 0.5, 'pixel_per_precision': 3.0,
            'field_of_view': {'width': 24.0, 'height': 19.2},
            'working_distance': 320}

    def _checks(self, extra):
        from validate_selection import SelectionValidator
        params = dict(self.BASE)
        params.update(extra)
        v = SelectionValidator()
        return v.validate(self.CAM, self.LENS, params, verbose=False)

    def test_declared_model_passes(self):
        checks = self._checks({'precision_model': {
            'mode': 'system_budget', 'tolerance_type': 'unilateral',
            'allocation_ratio': 0.2, 'pixel_factor': 3.0}})
        basis = next(c for c in checks if c.name == '精度口径')
        self.assertEqual(basis.result.value, '[PASS]', basis.message)
        self.assertIn('20%', basis.message)

    def test_undeclared_model_warns(self):
        checks = self._checks({})
        basis = next(c for c in checks if c.name == '精度口径')
        self.assertEqual(basis.result.value, '[WARN]',
                         '未声明 precision_model 时分配比例只是假设，必须 WARN')
        self.assertIn('30%', basis.message,
                      '未声明模型时应按行业常规 30% 分配并在报告中标出')

    def test_precision_chain_uses_budget(self):
        checks = self._checks({'precision_model': {
            'mode': 'system_budget', 'tolerance_type': 'unilateral',
            'allocation_ratio': 0.2, 'pixel_factor': 3.0}})
        chain = next(c for c in checks if c.name == '精度链')
        self.assertEqual(chain.result.value, '[PASS]', chain.message)
        self.assertIn('33.3', chain.message, '上限应为 0.5×20%÷3=33.3μm')
        self.assertIn('3.', chain.message, '余量应约 3.2 倍')


if __name__ == '__main__':
    unittest.main()
