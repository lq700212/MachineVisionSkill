# -*- coding: utf-8 -*-
"""L0 文档契约层：防止"文档说的和代码做的不一致"。

弱模型完全照 SKILL.md 执行——文档漂移（写了不存在的脚本/参数/字段）
会直接把弱模型带进沟里。纯离线，秒级。
运行：python run_all.py --layer doc
"""
import glob
import json
import os
import re
import unittest

import vt_common

SKILL_MD = os.path.join(vt_common.SKILL_DIR, 'SKILL.md')
README = os.path.join(vt_common.SKILL_DIR, 'README.md')
CHANGELOG = os.path.join(vt_common.SKILL_DIR, 'CHANGELOG.md')
TEMPLATE = os.path.join(vt_common.SKILL_DIR, 'config_template.json')
GEN = os.path.join(vt_common.TOOLS_DIR, 'vision_proposal_generator.py')


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def tool_sources():
    out = {}
    for p in glob.glob(os.path.join(vt_common.TOOLS_DIR, '*.py')):
        out[os.path.basename(p)] = read(p)
    return out


class TestDocReferences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = read(SKILL_MD)
        cls.readme = read(README) if os.path.exists(README) else ''
        cls.changelog = read(CHANGELOG)

    def test_referenced_tools_exist(self):
        """SKILL.md/README 里写的 tools/xxx.py 必须真实存在"""
        refs = set(re.findall(r'tools[/\\]([A-Za-z_0-9]+\.py)', self.skill))
        refs |= set(re.findall(r'tools[/\\]([A-Za-z_0-9]+\.py)', self.readme))
        missing = [r for r in refs
                   if not os.path.exists(os.path.join(vt_common.TOOLS_DIR, r))]
        self.assertEqual(missing, [], f'文档引用了不存在的脚本: {missing}')

    def test_core_cli_args_exist(self):
        """最短路径用到的参数必须都在 argparse 里（否则弱模型照抄即报错）"""
        gen_src = read(GEN)
        declared = set(re.findall(r"add_argument\(\s*['\"](--[a-z_]+)['\"]",
                                  gen_src))
        core = {'--config', '--text', '--files', '--template', '--output',
                '--auto', '--hardware_page', '--no_verify', '--wizard'}
        missing = core - declared
        self.assertEqual(missing, set(), f'generator 缺参数定义: {missing}')
        # 文档里出现的核心参数必须都在声明集合里
        doc_args = set(re.findall(r'--[a-z_]+', self.skill)) & core
        self.assertEqual(doc_args - declared, set(),
                         f'文档提到但未声明的参数: {doc_args - declared}')

    def test_red_lines_present(self):
        """红线（禁止手改PPT/拼造光源/自行确认口径）必须写在 SKILL.md"""
        for phrase in ('禁止拼造光源型号', '禁止用代码手改 PPT',
                       'precision_basis_confirmed', '_rejected'):
            self.assertIn(phrase, self.skill, f'SKILL.md 缺红线: {phrase}')

    def test_shortest_path_has_exit_codes(self):
        """弱模型靠退出码判断，0/1/2 三态必须写清楚"""
        for code in ('| `0` |', '| `1` |', '| `2` |'):
            self.assertIn(code, self.skill, f'最短路径缺退出码 {code}')

    def test_changelog_has_version_entry(self):
        self.assertTrue(re.search(r'^## \[', self.changelog, re.MULTILINE),
                        'CHANGELOG 顶部缺版本条目')

    def test_readme_points_to_runner(self):
        if not self.readme:
            self.skipTest('README 不存在')
        self.assertIn('run_all.py', self.readme,
                      'README 未指向统一测试入口')


class TestConfigTemplateContract(unittest.TestCase):
    """config_template 的字段必须真被代码消费，避免"填了也没用\""""

    def test_template_keys_consumed(self):
        with open(TEMPLATE, encoding='utf-8') as f:
            cfg = json.load(f)
        sources = '\n'.join(tool_sources().values())
        unused = []
        for key in cfg:
            if key.startswith('_'):
                continue
            if key not in sources:
                unused.append(key)
        self.assertEqual(unused, [], f'模板字段代码里从未读取: {unused}')

    def test_template_has_light_fields(self):
        with open(TEMPLATE, encoding='utf-8') as f:
            cfg = json.load(f)
        for key in ('light_brand_priority', 'light_angle',
                    'precision_basis_confirmed'):
            self.assertIn(key, cfg, f'模板缺光源/口径字段 {key}')


if __name__ == '__main__':
    unittest.main()
