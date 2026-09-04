# -*- coding: utf-8 -*-
"""通道3（AI浏览器接管自动执行）回归：2026-09-04 修复的4处链路断裂。

历史bug（修复前 fetch 的通道3形同虚设，必然落到人工SOP）：
1. 子进程参数错位：database_updater 传 [url, model]，而 browser_fetch CLI
   约定是 <型号> [品牌] —— url被当型号搜索，必然搜不到
2. 输出协议不匹配：只认 "页面已保存到:"，但 browser_fetch 实际输出
   "文件路径:" —— HTML路径永远解析不到
3. timeout=60s 太短：browser_fetch 含模拟人工随机延迟+多次networkidle等待，
   60s 大概率 TimeoutExpired
4. AttributeError：调用 _html_to_plain，但模块只有 html_to_plain ——
   即使前三关都过，最后一步也崩

用例全部离线（mock fetch_page/headless_render/subprocess.run），
不碰真实库与网络。
"""
import os
import subprocess
import sys
import unittest
from unittest import mock

import vt_common  # noqa: F401
import database_updater as du


# 可被 extract_lens_params 提取的假详情页（全文标签式，单型号页）
FAKE_HTML = """
<html><body>
<h1>TESTLENS-100 产品详情</h1>
<table>
<tr><td>放大倍率</td><td>0.5</td></tr>
<tr><td>支持CCD尺寸</td><td>Φ11.0</td></tr>
<tr><td>工作距</td><td>110±2</td></tr>
<tr><td>F/#</td><td>5.6</td></tr>
</table>
</body></html>
"""


def _make_args(tmp, html_path=None, brand='视清科技', model='TESTLENS-100'):
    """构造 fetch 子命令参数（draft 输出指向临时目录，不污染 CWD）"""
    ns = mock.Mock()
    ns.model = model
    ns.brand = brand
    ns.type = 'lens'
    ns.url = 'https://example.com/product/TESTLENS-100.html'
    ns.lens_type = '物方远心镜头'
    ns.draft = os.path.join(tmp, 'draft.json')
    ns.static_only = False
    ns.render_ms = 12000
    ns.db = os.path.join(tmp, 'unused_db.json')
    # 通道3需要真实存在的HTML文件（由mock的browser_fetch"产出"）
    if html_path is None:
        html_path = os.path.join(tmp, 'browser_saved.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(FAKE_HTML)
    return ns, html_path


def _force_channel3(tmp, html_path=None):
    """mock 前两级通道失败 + mock 子进程成功返回已保存的HTML。

    返回 (args, fake_run) —— run 的调用参数在用例中再断言。
    html_path=None 时由 _make_args 落盘假HTML并返回真实路径。
    """
    ns, html_path = _make_args(tmp, html_path=html_path)

    def fake_run(cmd, **kwargs):
        # 模拟 browser_fetch.py 成功输出（真实脚本同时打印两种标记行）
        out = (f"[SOP步骤2] 访问产品详情页...\n"
               f"  [OK] 产品详情页已保存\n"
               f"文件路径: {html_path}\n"
               f"页面已保存到: {html_path}\n")
        r = subprocess.CompletedProcess(cmd, 0, stdout=out, stderr='')
        return r

    return ns, fake_run


class TestChannel3AutoTakeover(unittest.TestCase):
    """通道3自动接管：子进程调用契约 + HTML解析 + 提取入库全链路"""

    def setUp(self):
        self.tmp = vt_common.temp_dir('vt_ch3_')

    def tearDown(self):
        vt_common.rmtree(self.tmp)

    def _run_fetch_channel3(self, ns, fake_run):
        """在 mock 前两级失败 + mock 子进程成功的环境下跑 cmd_fetch"""
        with mock.patch.object(du, 'fetch_page', side_effect=IOError('网络拒绝')), \
             mock.patch.object(du, 'headless_render', return_value=None), \
             mock.patch.object(du.subprocess, 'run', side_effect=fake_run):
            rc = du.cmd_fetch(ns)
        return rc

    def test_channel3_args_order_and_headless(self):
        """回归(参数错位bug): 子进程参数必须是 [型号, 品牌, --headless]。
        历史bug：传的是 [url, model] —— url被browser_fetch当型号搜索"""
        ns, fake_run = _force_channel3(self.tmp, None)
        calls = []

        def spy_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return fake_run(cmd, **kwargs)

        self._run_fetch_channel3(ns, spy_run)
        self.assertTrue(calls, msg='通道3未调用子进程（自动接管未触发）')
        cmd, kwargs = calls[0]
        self.assertTrue(cmd[1].endswith('browser_fetch.py'),
                        msg=f'被调脚本不是browser_fetch.py: {cmd}')
        self.assertEqual(cmd[2:],
                         ['TESTLENS-100', '视清科技', '--headless'],
                         msg=f'子进程参数错位（旧bug把url当型号）: {cmd}')

    def test_channel3_timeout_budget(self):
        """回归(60s超时bug): timeout必须≥180s。
        browser_fetch 内含模拟人工延迟（随机sleep合计可达数十秒）+
        多次networkidle等待，60s必超时导致通道3从未成功过"""
        ns, fake_run = _force_channel3(self.tmp, None)
        calls = []

        def spy_run(cmd, **kwargs):
            calls.append(kwargs)
            return fake_run(cmd, **kwargs)

        self._run_fetch_channel3(ns, spy_run)
        self.assertTrue(calls, msg='通道3未调用子进程')
        t = calls[0].get('timeout', 0)
        self.assertGreaterEqual(t, 180,
                                msg=f'timeout={t}s 太短（browser_fetch人工模拟延迟下必超时）')

    def test_channel3_html_path_protocol(self):
        """回归(协议不匹配bug): stdout解析必须兼容"文件路径:"标记行。
        历史bug：只认"页面已保存到:"，而browser_fetch输出"文件路径:"。"""
        ns, fake_run = _force_channel3(self.tmp, None)

        # 只输出旧协议行（不带"页面已保存到:"）也必须能解析成功
        html_path = os.path.join(self.tmp, 'browser_saved.html')

        def old_protocol_run(cmd, **kwargs):
            out = f"文件路径: {html_path}"
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr='')

        with mock.patch.object(du, 'fetch_page', side_effect=IOError('网络拒绝')), \
             mock.patch.object(du, 'headless_render', return_value=None), \
             mock.patch.object(du.subprocess, 'run', side_effect=old_protocol_run):
            rc = du.cmd_fetch(ns)
        self.assertEqual(rc, 0, msg='旧协议输出行"文件路径:"未被解析，通道3失败'
                                    '（历史bug：只认"页面已保存到:"）')

    def test_channel3_extract_and_draft_no_crash(self):
        """回归(AttributeError bug): HTML解析→提取→草稿全链路不崩并产出草稿。
        历史bug：调用了不存在的 _html_to_plain，即使拿到HTML也在最后一步崩"""
        ns, fake_run = _force_channel3(self.tmp, None)
        rc = self._run_fetch_channel3(ns, fake_run)
        self.assertEqual(rc, 0, msg='通道3未走通（提取/草稿链路异常）')
        self.assertTrue(os.path.isfile(ns.draft),
                        msg='草稿未产出，通道3未完成入库前半段')
        with open(ns.draft, encoding='utf-8') as f:
            import json
            draft = json.load(f)
        self.assertEqual(draft['entry']['model'], 'TESTLENS-100',
                         msg=f'草稿型号错: {draft}')
        self.assertAlmostEqual(draft['entry']['magnification'], 0.5, places=6,
                                msg=f'倍率提取错: {draft}')
        self.assertAlmostEqual(draft['entry']['working_distance'], 110.0, places=6,
                               msg=f'WD提取错: {draft}')

    def test_channel3_child_failure_falls_to_manual_sop(self):
        """回归: 子进程失败(returncode=2)时诚实降级输出人工SOP，exit=2。
        通道3不许编造：拿不到HTML就交人工，绝不用假数据入库"""
        ns, _ = _make_args(self.tmp)

        def fail_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 2, stdout='', stderr='搜索失败')

        with mock.patch.object(du, 'fetch_page', side_effect=IOError('网络拒绝')), \
             mock.patch.object(du, 'headless_render', return_value=None), \
             mock.patch.object(du.subprocess, 'run', side_effect=fail_run):
            rc = du.cmd_fetch(ns)
        self.assertEqual(rc, 2, msg='子进程失败必须exit=2转人工SOP（诚实降级）')
        self.assertFalse(os.path.exists(ns.draft) and os.path.getsize(ns.draft) > 0,
                         msg='子进程失败时不应产出草稿')


if __name__ == '__main__':
    unittest.main()
