# -*- coding: utf-8 -*-
"""
v1.1.0 扫描件/图片盖章专项测试（一条命令出 PASS/FAIL，弱模型等效）。

覆盖：
  T1 文本版 PDF 回归：智能定位成功 + 压平后公章不可单独选中 + 文字可搜
  T2 扫描件 PDF：自动识别扫描件 + OCR 建文字层 + 智能定位成功 + 压平生效 + 文字可搜
  T3 图片输入默认输出同格式图片：输出 PNG、尺寸与原图一致
  T4 图片输入指定 .pdf 输出：输出 PDF 且盖章页压平
  T5 扫描件 --dry-run：只分析不生成文件
  T6 图片输入时章确实落在"乙方（盖章）"行附近（渲染像素级校验，不漂移到默认右下角）

用法：python run_test4_scan.py
输出：系统临时目录 %TEMP%\\seal_test_out\\（每次运行前自动清旧输出）
固件：同目录 fixtures/ 下（由 make_fixture.py 生成，首次运行自动触发）
"""
import os
import subprocess
import sys
import tempfile

import fitz
from PIL import Image

# ---- 路径 ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
STAMPER = os.path.join(SKILL_DIR, "pdf_seal_stamper.py")
DEFAULT_SEAL = os.path.join(SKILL_DIR, "默认公章图片.png")

# 固件生成器同目录，直接导入
sys.path.insert(0, SCRIPT_DIR)
import make_fixture  # noqa: E402

# 测试输出落系统临时目录（不污染 skill 目录也不污染用户工作区）
OUT_DIR = os.path.join(tempfile.gettempdir(), "seal_test_out")

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def run_stamper(*args):
    # 位置参数顺序：合同文件 公章图片 输出文件
    args = list(args)
    if len(args) > 1 and args[1] is None:
        args[1] = DEFAULT_SEAL
    args = [a for a in args if a is not None]
    r = subprocess.run([sys.executable, STAMPER, *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def stamped_page_images_ok(pdf_path, page_no=1):
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_no - 1]
        imgs = page.get_images(full=True)
        if len(imgs) != 1:
            return False, f"图片对象数={len(imgs)}（应为1）"
        return True, "1 张整页位图"
    finally:
        doc.close()


def text_searchable(pdf_path, needle):
    doc = fitz.open(pdf_path)
    try:
        return any(needle in p.get_text() for p in doc)
    finally:
        doc.close()


def red_ratio_near(img, cx, cy, r):
    import numpy as np
    arr = np.asarray(img).astype(int)
    h, w = arr.shape[:2]
    x0, x1 = max(0, int(cx - r)), min(w, int(cx + r))
    y0, y1 = max(0, int(cy - r)), min(h, int(cy + r))
    sub = arr[y0:y1, x0:x1]
    red = ((sub[:, :, 0] > 120) & (sub[:, :, 0] > sub[:, :, 1] * 1.3) &
           (sub[:, :, 0] > sub[:, :, 2] * 1.3))
    return red.mean() if sub.size else 0.0


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for f in os.listdir(OUT_DIR):
        try:
            os.unlink(os.path.join(OUT_DIR, f))
        except PermissionError:
            print("WARNING: old output locked: %s (close locking program and retry)" % f)
            sys.exit(2)

    print("=" * 60)
    print("[PREP] Generating test fixtures")
    print("=" * 60)
    make_fixture.make_text_pdf()
    photo_size = make_fixture.render_photo()
    make_fixture.make_scan_pdf()
    print("  fixtures ready, photo=%dx%d" % photo_size)

    # ---- T1 ----
    print("\n" + "=" * 60)
    print("[T1] Text PDF regression")
    print("=" * 60)
    out1 = os.path.join(OUT_DIR, "t1_text_stamped.pdf")
    rc, log = run_stamper(make_fixture.TEXT_PDF, None, out1, "--company",
                          "上海示例精密仪器有限公司")
    check("T1 script OK", rc == 0)
    check("T1 auto定位 OK", "智能定位成功（策略：明确盖章栏）" in log)
    check("T1 output exists", os.path.exists(out1))
    if os.path.exists(out1):
        ok, detail = stamped_page_images_ok(out1)
        check("T1 flatten防编辑", ok, detail)
        check("T1 text searchable", text_searchable(out1, "乙方"))

    # ---- T2 ----
    print("\n" + "=" * 60)
    print("[T2] Scanned PDF (no text layer)")
    print("=" * 60)
    out2 = os.path.join(OUT_DIR, "t2_scan_stamped.pdf")
    rc, log = run_stamper(make_fixture.SCAN_PDF, None, out2, "--company",
                          "上海示例精密仪器有限公司")
    check("T2 script OK", rc == 0)
    check("T2 detected scanned PDF", "扫描件 PDF（无文本层）" in log)
    check("T2 OCR text layer built", "OCR 建立文字层完成" in log)
    check("T2 auto定位 OK", "智能定位成功（策略：明确盖章栏）" in log)
    check("T2 output exists", os.path.exists(out2))
    if os.path.exists(out2):
        ok, detail = stamped_page_images_ok(out2)
        check("T2 flatten防编辑", ok, detail)
        check("T2 text searchable", text_searchable(out2, "乙方"))

    # ---- T3 ----
    print("\n" + "=" * 60)
    print("[T3] Image input -> default PNG output")
    print("=" * 60)
    photo_copy = os.path.join(OUT_DIR, "t3_photo.png")
    Image.open(make_fixture.PHOTO_PNG).save(photo_copy)
    rc, log = run_stamper(photo_copy, None, None, "--company",
                          "上海示例精密仪器有限公司")
    expect3 = os.path.join(OUT_DIR, "t3_photo_已盖章.png")
    check("T3 script OK", rc == 0)
    check("T3 detected image input", "图片文件" in log)
    check("T3 output PNG exists", os.path.exists(expect3))
    if os.path.exists(expect3):
        with Image.open(expect3) as im:
            # pixmap 缩放取整允许 ±2px 允差（渲染 zoom 浮点取整，非回归不判死）
            dw, dh = abs(im.size[0] - photo_size[0]), abs(im.size[1] - photo_size[1])
            check("T3 output same resolution", dw <= 2 and dh <= 2,
                  "%s vs %s" % (im.size, photo_size))

    # ---- T4 ----
    print("\n" + "=" * 60)
    print("[T4] Image input -> PDF output")
    print("=" * 60)
    out4 = os.path.join(OUT_DIR, "t4_img2pdf_stamped.pdf")
    rc, log = run_stamper(make_fixture.PHOTO_PNG, None, out4, "--company",
                          "上海示例精密仪器有限公司")
    check("T4 script OK", rc == 0)
    check("T4 output PDF exists", os.path.exists(out4))
    if os.path.exists(out4):
        ok, detail = stamped_page_images_ok(out4)
        check("T4 flatten防编辑", ok, detail)
        check("T4 text searchable", text_searchable(out4, "乙方"))

    # ---- T5 ----
    print("\n" + "=" * 60)
    print("[T5] Scanned PDF --dry-run")
    print("=" * 60)
    out5 = os.path.join(OUT_DIR, "t5_dryrun.pdf")
    rc, log = run_stamper(make_fixture.SCAN_PDF, None, out5, "--dry-run",
                          "--company", "上海示例精密仪器有限公司")
    check("T5 script OK", rc == 0)
    check("T5 DRY RUN no output", "DRY RUN" in log and not os.path.exists(out5))

    # ---- T6 ----
    print("\n" + "=" * 60)
    print("[T6] Image seal placement check (should be near 乙方 row, not default bottom-right)")
    print("=" * 60)
    if os.path.exists(expect3):
        img = Image.open(expect3).convert("RGB")
        W, H = img.size
        y_expect = H * 660 / 842
        x_expect = W * 160 / 595
        r = W * 62 / 595
        ratio_hit = red_ratio_near(img, x_expect, y_expect, r)
        y_default = H * 547.5 / 842
        x_default = W * 318.5 / 595
        ratio_default = red_ratio_near(img, x_default, y_default, r)
        check("T6 seal near 乙方 row", ratio_hit > 0.01, "red_ratio=%.4f" % ratio_hit)
        check("T6 not at default position", ratio_default < 0.005,
              "default_pos_red=%.4f" % ratio_default)

    # ---- Summary ----
    print("\n" + "=" * 60)
    n_pass = sum(1 for _, ok, _ in results if ok)
    n_all = len(results)
    print("Summary: %d/%d PASS" % (n_pass, n_all))
    if n_pass == n_all:
        print("Result: ALL PASS")
    else:
        print("Result: FAIL detected -- failures:")
        for name, ok, detail in results:
            if not ok:
                print("  - %s %s" % (name, detail))
    print("=" * 60)
    sys.exit(0 if n_pass == n_all else 1)


if __name__ == "__main__":
    main()
