# -*- coding: utf-8 -*-
"""
v1.3.0 编排层回归测试（一条命令出 PASS/FAIL，弱模型等效）。

覆盖（只测编排逻辑，不重复测主脚本定位）：
  W1 doc2pdf --help：脚本存在且可启动
  W2 seal_workflow --help：脚本存在且可启动
  W3 seal_workflow 在文本版固件上 --dry-run：exit 0 + 打印【结论】（只分析不生成）
  W4 seal_workflow 在文本版固件上全量跑（两参输出式）：exit 0 + 输出 PDF 存在
     + 预览图存在 + 打印【结论】✅/⚠️（位置结论机检化，弱模型只须转述）
  W5 行内分侧契约：乙方↔卖方互为别名/对侧（防"章骑中缝"回归，见 v1.3.0 事故档案）
  W6 公章缺失给指引：exit 1 + 打印位置参数顺序提示（防位置错位 footgun）

用法：python run_test5_workflow.py
输出：系统临时目录 %TEMP%\\seal_test_out_wf\\（每次运行前自动清旧输出）
固件：同目录 fixtures/ 下（由 make_fixture.py 生成，首次运行自动触发）
注意：W4 会真实跑盖章（含压平），耗时约 1~2 分钟；Word 真机转换不在此测
  （依赖本机 Word，CI 不稳定），Word 路径以 doc2pdf 手动回归为准。
"""
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
WORKFLOW = os.path.join(SKILL_DIR, "seal_workflow.py")
DOC2PDF = os.path.join(SKILL_DIR, "doc2pdf.py")

sys.path.insert(0, SCRIPT_DIR)
import make_fixture  # noqa: E402

OUT_DIR = os.path.join(tempfile.gettempdir(), "seal_test_out_wf")

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def run_py(script, *args, timeout=900):
    r = subprocess.run([sys.executable, script, *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    make_fixture.make_text_pdf()  # 固件缺失时重建（与 run_test4 同约定）
    contract = make_fixture.TEXT_PDF
    if not os.path.exists(contract):
        print("❌ 固件缺失且无法生成，中止")
        return 1

    code, out = run_py(DOC2PDF, "--help", timeout=120)
    check("W1 doc2pdf 可启动", code == 0 and "用法" in out, f"exit={code}")

    code, out = run_py(WORKFLOW, "--help", timeout=120)
    check("W2 seal_workflow 可启动", code == 0 and "--no-default-role" in out,
          f"exit={code}")

    code, out = run_py(WORKFLOW, contract, "--dry-run", timeout=600)
    check("W3 dry-run 给结论",
          code == 0 and "【结论】" in out and "位置:" in out,
          f"exit={code}")

    # W4 用"两参输出式"（第二参给不存在的 .pdf→按输出理解、公章默认），
    # 顺带 lock 住位置参数防呆逻辑
    full_out = os.path.join(OUT_DIR, "wf_full_已盖章.pdf")
    code, out = run_py(WORKFLOW, contract, full_out, timeout=900)
    preview = os.path.splitext(full_out)[0] + "_预览.png"
    has_conclusion = "【结论】" in out
    verdict_ok = ("【结论】✅" in out) or ("【结论】⚠️" in out)
    check("W4 全量跑出文件+预览+结论",
          code == 0 and os.path.exists(full_out)
          and os.path.exists(preview) and has_conclusion and verdict_ok,
          f"exit={code} 输出存在={os.path.exists(full_out)} "
          f"预览存在={os.path.exists(preview)}")

    code, out = run_py(WORKFLOW, contract,
                       os.path.join(OUT_DIR, "no_such_seal_xyz.png"),
                       timeout=120)
    check("W6 公章缺失给指引",
          code == 1 and "公章图片不存在" in out and "位置参数顺序" in out,
          f"exit={code}")

    sys.path.insert(0, SKILL_DIR)
    import seal_workflow as wf  # noqa: E402
    check("W5 行内分侧契约",
          "卖方" in wf.ROLE_ALIASES.get("乙方", [])
          and "买方" in wf._opposite_aliases("卖方")
          and "卖方" in wf._opposite_aliases("买方"),
          "乙方↔卖方互为别名/对侧")

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n==== {len(results) - len(failed)}/{len(results)} PASS "
          f"({'ALL GREEN' if not failed else 'FAIL: ' + ','.join(failed)}) ====")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
