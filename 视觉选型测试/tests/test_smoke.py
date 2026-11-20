# -*- coding: utf-8 -*-
"""L0 冒烟层（秒级）：skill 目录/依赖/关键文件是否完整。

用途：改完任何代码先跑这一层，10 秒内确认"没有把 skill 改瘸"；
失败说明是结构性问题（文件丢失、语法错误、JSON 损坏），不必等全量。
运行：python run_all.py --layer smoke
"""
import importlib
import json
import os
import unittest

import vt_common

REQUIRED_FILES = [
    'SKILL.md',
    'AGENTS.md',
    'CHANGELOG.md',
    'config_template.json',
    'config/hardware_database.json',
    'tools/vision_proposal_generator.py',
    'tools/generate_ppt.py',
    'tools/check_ppt_quality.py',
    'tools/validate_selection.py',
    'tools/light_selector.py',
    'tools/camera_selector.py',
    'tools/lens_selector.py',
    'tools/precision_calculator.py',
    'tools/parse_user_data.py',
]

CORE_MODULES = [
    'vision_proposal_generator',
    'generate_ppt',
    'check_ppt_quality',
    'validate_selection',
    'light_selector',
    'camera_selector',
    'lens_selector',
    'precision_calculator',
    'parse_user_data',
]


class TestSkillLayout(unittest.TestCase):
    """被测 skill 的交付结构必须完整"""

    def test_required_files_exist(self):
        missing = [r for r in REQUIRED_FILES
                   if not os.path.exists(os.path.join(vt_common.SKILL_DIR, r))]
        self.assertEqual(missing, [], f'缺少关键文件: {missing}')

    def test_core_modules_importable(self):
        """语法错误/循环依赖/缺第三方包会在这里立刻暴露"""
        for name in CORE_MODULES:
            with self.subTest(module=name):
                importlib.import_module(name)

    def test_no_stray_scripts_in_skill_root(self):
        """skill 根目录不得混入临时调试脚本（历史事故：手写 build_ppt.py）"""
        stray = []
        for f in os.listdir(vt_common.SKILL_DIR):
            if not f.endswith('.py'):
                continue
            if f.startswith(('check_', 'tmp_', 'temp_', 'debug_', 'test_', 'build_')):
                stray.append(f)
        self.assertEqual(stray, [], f'skill 根目录出现临时脚本: {stray}')


class TestConfigAssets(unittest.TestCase):
    """配置资产必须可解析且字段齐全"""

    def test_hardware_database_parseable(self):
        path = os.path.join(vt_common.SKILL_DIR, 'config',
                            'hardware_database.json')
        with open(path, encoding='utf-8') as f:
            db = json.load(f)
        for key in ('cameras', 'lenses', 'light_sources'):
            self.assertIn(key, db, f'硬件库缺少 {key}')
            self.assertIsInstance(db[key], list, f'{key} 必须是列表')
        self.assertTrue(db['cameras'], '相机库为空')
        self.assertTrue(db['lenses'], '镜头库为空')

    def test_config_template_parseable(self):
        path = os.path.join(vt_common.SKILL_DIR, 'config_template.json')
        with open(path, encoding='utf-8') as f:
            cfg = json.load(f)
        # 模板值必须为 null/空，禁止把示例值当默认值（弱模型会直接复制）
        for key in ('project_name', 'precision_requirement', 'tolerance',
                    'cycle_time', 'detection_area'):
            self.assertIn(key, cfg, f'模板缺少字段 {key}')
            self.assertIsNone(cfg[key], f'模板字段 {key} 必须为 null')

    def test_skill_frontmatter(self):
        path = os.path.join(vt_common.SKILL_DIR, 'SKILL.md')
        with open(path, encoding='utf-8') as f:
            head = f.read(600)
        self.assertTrue(head.startswith('---'), 'SKILL.md 缺 frontmatter')
        self.assertIn('name:', head, 'frontmatter 缺 name')
        self.assertIn('description:', head, 'frontmatter 缺 description')
        # 加载器硬校验：name 必须是 ASCII slug
        for line in head.splitlines():
            if line.startswith('name:'):
                name = line.split(':', 1)[1].strip().strip('"\'')
                self.assertRegex(name, r'^[a-z0-9]+(-[a-z0-9]+)*$',
                                 f'name 不是合法 slug: {name}')


if __name__ == '__main__':
    unittest.main()
