#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PPT页面导出图片工具 - 固化"渲染导出+预览"验收步骤
==================================================

把PPTX每页导出为PNG并生成预览产物，供视觉验收/存档/人工抽查使用。
此前该步骤依赖AI临场写COM代码，现固化为脚本（弱模型直接调用）。

预览产物（全部落在预览目录内，默认 ppt_review\）：
  slide_N.png    每页原图（默认1600px宽）
  overview.png   全页联系表总览图（2列网格，一眼看全）
  index.html     浏览器预览页（双击即可翻看每页大图）

用法：
  python export_ppt_images.py 方案.pptx                     # 导出到同目录 ppt_review\
  python export_ppt_images.py 方案.pptx --outdir 导出目录    # 指定输出目录
  python export_ppt_images.py 方案.pptx --width 1920        # 指定宽度（默认1600）
  python export_ppt_images.py 方案.pptx --open              # 导出后打开预览目录

导出通道（自动降级）：
  1. 本机 PowerPoint COM自动化（后台导出不弹窗口）——首选
  2. 无 PowerPoint 时探测 LibreOffice headless 转 PDF（预览降级为PDF）
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
import webbrowser


def _export_via_powerpoint(pptx_path, outdir, width):
    """通道1：PowerPoint COM 导出每页PNG。返回成功页数。"""
    try:
        import win32com.client
    except ImportError:
        print("缺少 pywin32（pip install pywin32），无法调用PowerPoint导出")
        return 0

    ppt = None
    pres = None
    try:
        ppt = win32com.client.Dispatch('PowerPoint.Application')
        pres = ppt.Presentations.Open(pptx_path, ReadOnly=True, WithWindow=False)
        n = pres.Slides.Count
        height = int(width * 9 / 16)
        for i in range(1, n + 1):
            out = os.path.join(outdir, f'slide_{i}.png')
            pres.Slides(i).Export(out, 'PNG', width, height)
        return n
    except Exception as e:
        print(f"PowerPoint导出不可用（需本机安装PowerPoint）: {e}")
        return 0
    finally:
        try:
            if pres is not None:
                pres.Close()
            if ppt is not None:
                ppt.Quit()
        except Exception:
            pass


def _find_soffice():
    """探测 LibreOffice（PATH + 常见安装路径）"""
    exe = shutil.which('soffice')
    if exe:
        return exe
    for p in (
            r'C:\Program Files\LibreOffice\program\soffice.exe',
            r'C:\Program Files (x86)\LibreOffice\program\soffice.exe'):
        if os.path.exists(p):
            return p
    return None


def _export_via_libreoffice(pptx_path, outdir):
    """通道2：无PowerPoint时降级 LibreOffice headless 转PDF（零弹窗）。返回PDF路径或None。"""
    soffice = _find_soffice()
    if not soffice:
        return None
    try:
        print("[降级] 未检测到PowerPoint，改用 LibreOffice 转出PDF预览...")
        r = subprocess.run(
            [soffice, '--headless', '--convert-to', 'pdf', '--outdir', outdir, pptx_path],
            capture_output=True, text=True, timeout=180,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        pdf = os.path.join(outdir, os.path.splitext(os.path.basename(pptx_path))[0] + '.pdf')
        if r.returncode == 0 and os.path.exists(pdf):
            print(f"[降级] PDF预览已生成: {pdf}")
            return pdf
        print(f"[降级] LibreOffice 转换失败: {(r.stderr or '').strip()[:200]}")
    except Exception as e:
        print(f"[降级] LibreOffice 调用失败: {e}")
    return None


def build_overview(outdir, cols=2, thumb_width=800):
    """把 slide_N.png 拼成联系表总览图 overview.png。返回是否成功。"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("缺少 Pillow，跳过总览图生成")
        return False

    pages = sorted(glob.glob(os.path.join(outdir, 'slide_*.png')),
                   key=lambda p: int(''.join(ch for ch in os.path.basename(p) if ch.isdigit()) or 0))
    if not pages:
        return False

    thumbs = []
    for p in pages:
        im = Image.open(p).convert('RGB')
        h = int(thumb_width * im.height / im.width)
        thumbs.append((os.path.basename(p), im.resize((thumb_width, h))))

    rows = (len(thumbs) + cols - 1) // cols
    cell_h = max(t.height for _, t in thumbs) + 34
    pad = 16
    canvas = Image.new('RGB', (cols * thumb_width + (cols + 1) * pad,
                               rows * cell_h + (rows + 1) * pad), (235, 238, 242))
    draw = ImageDraw.Draw(canvas)
    for idx, (name, t) in enumerate(thumbs):
        r, c = divmod(idx, cols)
        x = pad + c * (thumb_width + pad)
        y = pad + r * cell_h
        canvas.paste(t, (x, y))
        # 页码标注（纯数字，避免中文字体依赖）
        page_no = ''.join(ch for ch in name if ch.isdigit())
        draw.rectangle([x, y + t.height, x + thumb_width, y + t.height + 30],
                       fill=(52, 73, 94))
        draw.text((x + 10, y + t.height + 8), f"page {page_no}", fill=(255, 255, 255))
    out = os.path.join(outdir, 'overview.png')
    canvas.save(out)
    print(f"总览图已生成: {out}（{len(thumbs)} 页）")
    return True


def build_index_html(outdir, pptx_name):
    """生成 index.html 浏览器预览页（相对路径引用页面图）。"""
    pages = sorted(glob.glob(os.path.join(outdir, 'slide_*.png')),
                   key=lambda p: int(''.join(ch for ch in os.path.basename(p) if ch.isdigit()) or 0))
    if not pages:
        return False
    items = "\n".join(
        f'    <figure><a href="{os.path.basename(p)}" target="_blank">'
        f'<img src="{os.path.basename(p)}" alt="page {i}"></a>'
        f'<figcaption>第 {i} 页</figcaption></figure>'
        for i, p in enumerate(pages, 1))
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>PPT预览 - {pptx_name}</title>
<style>
  body {{ font-family: "Microsoft YaHei", sans-serif; background: #eef1f5; margin: 24px; }}
  h1 {{ font-size: 20px; color: #2c3e50; }}
  .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; max-width: 1700px; }}
  figure {{ margin: 0; background: #fff; padding: 10px; border-radius: 8px;
           box-shadow: 0 1px 4px rgba(0,0,0,.12); }}
  img {{ width: 100%; border: 1px solid #ddd; display: block; }}
  figcaption {{ text-align: center; color: #555; padding-top: 6px; font-size: 14px; }}
  p.tip {{ color: #666; }}
</style>
</head>
<body>
<h1>PPT预览 - {pptx_name}</h1>
<p class="tip">点击任意页面查看原图；总览图见同目录 overview.png；规则自查报告见同目录 acceptance_report.txt</p>
<div class="grid">
{items}
</div>
</body>
</html>
"""
    out = os.path.join(outdir, 'index.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"预览页已生成: {out}（双击打开浏览）")
    return True


def export_ppt_images(pptx_path, outdir=None, width=1600):
    """导出PPTX全部页面并生成预览产物。返回(成功页数, 导出目录)。"""
    pptx_path = os.path.abspath(pptx_path)
    if not os.path.exists(pptx_path):
        print(f"文件不存在: {pptx_path}")
        return 0, None
    if outdir is None:
        outdir = os.path.join(os.path.dirname(pptx_path), 'ppt_review')
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)

    n = _export_via_powerpoint(pptx_path, outdir, width)
    if n:
        print(f"已导出 {n} 页 → {outdir}")
        build_overview(outdir)
        build_index_html(outdir, os.path.basename(pptx_path))
        return n, outdir

    # 通道2：无 PowerPoint 时的降级预览
    pdf = _export_via_libreoffice(pptx_path, outdir)
    if pdf:
        return -1, outdir  # 负数=降级成功（PDF），调用方据此区分
    return 0, None


def main():
    parser = argparse.ArgumentParser(description='PPT页面导出+预览生成（验收前置步骤）')
    parser.add_argument('pptx', help='PPTX文件路径')
    parser.add_argument('--outdir', help='导出目录（默认同目录ppt_review）')
    parser.add_argument('--width', type=int, default=1600, help='导出宽度像素（默认1600）')
    parser.add_argument('--open', action='store_true', help='导出后打开预览目录/页面')
    args = parser.parse_args()

    n, outdir = export_ppt_images(args.pptx, args.outdir, args.width)
    if n and outdir:
        if args.open:
            index = os.path.join(outdir, 'index.html')
            if os.path.exists(index):
                webbrowser.open('file://' + index.replace('\\', '/'))
            else:
                os.startfile(outdir)
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
