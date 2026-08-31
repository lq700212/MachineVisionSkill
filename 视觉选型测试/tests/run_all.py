# -*- coding: utf-8 -*-
"""测试runner：一键运行全部用例，中文汇总报告，exit code 供 CI/模型判断。

用法：
  python run_all.py           # 全量（含在线用例与PPT端到端重用例）
  python run_all.py --fast    # 跳过重用例（test_ppt_pipeline）
"""
import argparse
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vt_common  # noqa: F401,E402 - 注入被测skill路径必须先于用例import


def main():
    ap = argparse.ArgumentParser(description='视觉硬件选型 skill 测试套件')
    ap.add_argument('--fast', action='store_true', help='跳过PPT端到端重用例')
    args, _ = ap.parse_known_args()

    print('=' * 64)
    print('[测试skill] 视觉硬件选型 · 全量验证（回归+注入）')
    print(f'  被测skill: {vt_common.SKILL_DIR}')
    if not os.path.isdir(vt_common.TOOLS_DIR):
        print(f'结论: ✗ 被测skill不存在: {vt_common.SKILL_DIR}')
        print('  （可用环境变量 VISION_SKILL_DIR 指定其他路径）')
        return 2
    print(f'  官网可达: {"是" if vt_common.online() else "否（在线用例将跳过）"}')
    print(f'  模式: {"fast（跳过PPT端到端）" if args.fast else "全量"}')
    print('=' * 64)

    loader = unittest.TestLoader()
    suite = loader.discover(os.path.dirname(os.path.abspath(__file__)),
                            pattern='test_*.py')

    def _flatten(s):
        for item in s:
            if isinstance(item, unittest.TestSuite):
                yield from _flatten(item)
            else:
                yield item

    if args.fast:
        # fast模式：剔除标记为重用例的模块
        suite = unittest.TestSuite(
            t for t in _flatten(suite) if 'test_ppt_pipeline' not in t.id())

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    total = result.testsRun
    failed = len(result.failures)
    errored = len(result.errors)
    skipped = len(result.skipped)
    passed = total - failed - errored - skipped
    print('\n' + '=' * 64)
    print(f'汇总: 运行{total}  通过{passed}  失败{failed}  错误{errored}  跳过{skipped}')
    if failed or errored:
        print('失败明细:')
        for t, tb in result.failures + result.errors:
            print(f'  - {t.id()}\n      {tb.strip().splitlines()[-1][:120]}')
        print('结论: ✗ 存在失败——修复被测skill后必须重跑全量；'
              '处置不了的原样报告用户，禁止改被测脚本硬凑通过')
        return 1
    print(f'结论: ✓ 全部通过（跳过{skipped}条'
          + ('，含离线跳过的在线用例' if skipped else '') + '）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
