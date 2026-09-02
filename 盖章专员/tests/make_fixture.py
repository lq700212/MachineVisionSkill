# -*- coding: utf-8 -*-
"""
扫描件/图片盖章测试固件生成器（run_test4_scan.py 的前置步骤，也可单独运行）。
生成三份同源固件（输出到本脚本同目录的 fixtures/ 下）：
  1. text_contract.pdf  文本版合同（甲方/乙方 + 乙方明确盖章栏）—— 回归原有功能
  2. contract_photo.png 该合同渲染图（模拟手机拍照件）—— 图片输入测试
  3. scan_contract.pdf  由渲染图重建的无文本层 PDF（模拟扫描件）—— 扫描件测试
"""
import io
import os
import fitz
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
TEXT_PDF = os.path.join(FIXTURES, "text_contract.pdf")
PHOTO_PNG = os.path.join(FIXTURES, "contract_photo.png")
SCAN_PDF = os.path.join(FIXTURES, "scan_contract.pdf")

RENDER_DPI = 200  # 模拟拍照/扫描分辨率


def make_text_pdf():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    lines = [
        (80, "采 购 合 同", 18),
        (130, "合同编号：HT-2026-0001", 11),
        (160, "甲方（需方）：苏州华际光电科技有限公司", 11),
        (185, "乙方（供方）：上海示例精密仪器有限公司", 11),
        (230, "一、产品名称、规格及数量：光学镜片 100 片。", 11),
        (255, "二、价格：人民币伍万元整。", 11),
        (280, "三、交付：合同签订后 30 日内交付。", 11),
        (620, "甲方（盖章）：", 12),
        (660, "乙方（盖章）：", 12),
        (720, "签订日期：2026 年 9 月 1 日", 11),
    ]
    for y, text, size in lines:
        page.insert_text(fitz.Point(72, y), text, fontsize=size,
                         fontname="china-s")
    os.makedirs(FIXTURES, exist_ok=True)
    doc.save(TEXT_PDF)
    doc.close()


def render_photo():
    doc = fitz.open(TEXT_PDF)
    pix = doc[0].get_pixmap(dpi=RENDER_DPI, alpha=False)
    stride = getattr(pix, "stride", pix.width * 3)
    img = Image.frombuffer("RGB", (pix.width, pix.height), pix.samples,
                           "raw", "RGB", stride, 1).copy()
    doc.close()
    img.save(PHOTO_PNG)
    return img.size


def make_scan_pdf():
    img = Image.open(PHOTO_PNG).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(SCAN_PDF)
    doc.close()


if __name__ == "__main__":
    make_text_pdf()
    size = render_photo()
    make_scan_pdf()
    print(f"固件生成完成：\n  {TEXT_PDF}\n  {PHOTO_PNG} ({size[0]}x{size[1]})\n  {SCAN_PDF}")
