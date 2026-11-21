# -*- coding: utf-8 -*-
"""L0 数据完整性层：硬件库是选型的唯一事实来源，必须可核验、无假型号。

用途：扩库/fetch/refresh 之后先跑这一层，防止"编造型号或不完整条目"
悄悄进库并流进交付物。纯离线，秒级。
运行：python run_all.py --layer data
"""
import json
import os
import unittest

import vt_common

DB_PATH = os.path.join(vt_common.SKILL_DIR, 'config', 'hardware_database.json')

# 历史假型号/错误命名（官网查无此型号，禁止以任何形式回流）
FAKE_MODELS = [
    'RL-150-120-W', 'RL-100-90-W', 'ZF-150W', 'ZF-300W',
    'LFV-300X10', 'OPT-RI15030-W',
]

CAMERA_REQUIRED = ('brand', 'model', 'resolution', 'pixel_size',
                   'sensor_size', 'lens_mount', 'verified')
LENS_REQUIRED = ('brand', 'model', 'magnification', 'mount',
                 'working_distance', 'verified')
LIGHT_REQUIRED = ('brand', 'model', 'type', 'verified')


def missing_fields(item, required):
    """字段必须存在；除 verified（允许 False）外还必须有值"""
    return [k for k in required
            if k not in item or (k != 'verified' and not item.get(k))]


def load_db():
    with open(DB_PATH, encoding='utf-8') as f:
        return json.load(f)


class TestDatabaseSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = load_db()

    def test_camera_required_fields(self):
        for item in self.db['cameras']:
            missing = missing_fields(item, CAMERA_REQUIRED)
            self.assertEqual(missing, [],
                             f"相机 {item.get('model')} 缺字段 {missing}")

    def test_lens_required_fields(self):
        for item in self.db['lenses']:
            missing = missing_fields(item, LENS_REQUIRED)
            self.assertEqual(missing, [],
                             f"镜头 {item.get('model')} 缺字段 {missing}")

    def test_light_required_fields(self):
        for item in self.db['light_sources']:
            missing = missing_fields(item, LIGHT_REQUIRED)
            self.assertEqual(missing, [],
                             f"光源 {item.get('model')} 缺字段 {missing}")

    def test_models_unique(self):
        for key in ('cameras', 'lenses', 'light_sources'):
            models = [i.get('model') for i in self.db[key]]
            dup = {m for m in models if models.count(m) > 1}
            self.assertEqual(dup, set(), f'{key} 存在重复型号: {dup}')

    def test_no_fake_models(self):
        """假型号绝不能通过扩库回流（2026-11-20 事故）"""
        for key in ('cameras', 'lenses', 'light_sources'):
            for item in self.db[key]:
                model = str(item.get('model') or '')
                for fake in FAKE_MODELS:
                    self.assertNotIn(fake, model,
                                     f'{key} 出现历史假型号 {fake}: {model}')


class TestLensWorkingDistanceSchema(unittest.TestCase):
    """2026-11-20 事故：WD 从未参与选型，MOD=500mm 的镜头在 WD=300mm 项目里
    仅凭倍率中选。镜头必须显式声明 mod/wd_range（值可为 null，键必须存在），
    否则"未核验"会伪装成"可用"。"""

    @classmethod
    def setUpClass(cls):
        cls.db = load_db()

    def test_wd_fields_present(self):
        for item in self.db['lenses']:
            for key in ('mod', 'wd_range', 'distortion'):
                self.assertIn(key, item,
                              f"镜头 {item.get('model')} 缺 {key} 键"
                              f"（未知也要显式 null，不能省略）")

    def test_wd_range_shape(self):
        for item in self.db['lenses']:
            r = item.get('wd_range')
            if r is None:
                continue
            self.assertIsInstance(r, list, f"{item.get('model')} wd_range 必须是数组")
            self.assertEqual(len(r), 2, f"{item.get('model')} wd_range 必须是 [min,max]")
            lo, hi = r
            if lo is not None and hi is not None:
                self.assertLessEqual(lo, hi,
                                     f"{item.get('model')} wd_range 下限大于上限")

    def test_mod_matches_range_floor(self):
        for item in self.db['lenses']:
            mod, r = item.get('mod'), item.get('wd_range')
            if mod and r and r[0] is not None:
                self.assertAlmostEqual(
                    mod, r[0], delta=1.0,
                    msg=f"{item.get('model')} mod={mod} 与 wd_range 下限 {r[0]} 不一致")

    def test_wd_mag_table_shape(self):
        """厂家 WD-倍率表必须是 [wd, mag] 数组，且附来源说明"""
        for item in self.db['lenses']:
            table = item.get('wd_mag_table')
            if table is None:
                continue
            self.assertIsInstance(table, list, f"{item.get('model')} 表格式错误")
            self.assertGreaterEqual(len(table), 1)
            for row in table:
                self.assertEqual(len(row), 2,
                                 f"{item.get('model')} 表行必须是 [wd, mag]")
                wd, mag = row
                self.assertGreater(wd, 0, f"{item.get('model')} WD 必须>0")
                self.assertGreater(mag, 0, f"{item.get('model')} 倍率必须>0")
            self.assertTrue(item.get('wd_mag_table_basis'),
                            f"{item.get('model')} 有倍率表但没写来源")

    def test_external_candidates_documented(self):
        """库外查过的型号必须留档，避免"库里没有"被当成没查过"""
        items = self.db.get('external_candidates', [])
        self.assertTrue(items, 'external_candidates 为空：库外核查结果必须留档')
        for item in items:
            for key in ('model', 'mod', 'verdict', 'reason', 'verification_url'):
                self.assertIn(key, item, f"库外记录 {item.get('model')} 缺 {key}")
            self.assertIn(item['verdict'], ('rejected', 'usable', 'usable_with_risk'),
                          f"{item.get('model')} verdict 取值非法")



    @classmethod
    def setUpClass(cls):
        cls.db = load_db()

    def test_verified_requires_url(self):
        """verified=true 必须有官网链接，否则"可查证"是空话"""
        for key in ('cameras', 'lenses', 'light_sources'):
            for item in self.db[key]:
                if not item.get('verified'):
                    continue
                url = str(item.get('verification_url') or '')
                self.assertTrue(url.startswith('http'),
                                f"{key} {item.get('model')} verified=true 但无官网链接")

    def test_unverified_has_note(self):
        """未核验条目必须写明缺什么，禁止留空让人猜"""
        for key in ('cameras', 'lenses', 'light_sources'):
            for item in self.db[key]:
                if item.get('verified'):
                    continue
                note = str(item.get('note') or '') + str(item.get('history') or '')
                self.assertTrue(note.strip(),
                                f"{key} {item.get('model')} verified=false 但无 note 说明")

    def test_light_angle_valid(self):
        """环光角度必须是 0~90 的数值，高/低角度分档才可信"""
        for item in self.db['light_sources']:
            angle = item.get('angle')
            if angle is None:
                continue
            self.assertIsInstance(angle, (int, float),
                                  f"光源 {item.get('model')} angle 非数值: {angle}")
            self.assertGreaterEqual(angle, 0)
            self.assertLessEqual(angle, 90)

    def test_light_numeric_ranges(self):
        for item in self.db['light_sources']:
            for field, lo, hi in (('inner_diameter', 1, 2000),
                                  ('outer_diameter', 1, 2000),
                                  ('power_w', 0.1, 5000)):
                val = item.get(field)
                if val is None:
                    continue
                self.assertIsInstance(val, (int, float),
                                      f"{item.get('model')}.{field} 非数值")
                self.assertGreaterEqual(val, lo,
                                        f"{item.get('model')}.{field} 越界: {val}")
                self.assertLessEqual(val, hi,
                                     f"{item.get('model')}.{field} 越界: {val}")

    def test_brand_priority_brands_exist(self):
        """默认品牌优先级里至少要有真实条目，否则降级链是空的"""
        # 与 vision_proposal_generator._recommend_light_source 的默认值对齐；
        # 改默认优先级时这里会提醒同步（契约测试）
        default_brands = ['追光者', '孚根', 'OPT', 'CCS']
        brands = {i.get('brand') for i in self.db['light_sources']}
        hit = [b for b in default_brands if b in brands]
        self.assertTrue(hit, f'默认优先级 {default_brands} 与库内品牌 {brands} 无交集')


class TestConfigTemplatePrecisionModel(unittest.TestCase):
    """2026-11-21：模板若预填 precision_model，用户照抄就会跳过'口径确认'。

    precision_model 一旦非 null，resolve_precision_budget 会认为口径已声明
    （is_assumption=False），核验不再出 WARN，未与客户确认的分配比例
    就会静默进交付物。模板必须留 null，强制用户显式声明。
    """

    TEMPLATE = os.path.join(vt_common.SKILL_DIR, 'config', '..',
                            'config_template.json')

    def test_template_exists_and_parses(self):
        with open(self.TEMPLATE, encoding='utf-8') as f:
            data = json.load(f)
        self.assertIsNone(
            data.get('precision_model'),
            'config_template.json 的 precision_model 必须是 null，'
            '否则用户照抄会绕过口径确认 WARN')
        self.assertIsNone(data.get('tolerance'))
        self.assertIsNone(data.get('precision_requirement'))
        self.assertIn('_字段1b_精度模型_两套口径不可叠加', data,
                      '模板必须保留口径说明字段')

    def test_template_copied_with_tolerance_still_warns(self):
        """模板原样拷走 + 只填 tolerance 时，口径仍应被标记为假设。"""
        from precision_calculator import resolve_precision_budget
        with open(self.TEMPLATE, encoding='utf-8') as f:
            params = json.load(f)
        params['tolerance'] = 0.5
        budget = resolve_precision_budget(params)
        self.assertIsNotNone(budget)
        self.assertTrue(budget['is_assumption'],
                        '模板未声明 precision_model 时必须 is_assumption=True')


if __name__ == '__main__':
    unittest.main()
