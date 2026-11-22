# -*- coding: utf-8 -*-
"""L2 工作流契约：一条命令的退出码/产物/幂等性必须稳定。

这是"改完代码有没有把主流程改坏"的核心回归层：
  0 = 成功（PPT 在 output 根目录且 FAIL=0）
  1 = 未生成/未通过验收（不得交付）
  2 = 缺字段/口径需用户拍板（不得自行补）
运行：python run_all.py --layer workflow
"""
import glob
import json
import os
import subprocess
import sys
import unittest

import vt_common

GEN = os.path.join(vt_common.TOOLS_DIR, 'vision_proposal_generator.py')

BASE = {'project_name': '工作流契约', 'precision_requirement': 0.03,
        'cycle_time': 3, 'detection_area': '38.5x22'}


def write_cfg(path, extra=None):
    data = dict(BASE)
    data.update(extra or {})
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def run_gen(cfg, out, extra_args=None):
    cmd = [sys.executable, GEN, '--config', cfg, '--output', out, '--auto']
    cmd += list(extra_args or [])
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=300)


class TestExitCodes(unittest.TestCase):
    def test_no_template_selection_only_exit0(self):
        """无模板：只输出选型结果，exit 0，不得产假 PPT"""
        tmp = vt_common.temp_dir('vt_wf1_')
        try:
            cfg = os.path.join(tmp, 'project_config.json')
            out = os.path.join(tmp, 'output')
            write_cfg(cfg)
            p = run_gen(cfg, out)
            log = (p.stdout or '') + (p.stderr or '')
            self.assertEqual(p.returncode, 0, log[-800:])
            self.assertTrue(os.path.exists(
                os.path.join(out, 'selection_result.json')),
                '无模板时选型结果必须落盘')
            self.assertFalse(glob.glob(os.path.join(out, '*.pptx')),
                             '无模板不得产出 PPT')
        finally:
            vt_common.rmtree(tmp)

    def test_missing_precision_exit2_no_output(self):
        """缺精度口径：exit 2 + 可执行指引，不产任何交付物"""
        tmp = vt_common.temp_dir('vt_wf2_')
        try:
            cfg = os.path.join(tmp, 'project_config.json')
            out = os.path.join(tmp, 'output')
            with open(cfg, 'w', encoding='utf-8') as f:
                json.dump({'project_name': '缺精度', 'cycle_time': 3,
                           'detection_area': '38.5x22'}, f, ensure_ascii=False)
            p = run_gen(cfg, out)
            log = (p.stdout or '') + (p.stderr or '')
            self.assertEqual(p.returncode, 2, log[-800:])
            self.assertIn('缺少精度口径', log)
            self.assertFalse(os.path.exists(
                os.path.join(out, 'selection_result.json')),
                'exit 2 不得留下半成品')
        finally:
            vt_common.rmtree(tmp)

    def test_suspect_precision_exit2(self):
        """精度口径偏大（疑似公差）：硬阻断，禁止继续交付低配方案"""
        tmp = vt_common.temp_dir('vt_wf3_')
        try:
            cfg = os.path.join(tmp, 'project_config.json')
            out = os.path.join(tmp, 'output')
            write_cfg(cfg, {'precision_requirement': 0.5,
                            'detection_type': '定位引导'})
            p = run_gen(cfg, out)
            log = (p.stdout or '') + (p.stderr or '')
            self.assertEqual(p.returncode, 2, log[-800:])
            self.assertIn('口径复核', log)
            self.assertIn('measurement_accuracy', log)
        finally:
            vt_common.rmtree(tmp)

    def test_measurement_accuracy_exit0(self):
        """客户明确说"测量精度0.5mm" → basis=measurement_accuracy 直接放行"""
        tmp = vt_common.temp_dir('vt_wf4b_')
        try:
            cfg = os.path.join(tmp, 'project_config.json')
            out = os.path.join(tmp, 'output')
            write_cfg(cfg, {'precision_requirement': 0.5,
                            'precision_basis': 'measurement_accuracy',
                            'detection_type': '定位引导'})
            p = run_gen(cfg, out)
            self.assertEqual(p.returncode, 0,
                             ((p.stdout or '') + (p.stderr or ''))[-800:])
        finally:
            vt_common.rmtree(tmp)

    def test_confirmed_precision_exit0(self):
        """用户拍板非公差后，确认字段放行"""
        tmp = vt_common.temp_dir('vt_wf4_')
        try:
            cfg = os.path.join(tmp, 'project_config.json')
            out = os.path.join(tmp, 'output')
            write_cfg(cfg, {'precision_requirement': 0.5,
                            'detection_type': '定位引导',
                            'precision_basis_confirmed': True})
            p = run_gen(cfg, out)
            self.assertEqual(p.returncode, 0,
                             ((p.stdout or '') + (p.stderr or ''))[-800:])
        finally:
            vt_common.rmtree(tmp)


class TestArtifacts(unittest.TestCase):
    def test_selection_result_schema(self):
        tmp = vt_common.temp_dir('vt_wf5_')
        try:
            cfg = os.path.join(tmp, 'project_config.json')
            out = os.path.join(tmp, 'output')
            write_cfg(cfg)
            p = run_gen(cfg, out)
            self.assertEqual(p.returncode, 0)
            with open(os.path.join(out, 'selection_result.json'),
                      encoding='utf-8') as f:
                r = json.load(f)
            for key in ('project_info', 'hardware_selection', 'validation',
                        'validation_passed'):
                self.assertIn(key, r, f'选型结果缺 {key}')
            hw = r['hardware_selection']
            for key in ('camera', 'lens', 'light_source'):
                self.assertIn(key, hw, f'hardware_selection 缺 {key}')
            self.assertTrue(hw['camera'].get('model'), '相机型号为空')
            self.assertTrue(hw['lens'].get('model'), '镜头型号为空')
            self.assertIsInstance(r['validation_passed'], bool)
        finally:
            vt_common.rmtree(tmp)

    def test_rerun_keeps_single_ppt(self):
        """连跑两次：旧版本自动清理，根目录只能有一个可交付 PPT"""
        from test_ppt_pipeline import write_template
        tmp = vt_common.temp_dir('vt_wf6_')
        try:
            cfg = os.path.join(tmp, 'project_config.json')
            tpl = os.path.join(tmp, 'template.pptx')
            out = os.path.join(tmp, 'output')
            write_cfg(cfg)
            write_template(tpl)
            for i in range(2):
                p = run_gen(cfg, out, ['--template', tpl])
                log = (p.stdout or '') + (p.stderr or '')
                self.assertEqual(p.returncode, 0, f'第{i + 1}次失败\n{log[-800:]}')
            ppt = glob.glob(os.path.join(out, '*.pptx'))
            self.assertEqual(len(ppt), 1,
                             f'重复运行后应只剩1个PPT，实际 {len(ppt)}')
        finally:
            vt_common.rmtree(tmp)

    def test_no_verify_warns(self):
        """--no_verify 仅人工排障：产物保留但必须打印"不得作为交付依据\""""
        from test_ppt_pipeline import write_template
        tmp = vt_common.temp_dir('vt_wf7_')
        try:
            cfg = os.path.join(tmp, 'project_config.json')
            tpl = os.path.join(tmp, 'template.pptx')
            out = os.path.join(tmp, 'output')
            write_cfg(cfg)
            write_template(tpl)
            p = run_gen(cfg, out, ['--template', tpl, '--no_verify'])
            log = (p.stdout or '') + (p.stderr or '')
            self.assertEqual(p.returncode, 0, log[-800:])
            self.assertIn('不得作为交付依据', log)
            self.assertEqual(len(glob.glob(os.path.join(out, '*.pptx'))), 1)
        finally:
            vt_common.rmtree(tmp)


if __name__ == '__main__':
    unittest.main()
