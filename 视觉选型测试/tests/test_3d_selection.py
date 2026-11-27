# -*- coding: utf-8 -*-
"""3D 视觉引导选型分支（three_d_selector.py）契约测试。

覆盖：
  - 3D 相机库 schema / 可查证 / 置信度字段
  - FOV 插值（两点线性 / 单点缩放）
  - 误差预算（设计目标 80%、RSS 可复现、四项超目标时 budget_infeasible）
  - 厂商 guidance 优先于自算
  - 参数校验 exit 2（缺尺寸 / 缺精度 / 口径未声明）
  - 端到端：300x300 / 0.5mm → exit 0 且有 PASS
  - 注入：巨大产品 → 全 FAIL exit 1
  - Markdown 必含误差预算与厂商对比章节
"""
import json
import os
import subprocess
import sys
import unittest

import vt_common

TOOLS = vt_common.TOOLS_DIR
SKILL = vt_common.SKILL_DIR
SCRIPT = os.path.join(TOOLS, 'three_d_selector.py')
DB = os.path.join(SKILL, 'config', 'hardware_database.json')

if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import three_d_selector as tds  # noqa: E402


def load_db():
    with open(DB, encoding='utf-8') as f:
        return json.load(f)


def run_cli(args, cwd=None):
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        env=env, cwd=cwd or TOOLS, timeout=120,
    )


class TestThreeDCameraDatabase(unittest.TestCase):
    """3D 相机库必须可查证、字段完整、置信度合法"""

    def setUp(self):
        self.db = load_db()
        self.cams = self.db.get('three_d_cameras') or []

    def test_table_exists_and_not_empty(self):
        self.assertGreaterEqual(len(self.cams), 8,
                                '3D 相机表至少覆盖 8 个主流型号，否则候选池不可信')

    def test_required_fields(self):
        required = ['brand', 'model', 'technology', 'working_distance_mm',
                    'fov_near', 'resolution', 'z_repeatability_mm',
                    'interface', 'verified', 'data_confidence']
        for c in self.cams:
            for k in required:
                self.assertIn(k, c, f"{c.get('model')} 缺字段 {k}")

    def test_verified_requires_url(self):
        for c in self.cams:
            if c.get('verified'):
                self.assertTrue(c.get('verification_url'),
                                f"{c['model']} verified=true 但没有官网链接")

    def test_confidence_enum(self):
        for c in self.cams:
            self.assertIn(c.get('data_confidence'), ('high', 'medium', 'low'),
                          f"{c['model']} data_confidence 非法")

    def test_low_confidence_must_have_confirmation_note(self):
        """低置信度条目必须写明要厂商确认什么，否则等于默认可信"""
        for c in self.cams:
            if c.get('data_confidence') == 'low':
                self.assertTrue(c.get('needs_vendor_confirmation'),
                                f"{c['model']} 标记 low 却没写待确认项")

    def test_wd_range_shape(self):
        for c in self.cams:
            rng = c.get('working_distance_mm')
            self.assertIsInstance(rng, list, f"{c['model']} WD 必须是 [min,max]")
            self.assertEqual(len(rng), 2)
            self.assertLess(rng[0], rng[1])

    def test_guidance_accuracy_only_vendor_values(self):
        """guidance_accuracy_mm 只能是厂商口径；有值必须带 scope 和出处"""
        for c in self.cams:
            g = c.get('guidance_accuracy_mm')
            if g is not None:
                self.assertEqual(c.get('guidance_accuracy_scope'), 'system',
                                 f"{c['model']} guidance 值必须标 scope=system")
                self.assertTrue(c.get('guidance_url'),
                                f"{c['model']} guidance 值必须给官方出处")


class TestFovMath(unittest.TestCase):
    """FOV 插值：两点线性、单点缩放、边界外推标记"""

    def _cam(self, near, far=None):
        c = {'fov_near': near}
        if far:
            c['fov_far'] = far
        return c

    def test_two_point_linear_midpoint(self):
        cam = self._cam(
            {'width': 400, 'height': 300, 'distance': 500},
            {'width': 800, 'height': 600, 'distance': 1000},
        )
        fov = tds.ThreeDCameraSelector.fov_at_wd(cam, 750)
        self.assertAlmostEqual(fov['width'], 600, places=1)
        self.assertAlmostEqual(fov['height'], 450, places=1)
        self.assertFalse(fov['estimated'])

    def test_two_point_clamps_outside_range(self):
        cam = self._cam(
            {'width': 400, 'height': 300, 'distance': 500},
            {'width': 800, 'height': 600, 'distance': 1000},
        )
        fov = tds.ThreeDCameraSelector.fov_at_wd(cam, 1200)
        self.assertAlmostEqual(fov['width'], 800, places=1)
        self.assertTrue(fov['estimated'], '超出范围必须标记 estimated')

    def test_single_point_scales_by_ratio(self):
        cam = self._cam({'width': 570, 'height': 460, 'distance': 600})
        fov = tds.ThreeDCameraSelector.fov_at_wd(cam, 300)
        self.assertAlmostEqual(fov['width'], 285, places=1)
        self.assertAlmostEqual(fov['height'], 230, places=1)
        self.assertTrue(fov['estimated'])


class TestErrorBudget(unittest.TestCase):
    """误差预算：设计目标 80%，RSS 可复现"""

    def test_design_target_is_80pct(self):
        b = tds.ThreeDCameraSelector.error_budget({}, 0.5)
        self.assertAlmostEqual(b['design_target_mm'], 0.4, places=4)
        self.assertAlmostEqual(b['total_rss_mm'], 0.4, places=3)

    def test_camera_budget_math(self):
        b = tds.ThreeDCameraSelector.error_budget({}, 0.5)
        others = b['others_rss_mm']
        expect = (0.4 ** 2 - others ** 2) ** 0.5
        self.assertAlmostEqual(b['camera_budget_mm'], round(expect, 4), places=3)

    def test_infeasible_when_others_exceed_target(self):
        """标定/机器人/夹爪/工件四项 RSS 已超设计目标 → 相机无预算"""
        params = {'calibration_error_mm': 0.3, 'robot_error_mm': 0.3,
                  'gripper_error_mm': 0.2, 'part_error_mm': 0.2}
        b = tds.ThreeDCameraSelector.error_budget(params, 0.5)
        self.assertTrue(b['budget_infeasible'])
        self.assertEqual(b['camera_budget_mm'], 0.0)

    def test_design_ratio_clamped(self):
        b = tds.ThreeDCameraSelector.error_budget({'design_margin_ratio': 0.1}, 0.5)
        self.assertGreaterEqual(b['design_margin_ratio'], 0.5)


class TestVendorGuidancePriority(unittest.TestCase):
    """厂商给 guidance 时直接用，不再叠加标定/机器人"""

    def test_vendor_guidance_used_directly(self):
        cam = {'model': 'X', 'guidance_accuracy_mm': 0.5,
               'guidance_accuracy_scope': 'system',
               'z_repeatability_mm': 0.05, 'vdi_accuracy_mm': 0.1}
        budget = tds.ThreeDCameraSelector.error_budget({}, 0.5)
        err = tds.ThreeDCameraSelector.camera_error(cam, 600, {}, budget)
        self.assertAlmostEqual(err['total_mm'], 0.5)
        self.assertEqual(err['scope'], 'system')
        self.assertIn('vendor_guidance', err['components'])

    def test_no_guidance_falls_back_to_rss(self):
        cam = {'model': 'X', 'z_repeatability_mm': 0.05, 'vdi_accuracy_mm': 0.1,
               'fov_near': {'width': 600, 'height': 400, 'distance': 600},
               'resolution': {'width': 1920, 'height': 1200}}
        budget = tds.ThreeDCameraSelector.error_budget({}, 0.5)
        err = tds.ThreeDCameraSelector.camera_error(cam, 600, {}, budget)
        self.assertLess(err['total_mm'], 0.5)
        self.assertIn('camera_measure', err['components'])
        self.assertIn('样件实测', err['note'])


class TestParamValidation(unittest.TestCase):
    """参数校验：缺关键字段必须 exit 2，不许自行补口径"""

    def test_missing_size_exit2(self):
        r = run_cli(['--precision', '0.5', '--output', vt_common.temp_dir()])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn('part_size', r.stdout)

    def test_missing_precision_exit2(self):
        r = run_cli(['--part-size', '300x300', '--output', vt_common.temp_dir()])
        self.assertEqual(r.returncode, 2)
        self.assertIn('precision_requirement', r.stdout)

    def test_missing_basis_exit2(self):
        """命令行默认给了 basis；config 模式不填必须被拦"""
        tmp = vt_common.temp_dir()
        cfg = os.path.join(tmp, 'c.json')
        with open(cfg, 'w', encoding='utf-8') as f:
            json.dump({'part_size': '300x300', 'precision_requirement': 0.5}, f)
        r = run_cli(['--config', cfg, '--output', tmp])
        self.assertEqual(r.returncode, 2)
        self.assertIn('精度口径', r.stdout)

    def test_bad_installation_exit2(self):
        tmp = vt_common.temp_dir()
        cfg = os.path.join(tmp, 'c.json')
        with open(cfg, 'w', encoding='utf-8') as f:
            json.dump({'part_size': '300x300', 'precision_requirement': 0.5,
                       'precision_basis': 'guidance_accuracy',
                       'installation': 'SIDE'}, f)
        r = run_cli(['--config', cfg, '--output', tmp])
        self.assertEqual(r.returncode, 2)


class TestEndToEnd(unittest.TestCase):
    """端到端：真实库 + 300x300/0.5mm 项目"""

    @classmethod
    def setUpClass(cls):
        cls.out = vt_common.temp_dir()
        cls.r = run_cli(['--part-size', '300x300', '--precision', '0.5',
                         '--precision-basis', 'guidance_accuracy',
                         '--cycle-time', '3', '--installation', 'ETH',
                         '--output', cls.out, '--top-n', '11'])
        cls.json_path = os.path.join(cls.out, 'three_d_selection.json')
        cls.md_path = os.path.join(cls.out, '3D视觉引导方案.md')
        cls.data = None
        if os.path.isfile(cls.json_path):
            with open(cls.json_path, encoding='utf-8') as f:
                cls.data = json.load(f)

    @classmethod
    def tearDownClass(cls):
        vt_common.rmtree(cls.out)

    def test_exit0_and_has_pass(self):
        self.assertEqual(self.r.returncode, 0, self.r.stdout + self.r.stderr)
        self.assertTrue(self.data['summary']['has_feasible'])

    def test_outputs_exist(self):
        self.assertTrue(os.path.isfile(self.json_path))
        self.assertTrue(os.path.isfile(self.md_path))

    def test_mech_mind_pro_m_fails(self):
        """厂商推荐的 PRO M 必须被判 FAIL（官方引导精度 1.5mm > 0.5mm）"""
        pro_m = [c for c in self.data['candidates'] if 'PRO M' in c['model']]
        self.assertTrue(pro_m, '库里必须有 PRO M 用于对比')
        self.assertEqual(pro_m[0]['verdict'], 'FAIL')
        self.assertGreater(pro_m[0]['guidance_error']['total_mm'], 0.5)

    def test_all_candidates_have_reasons_or_pass(self):
        for c in self.data['candidates']:
            if c['verdict'] == 'FAIL':
                self.assertTrue(c['reasons'], f"{c['model']} FAIL 但没写原因")

    def test_fov_meets_requirement_for_pass(self):
        req = self.data['requirements']
        need_w = req['part_size_mm']['width'] * req['fov_margin']
        need_h = req['part_size_mm']['height'] * req['fov_margin']
        for c in self.data['candidates']:
            if c['verdict'] == 'PASS':
                self.assertGreaterEqual(c['fov_at_wd_mm']['width'], need_w)
                self.assertGreaterEqual(c['fov_at_wd_mm']['height'], need_h)

    def test_markdown_has_budget_and_vendor_compare(self):
        with open(self.md_path, encoding='utf-8') as f:
            md = f.read()
        for kw in ('误差预算', '设计目标', 'RSS', 'PRO M', '底部不平整',
                   '换型', 'ETH'):
            self.assertIn(kw, md, f'方案缺章节关键词: {kw}')

    def test_json_has_budget_infeasible_flag(self):
        self.assertIn('budget_infeasible', self.data['error_budget'])


class TestRotationEnvelope(unittest.TestCase):
    """产品可能任意旋转时，FOV 必须按外接圆校核"""

    def test_rotate_requires_diagonal_fov(self):
        out = vt_common.temp_dir()
        try:
            r = run_cli(['--part-size', '300x300', '--precision', '0.5',
                         '--part-may-rotate', '--output', out, '--top-n', '11'])
            self.assertEqual(r.returncode, 0, r.stdout)
            with open(os.path.join(out, 'three_d_selection.json'), encoding='utf-8') as f:
                d = json.load(f)
            self.assertTrue(d['requirements']['part_may_rotate'])
            need = 300 * (2 ** 0.5) * d['requirements']['fov_margin']
            for c in d['candidates']:
                if c['verdict'] == 'PASS':
                    self.assertGreaterEqual(c['fov_at_wd_mm']['width'], need - 0.5)
                    self.assertGreaterEqual(c['fov_at_wd_mm']['height'], need - 0.5)
        finally:
            vt_common.rmtree(out)

    def test_rotate_makes_more_fail_than_fixed(self):
        """旋转包络更严，FAIL 数量不应减少"""
        out1 = vt_common.temp_dir()
        out2 = vt_common.temp_dir()
        try:
            run_cli(['--part-size', '300x300', '--precision', '0.5',
                     '--output', out1, '--top-n', '11'])
            run_cli(['--part-size', '300x300', '--precision', '0.5',
                     '--part-may-rotate', '--output', out2, '--top-n', '11'])
            with open(os.path.join(out1, 'three_d_selection.json'), encoding='utf-8') as f:
                d1 = json.load(f)
            with open(os.path.join(out2, 'three_d_selection.json'), encoding='utf-8') as f:
                d2 = json.load(f)
            self.assertGreaterEqual(d2['summary']['fail'], d1['summary']['fail'])
        finally:
            vt_common.rmtree(out1)
            vt_common.rmtree(out2)


class TestRecommendationRules(unittest.TestCase):
    """推荐规则：low 置信度不得当首选；工作点不早于最佳工作距离"""

    @classmethod
    def setUpClass(cls):
        cls.out = vt_common.temp_dir()
        run_cli(['--part-size', '300x300', '--precision', '0.5',
                 '--output', cls.out, '--top-n', '11'])
        with open(os.path.join(cls.out, 'three_d_selection.json'), encoding='utf-8') as f:
            cls.data = json.load(f)

    @classmethod
    def tearDownClass(cls):
        vt_common.rmtree(cls.out)

    def test_recommendation_not_low_confidence(self):
        rec = self.data.get('recommendation') or {}
        self.assertNotEqual(rec.get('data_confidence'), 'low',
                            'low 置信度型号不得作为推荐首选')

    def test_low_confidence_listed_separately(self):
        for c in self.data.get('low_confidence_candidates') or []:
            self.assertEqual(c.get('data_confidence'), 'low')

    def test_wd_not_before_optimal(self):
        """推荐工作距离不应早于相机最佳工作距离（厂家标称值在 optimal 测得）"""
        for c in self.data['candidates']:
            if c['verdict'] != 'PASS':
                continue
            wd = c.get('recommended_wd_mm')
            if wd is None:
                continue
            # 从库里取 optimal
            db = load_db()
            cam = next((x for x in db['three_d_cameras']
                        if x['model'] == c['model']), None)
            if not cam:
                continue
            opt = cam.get('optimal_working_distance_mm')
            lo = (cam.get('working_distance_mm') or [None])[0]
            if opt and lo and lo <= opt:
                self.assertGreaterEqual(
                    wd + 1.0, opt,
                    f"{c['model']} 推荐 WD {wd} 早于最佳 WD {opt}")


class TestCustomerProposal(unittest.TestCase):
    """--customer 生成客户交付版，必须含 BOM/标定/验收"""

    @classmethod
    def setUpClass(cls):
        cls.out = vt_common.temp_dir()
        cls.r = run_cli(['--part-size', '300x300', '--precision', '0.5',
                         '--customer', '--output', cls.out])

    @classmethod
    def tearDownClass(cls):
        vt_common.rmtree(cls.out)

    def test_file_generated(self):
        p = os.path.join(self.out, '3D视觉引导抓取系统技术方案_客户版.md')
        self.assertTrue(os.path.isfile(p))

    def test_required_sections(self):
        p = os.path.join(self.out, '3D视觉引导抓取系统技术方案_客户版.md')
        with open(p, encoding='utf-8') as f:
            md = f.read()
        for kw in ('系统配置清单', 'BOM', '手眼标定', '换型', '验收测试计划',
                   '风险清单', '待确认清单', 'PRO M'):
            self.assertIn(kw, md, f'客户版缺章节: {kw}')

    def test_cycle_time_assumption_labeled(self):
        """节拍为假设值时必须标注，不能写成客户提供"""
        out = vt_common.temp_dir()
        try:
            r = run_cli(['--part-size', '300x300', '--precision', '0.5',
                         '--cycle-time', '3', '--cycle-time-assumed',
                         '--customer', '--output', out])
            self.assertEqual(r.returncode, 0, r.stdout)
            p = os.path.join(out, '3D视觉引导抓取系统技术方案_客户版.md')
            with open(p, encoding='utf-8') as f:
                md = f.read()
            self.assertIn('假设值', md, '假设节拍必须显式标注')
            self.assertNotIn('| 节拍 | 3.0 s/件 | 客户提供 |', md,
                             '假设节拍不得标成客户提供')
        finally:
            vt_common.rmtree(out)

    def test_low_confidence_not_in_backups(self):
        """低置信度型号不得同时出现在备选方案里"""
        p = os.path.join(self.out, '3D视觉引导抓取系统技术方案_客户版.md')
        with open(p, encoding='utf-8') as f:
            md = f.read()
        if '### 3.2' not in md or '### 3.3' not in md:
            return
        backups = md.split('### 3.2')[1].split('### 3.3')[0]
        low_conf = md.split('### 3.3')[1].split('## 4')[0]
        for line in low_conf.splitlines():
            if not line.startswith('| ') or '型号' in line or '---' in line:
                continue
            model = line.split('|')[1].strip()
            self.assertNotIn(model, backups,
                             f'{model} 是低置信度候选，不得同时列为备选')


class TestInjection(unittest.TestCase):
    """注入：极端需求下结论必须翻转，不能永远推荐同一台"""

    def test_huge_part_all_fail(self):
        out = vt_common.temp_dir()
        try:
            r = run_cli(['--part-size', '3000x3000', '--precision', '0.5',
                         '--output', out])
            self.assertEqual(r.returncode, 1, r.stdout)
        finally:
            vt_common.rmtree(out)

    def test_loose_precision_more_pass(self):
        """精度放宽到 2mm，PASS 数量必须不少于 0.5mm 时"""
        out1 = vt_common.temp_dir()
        out2 = vt_common.temp_dir()
        try:
            r1 = run_cli(['--part-size', '300x300', '--precision', '0.5',
                          '--output', out1, '--top-n', '11'])
            r2 = run_cli(['--part-size', '300x300', '--precision', '2.0',
                          '--output', out2, '--top-n', '11'])
            with open(os.path.join(out1, 'three_d_selection.json'), encoding='utf-8') as f:
                d1 = json.load(f)
            with open(os.path.join(out2, 'three_d_selection.json'), encoding='utf-8') as f:
                d2 = json.load(f)
            self.assertGreaterEqual(d2['summary']['pass'], d1['summary']['pass'])
            self.assertEqual(r1.returncode, 0)
            self.assertEqual(r2.returncode, 0)
        finally:
            vt_common.rmtree(out1)
            vt_common.rmtree(out2)


class TestDefaultOutputDir(unittest.TestCase):
    """默认输出目录 = 项目名（目录名与 PPT 名一致），不再固定 ./output。

    背景：方案目录固定叫 output 时，多个项目产物互相覆盖，用户也分不清
    哪个目录对应哪份 PPT。约定改动后必须锁死，防止回退。
    """

    def test_default_dir_named_after_project(self):
        tmp = vt_common.temp_dir('vt_3dout_')
        try:
            proj = os.path.join(tmp, 'proj')
            elsewhere = os.path.join(tmp, 'elsewhere')
            os.makedirs(proj)
            os.makedirs(elsewhere)
            cfg = os.path.join(proj, 'c.json')
            with open(cfg, 'w', encoding='utf-8') as f:
                json.dump({'project_name': '三D默认输出测试',
                           'part_size': '300x300',
                           'precision_requirement': 0.5,
                           'precision_basis': 'guidance_accuracy',
                           'cycle_time': 3,
                           'installation': 'ETH'}, f, ensure_ascii=False)
            # 不传 --output，且 cwd 故意不在 config 目录：默认应建在 config 目录下
            r = run_cli(['--config', cfg, '--no-markdown'], cwd=elsewhere)
            self.assertEqual(r.returncode, 0, (r.stdout or '') + (r.stderr or ''))
            expected = os.path.join(proj, '三D默认输出测试')
            self.assertTrue(os.path.isdir(expected),
                            f'默认目录应为「config 目录/项目名」: {expected}\n{r.stdout[-800:]}')
            self.assertTrue(
                os.path.isfile(os.path.join(expected, 'three_d_selection.json')),
                '选型 JSON 必须落在项目名目录内')
            self.assertFalse(os.path.isdir(os.path.join(elsewhere, '三D默认输出测试')),
                             '产物不得落到调用时的 cwd（AI 从任意目录调用很常见）')
            self.assertFalse(os.path.isdir(os.path.join(tmp, 'output')),
                             '不得再生成固定的 output 目录')
        finally:
            vt_common.rmtree(tmp)

    def test_safe_name_strips_illegal_chars(self):
        """项目名里的 Windows 非法字符必须清掉，空名回落到默认目录名"""
        self.assertEqual(tds._safe_name('A/B:C*D?E'), 'ABCDE')
        self.assertEqual(tds._safe_name('   '), '3D视觉引导抓取方案')
        self.assertEqual(tds._safe_name(None), '3D视觉引导抓取方案')
        # 中文括号/乘号/逗号是合法字符，不能被误删
        self.assertEqual(tds._safe_name('方案（300×300，ETH）'), '方案（300×300，ETH）')


if __name__ == '__main__':
    unittest.main(verbosity=2)
