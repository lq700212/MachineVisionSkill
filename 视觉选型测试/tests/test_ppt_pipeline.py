# -*- coding: utf-8 -*-
"""端到端重用例：config→选型→核验→PPT→验收FAIL=0
（config 与模板均在临时目录现场合成，不依赖用户工作区、不污染任何真实数据；
2026-09-03 前本文件依赖工作区 project_config.json+模板缺失即整类跳过，
改写为自包含后任何环境都实跑）"""
import glob
import json
import os
import subprocess
import sys
import unittest

import vt_common

GENERATOR = os.path.join(vt_common.TOOLS_DIR, 'vision_proposal_generator.py')

# 标准口径：此前 --text 实跑 FAIL=0 的组合（精度0.03/节拍3s/检测区域38.5x22）
CONFIG = {
    'project_name': '自包含端到端',
    'precision_requirement': 0.03,
    'cycle_time': 3,
    'detection_area': '38.5x22',
}


def write_config(path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(CONFIG, f, ensure_ascii=False)


def write_template(path):
    """合成最小硬件模板：一页硬件选型页，含表格4行+描述3行+WD标注2个。
    文本刻意避开 STALE_TOKENS（旧型号残留检查的一切触发词），
    文本框给足宽度并显式字号（溢出预检不误报），无图片（C7仅WARN可接受）。"""
    from pptx import Presentation
    from pptx.util import Mm, Pt
    prs = Presentation()
    prs.slide_width, prs.slide_height = Mm(254), Mm(142)
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # 空白版式

    def add_text(left, top, width, height, text, size=14):
        box = slide.shapes.add_textbox(Mm(left), Mm(top), Mm(width), Mm(height))
        box.text_frame.word_wrap = True
        p = box.text_frame.paragraphs[0]
        p.text = text
        p.runs[0].font.size = Pt(size)
        return box

    add_text(10, 5, 200, 12, '硬件选型', size=20)
    # 表格：行首列标题命中替换规则，值列给占位（会被实际值替换）
    tbl_shape = slide.shapes.add_table(4, 2, Mm(10), Mm(20), Mm(200), Mm(60))
    rows = [('相机工作距离', '110mm'), ('相机视野', '50mm×40mm'),
            ('相机精度', '0.01mm/pixel'), ('光源工作距离', '80mm')]
    for i, (h, v) in enumerate(rows):
        for j, t in enumerate((h, v)):
            cell = tbl_shape.table.cell(i, j)
            cell.text = t
            for p in cell.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(12)
    add_text(10, 85, 200, 12, '使用500万像素相机，分辨率为2448 × 2048')
    add_text(10, 99, 200, 12, '镜头： WWK05-110-111V3')
    add_text(10, 113, 200, 12, '环光： RL-100-90-W')
    add_text(220, 20, 25, 10, '110mm')
    add_text(220, 35, 25, 10, '80mm')
    prs.save(path)


def run_generator(cfg, template, out, cwd=None):
    cmd = [sys.executable, GENERATOR, '--config', cfg,
           '--template', template, '--output', out, '--auto']
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace',
                          timeout=300, cwd=cwd or os.getcwd())


def assert_deliverable(testcase, proc, out):
    combined = (proc.stdout or '') + (proc.stderr or '')
    testcase.assertEqual(proc.returncode, 0,
                         f'主流程退出码{proc.returncode}\n{combined[-1500:]}')
    pptx = glob.glob(os.path.join(out, '*.pptx'))
    testcase.assertTrue(pptx, f'未产出PPT\n{combined[-800:]}')
    report = os.path.join(out, 'acceptance_report.txt')
    testcase.assertTrue(os.path.exists(report), '验收报告未生成')
    content = open(report, encoding='utf-8', errors='replace').read()
    testcase.assertRegex(content, r'FAIL=0',
                         msg=f'PPT规则自查存在FAIL，不可交付\n{content[-800:]}')


class TestPptPipeline(unittest.TestCase):

    def test_config_to_ppt_fail0(self):
        """回归: config一条命令到PPT，验收FAIL=0（可交付标准）"""
        tmp = vt_common.temp_dir('vt_ppt_')
        try:
            cfg = os.path.join(tmp, 'project_config.json')
            tpl = os.path.join(tmp, 'template.pptx')
            out = os.path.join(tmp, 'out')
            write_config(cfg)
            write_template(tpl)
            p = run_generator(cfg, tpl, out)
            assert_deliverable(self, p, out)
        finally:
            vt_common.rmtree(tmp)

    def test_relative_output_acceptance_still_fails0(self):
        """回归: 相对 --output 时验收不得静默失效（2026-08-31事故：
        验收子进程 cwd=tools_dir，相对路径被 abspath 错位到 tools\\output，
        验收查错文件仍打印完成——交付失检。修复后路径在入口归一为绝对）"""
        tmp = vt_common.temp_dir('vt_pptrel_')
        try:
            cfg = os.path.join(tmp, 'project_config.json')
            tpl = os.path.join(tmp, 'template.pptx')
            write_config(cfg)
            write_template(tpl)
            rel_out = 'vt_rel_out_tmp'
            p = run_generator(cfg, tpl, rel_out, cwd=tmp)
            assert_deliverable(self, p, os.path.join(tmp, rel_out))
        finally:
            vt_common.rmtree(tmp)


    def test_hardware_page_out_of_range_fails_loudly(self):
        """回归: --hardware_page 语义是\"第N个硬件页\"而非幻灯片页码，越界此前
        只打印一行错误并 return None，上层继续走验收，用户只看到\"跑完没PPT\"。
        现要求：非零退出 + 列出真实硬件页 + 不产出半成品 PPT/验收报告"""
        tmp = vt_common.temp_dir('vt_page_')
        try:
            cfg = os.path.join(tmp, 'project_config.json')
            tpl = os.path.join(tmp, 'template.pptx')
            out = os.path.join(tmp, 'out')
            write_config(cfg)
            write_template(tpl)
            cmd = [sys.executable, GENERATOR, '--config', cfg,
                   '--template', tpl, '--output', out, '--auto',
                   '--hardware_page', '5']
            p = subprocess.run(cmd, capture_output=True, text=True,
                               encoding='utf-8', errors='replace',
                               timeout=300)
            combined = (p.stdout or '') + (p.stderr or '')
            self.assertNotEqual(p.returncode, 0,
                                f'越界必须非零退出\n{combined[-1200:]}')
            self.assertIn('超出范围', combined)
            self.assertIn('第几个硬件页', combined)
            self.assertIn('第1页=第1个硬件页', combined,
                          msg='必须列出模板里硬件页的真实页码')
            self.assertFalse(glob.glob(os.path.join(out, '*.pptx')),
                             '越界不得产出半成品PPT')
            self.assertFalse(os.path.exists(
                os.path.join(out, 'acceptance_report.txt')),
                '未生成PPT不得进入验收')
        finally:
            vt_common.rmtree(tmp)


def slide_texts(pptx_path):
    """收集整份 PPT 的全部文本（含表格单元格）"""
    from pptx import Presentation
    texts = []

    def walk(shapes):
        for sh in shapes:
            if getattr(sh, 'has_text_frame', False) and sh.has_text_frame:
                texts.append(sh.text_frame.text)
            if getattr(sh, 'has_table', False) and sh.has_table:
                for row in sh.table.rows:
                    for cell in row.cells:
                        texts.append(cell.text)
    for slide in Presentation(pptx_path).slides:
        walk(slide.shapes)
    return texts


class TestLightPlaceholderInPpt(unittest.TestCase):
    """光源库无匹配时，PPT 必须把\"待选型（需扩库）\"写进光源行，
    并覆盖模板里的旧型号（否则评审会以为本方案选的就是模板那个型号）"""

    def test_needs_expansion_overwrites_template_model(self):
        from generate_ppt import generate_ppt
        tmp = vt_common.temp_dir('vt_lightph_')
        try:
            tpl = os.path.join(tmp, 'template.pptx')
            out = os.path.join(tmp, 'out.pptx')
            write_template(tpl)
            with open(os.path.join(vt_common.SKILL_DIR, 'config',
                                   'hardware_database.json'),
                      encoding='utf-8') as f:
                db = json.load(f)
            cam = next(c for c in db['cameras']
                       if c.get('model') == 'MV-CS050-10GM')
            lens = next(l for l in db['lenses']
                        if l.get('model') == 'WWK05-110-111V3')
            r = generate_ppt(
                template_path=tpl, output_path=out,
                camera=cam, lens=lens,
                light_source={'brand': '', 'model': '',
                              'needs_expansion': True,
                              'type': 'LED环形光光源',
                              'working_distance': 200},
                project_name='待选型测试',
                field_of_view={'width': 60, 'height': 40},
                hardware_page=None)
            self.assertTrue(r, msg='generate_ppt 不应返回 None')
            joined = '\n'.join(slide_texts(out))
            self.assertIn('待选型（需扩库）', joined,
                          msg='光源未选中时必须写明待选型')
            self.assertNotIn('RL-100-90-W', joined,
                             msg='模板旧型号必须被覆盖')
        finally:
            vt_common.rmtree(tmp)


class TestAcceptanceQuarantine(unittest.TestCase):
    """回归: 验收 FAIL 此前只打印一句"处理前不要交付"，PPT 仍留在 output 根
    目录，弱模型看到文件就会交付。现要求：FAIL → 返回 False + PPT 移入
    _rejected\\\\ + 主流程据此非零退出，物理上杜绝误交付。"""

    def test_fail_quarantines_ppt(self):
        import contextlib
        import io

        from pptx import Presentation
        from pptx.util import Mm

        from vision_proposal_generator import VisionProposalGenerator
        tmp = vt_common.temp_dir('vt_quar_')
        try:
            out = os.path.join(tmp, 'out')
            os.makedirs(out)
            ppt = os.path.join(out, '方案.pptx')
            prs = Presentation()
            prs.slide_width, prs.slide_height = Mm(254), Mm(142)
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            box = slide.shapes.add_textbox(Mm(10), Mm(10), Mm(200), Mm(20))
            box.text_frame.text = '硬件选型'
            box2 = slide.shapes.add_textbox(Mm(10), Mm(40), Mm(200), Mm(20))
            box2.text_frame.text = '相机： Basler acA2500-14gm'  # 故意留旧型号
            prs.save(ppt)

            g = VisionProposalGenerator()
            g.auto_mode = True
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ok = g._run_acceptance(ppt, out)
            log = buf.getvalue()

            self.assertFalse(ok, msg=f'验收FAIL必须返回False\n{log[-800:]}')
            self.assertFalse(os.path.exists(ppt),
                             msg='FAIL的PPT不得留在可交付目录根')
            rejected = glob.glob(os.path.join(out, '_rejected', '*.pptx'))
            self.assertTrue(rejected, msg='FAIL的PPT必须移入_rejected留证')
            self.assertIn('拒绝交付', log)
            self.assertIn('_rejected', log)
        finally:
            vt_common.rmtree(tmp)


if __name__ == '__main__':
    unittest.main()
