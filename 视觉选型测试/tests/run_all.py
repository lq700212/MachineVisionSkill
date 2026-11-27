# -*- coding: utf-8 -*-
"""视觉硬件选型 skill 测试运行器（分层回归）。

分层（按"改了什么"选层，详见 README.md）：
  smoke    秒级结构自检：文件/依赖/JSON 合法性
  data     硬件库完整性：schema/可查证/无假型号
  doc      文档契约：SKILL.md/README/模板与代码一致
  core     选型算法单元：精度链/镜头/光源/文本解析/图片/3D引导
  ppt      PPT 质检规则契约（check_ppt_quality 判定边界）
  workflow 端到端工作流：退出码/产物/幂等/验收隔离
  all      全部（默认）

用法：
  python run_all.py                     # 全量
  python run_all.py --layer smoke       # 只跑冒烟（10秒）
  python run_all.py --layer smoke,core  # 多层
  python run_all.py --fast              # 跳过端到端重用例
  python run_all.py --list              # 列出全部用例
  python run_all.py --failfast          # 首个失败即停
"""
import argparse
import os
import sys
import time
import unittest

# 根因：Windows 控制台默认 cp936，被测脚本 print 中文时 stdout 是 GBK，
# 而用例按 UTF-8 解码子进程输出（断言中文关键字），导致 12 条断言假失败。
# 统一给子进程注入 UTF-8 stdio，保证任何 shell/代码页下结果一致。
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vt_common  # noqa: F401,E402 - 注入被测skill路径必须先于用例import

# 层 → 测试模块文件
LAYERS = {
    'smoke': ['test_smoke.py'],
    'data': ['test_data_integrity.py'],
    'doc': ['test_doc_contract.py'],
    'core': ['test_selection_core.py', 'test_text_entry.py',
             'test_channel3.py', 'test_image_fetch.py',
             'test_industry_compliance.py', 'test_3d_selection.py'],
    'ppt': ['test_ppt_quality_contract.py'],
    'workflow': ['test_workflow_contract.py', 'test_ppt_pipeline.py'],
}
ALL_LAYERS = list(LAYERS)

# --fast 跳过的端到端模块（会启动子进程/PPT，耗时最长）
HEAVY_MODULES = {'test_ppt_pipeline.py', 'test_workflow_contract.py'}


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def module_of(test):
    return test.id().split('.')[0] + '.py'


def main():
    ap = argparse.ArgumentParser(description='视觉硬件选型 skill 分层测试')
    ap.add_argument('--layer', default='all',
                    help=f'层名，逗号分隔：{", ".join(ALL_LAYERS)},all（默认 all）')
    ap.add_argument('--fast', action='store_true', help='跳过端到端重用例')
    ap.add_argument('--list', action='store_true', help='只列出用例，不运行')
    ap.add_argument('--failfast', action='store_true', help='首个失败即停')
    args = ap.parse_args()

    if args.layer.strip().lower() == 'all':
        selected = list(ALL_LAYERS)
    else:
        selected = [s.strip() for s in args.layer.split(',') if s.strip()]
        bad = [s for s in selected if s not in LAYERS]
        if bad:
            print(f'未知层: {bad}；可选: {", ".join(ALL_LAYERS)},all')
            return 2
    modules = []
    for layer in selected:
        modules.extend(LAYERS[layer])
    if args.fast:
        modules = [m for m in modules if m not in HEAVY_MODULES]
    modules = list(dict.fromkeys(modules))  # 去重保序

    print('=' * 64)
    print('[测试skill] 视觉硬件选型 · 分层验证')
    print(f'  被测skill: {vt_common.SKILL_DIR}')
    if not os.path.isdir(vt_common.TOOLS_DIR):
        print(f'结论: ✗ 被测skill不存在: {vt_common.SKILL_DIR}')
        print('  （可用环境变量 VISION_SKILL_DIR 指定其他路径）')
        return 2
    print(f'  官网可达: {"是" if vt_common.online() else "否（在线用例将跳过）"}')
    print(f'  层: {",".join(selected)}    模块数: {len(modules)}'
          + ('    [fast]' if args.fast else ''))
    print('=' * 64)

    tests_dir = os.path.dirname(os.path.abspath(__file__))
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for mod in modules:
        path = os.path.join(tests_dir, mod)
        if not os.path.exists(path):
            print(f'[WARN] 层内模块不存在: {mod}')
            continue
        suite.addTests(loader.discover(tests_dir, pattern=mod))

    if args.list:
        for t in flatten(suite):
            print(f'  {t.id()}')
        print(f'\n共 {len(list(flatten(suite)))} 条用例')
        return 0

    t0 = time.time()
    runner = unittest.TextTestRunner(verbosity=2, failfast=args.failfast)
    result = runner.run(suite)
    cost = time.time() - t0

    total = result.testsRun
    failed = len(result.failures)
    errored = len(result.errors)
    skipped = len(result.skipped)
    passed = total - failed - errored - skipped
    print('\n' + '=' * 64)
    print(f'汇总: 运行{total}  通过{passed}  失败{failed}  错误{errored}  '
          f'跳过{skipped}  耗时{cost:.1f}s')
    if failed or errored:
        print('失败明细:')
        for t, tb in result.failures + result.errors:
            print(f'  - {t.id()}\n      {tb.strip().splitlines()[-1][:120]}')
        print('结论: ✗ 存在失败——修复被测skill后必须重跑全量；'
              '处置不了的原样报告用户，禁止改被测脚本硬凑通过')
        return 1
    print(f'结论: ✓ 全部通过（跳过{skipped}条'
          + ('，含离线跳过的在线用例' if skipped else '') + '）')
    if selected != ALL_LAYERS:
        print(f'提示: 本次只跑了 {",".join(selected)} 层；交付前请跑全量 '
              f'`python run_all.py`')
    return 0


if __name__ == '__main__':
    sys.exit(main())
