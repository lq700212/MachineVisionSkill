# -*- coding: utf-8 -*-
"""端到端重用例：工作区config→选型→核验→PPT→验收FAIL=0
（输出到临时目录，不污染工作区output/；--fast 模式下被runner剔除）"""
import glob
import os
import subprocess
import sys
import unittest

import vt_common

GENERATOR = os.path.join(vt_common.TOOLS_DIR, 'vision_proposal_generator.py')


@unittest.skipUnless(vt_common.workspace_ready(),
                     '工作区缺project_config.json或模板PPT，端到端用例跳过')
class TestPptPipeline(unittest.TestCase):

    def test_config_to_ppt_fail0(self):
        """回归: config一条命令到PPT，验收FAIL=0（可交付标准）"""
        out = vt_common.temp_dir('vt_ppt_')
        cmd = [sys.executable, GENERATOR,
               '--config', os.path.join(vt_common.WORKSPACE, 'project_config.json'),
               '--output', out, '--auto']
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=300)
        combined = (p.stdout or '') + (p.stderr or '')
        self.assertEqual(p.returncode, 0,
                         f'主流程退出码{p.returncode}\n{combined[-1500:]}')
        pptx = glob.glob(os.path.join(out, '*.pptx'))
        self.assertTrue(pptx, f'未产出PPT\n{combined[-800:]}')
        report = os.path.join(out, 'acceptance_report.txt')
        self.assertTrue(os.path.exists(report), '验收报告未生成')
        content = open(report, encoding='utf-8', errors='replace').read()
        self.assertRegex(content, r'FAIL=0',
                         msg='PPT规则自查存在FAIL，不可交付')
        vt_common.rmtree(out)

    def test_relative_output_acceptance_still_fails0(self):
        """回归: 相对 --output 时验收不得静默失效（2026-08-31事故：
        验收子进程 cwd=tools_dir，相对路径被 abspath 错位到 tools\\output，
        验收查错文件仍打印完成——交付失检。修复后路径在入口归一为绝对）"""
        rel_out = 'vt_rel_out_tmp'
        out_abs = os.path.join(vt_common.WORKSPACE, rel_out)
        cmd = [sys.executable, GENERATOR,
               '--config', os.path.join(vt_common.WORKSPACE, 'project_config.json'),
               '--output', rel_out, '--auto']
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=300,
                           cwd=vt_common.WORKSPACE)
        combined = (p.stdout or '') + (p.stderr or '')
        self.assertEqual(p.returncode, 0,
                         f'主流程退出码{p.returncode}\n{combined[-1500:]}')
        report = os.path.join(out_abs, 'acceptance_report.txt')
        self.assertTrue(os.path.exists(report),
                        f'相对--output时验收报告未生成（验收可能错位失效）\n{combined[-800:]}')
        content = open(report, encoding='utf-8', errors='replace').read()
        self.assertRegex(content, r'FAIL=0',
                         msg='相对--output下PPT自查存在FAIL，不可交付')
        vt_common.rmtree(out_abs)


if __name__ == '__main__':
    unittest.main()
