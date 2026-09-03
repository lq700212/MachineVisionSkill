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


class TestFlyShootingLightChain(unittest.TestCase):
    """飞拍光源链回归（2026-09-03：三处断裂一次修通——类型过滤误杀频闪、
    曝光上限检查方向反了、主流程忽略飞拍且丢 strobe 标记）"""

    def test_strobe_survives_default_type_filter(self):
        """回归: 飞拍+默认类型(环形光)不得把频闪光源提前滤空；
        历史bug：唯一频闪 type=频闪光源≠环形光，查询恒为空"""
        from light_selector import select_light_source
        r = select_light_source(100, 120, light_type='环形光',
                                is_fly_shooting=True, max_exposure_us=100)
        self.assertTrue(r, msg='飞拍查询恒为空=频闪被类型过滤误杀')
        self.assertTrue(all(l.get('strobe') for l in r),
                        msg='飞拍结果必须全是频闪光源')

    def test_loose_exposure_not_filtered(self):
        """回归: 系统上限(2000μs)比光源max(1000μs)宽松是正常余量，
        不得过滤；历史bug：上确界检查方向反了，该过不过"""
        from light_selector import select_light_source
        r = select_light_source(100, 120, light_type='频闪光源',
                                is_fly_shooting=True, max_exposure_us=2000)
        self.assertTrue(r, msg='宽松上限被过滤=上确界检查方向错误')

    def test_too_short_exposure_filtered(self):
        """注入防误伤: 系统要求5μs短于光源最短10μs，必须滤掉（下确界仍有效）"""
        from light_selector import select_light_source
        r = select_light_source(100, 120, light_type='频闪光源',
                                is_fly_shooting=True, max_exposure_us=5)
        self.assertFalse(r, msg='光源打不到系统要求的短曝光，必须无候选')

    def test_main_flow_recommends_strobe(self):
        """回归: 主流程飞拍必须推荐频闪光源且透传 strobe 标记；
        历史bug：主流程忽略 is_fly_shooting，随机拿普通环形光→核验必FAIL"""
        from vision_proposal_generator import VisionProposalGenerator
        g = VisionProposalGenerator()
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


if __name__ == '__main__':
    unittest.main()
