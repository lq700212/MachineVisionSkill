#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
svg2res.py — 设计图标一键转项目资源（svg2res = SVG to resources）

两个子命令：

1. preview  — 扫描目录下全部 *.svg 生成「方案预览页」preview.html
              （每款卡片：大图 + 浅底/深底 × 48/32/20px 尺寸阶梯）。
              说明文字自动取 SVG 文件内第一个 <!-- 注释 -->（AI 画 SVG 时把
              方案语义写在头注释里，预览页直接引用，不重复维护）。

2. convert  — 单款 SVG → 项目可直接用的图片资源：
              PNG 阶梯 512/256/128/64/48/32/24/20/16 + 多帧 ICO（16~256，可作
              app.ico / favicon.ico）。WPF 项目把 <name>.ico 拷到 Assets 并设
              csproj 的 <ApplicationIcon> 即可。

   convert-dir — 批量转换目录下全部 *.svg（每款一个子目录）。

用法：
  python svg2res.py preview  <svg-dir> [--out preview.html]
  python svg2res.py convert  <in.svg> <out-dir> [--name base]
  python svg2res.py convert-dir <svg-dir> <out-dir>

依赖：Edge（渲染 SVG，本机必有）、Pillow（PNG 缩放 + ICO 打包，仅 convert 需要）。
渲染链路：Edge headless 按 device-scale-factor 放大出 512px 高清位图一张，
其余尺寸全部 PIL LANCZOS 缩（比逐尺寸截图快一个数量级，缩小质量无损于 512 源）。

实现注意（实踩沉淀）：
- Edge 截图必须带 --user-data-dir（临时目录），否则不落盘（与本 skill 步骤 7 同坑）；
- --default-background-color=00000000 保持透明底（深浅主题都不穿帮）；
- SVG 根有 width/height 时按 CSS 尺寸渲染（用 scale factor 放大）；只有 viewBox 时
  文档会铺满窗口（window-size 即输出尺寸）；两者都无 = SVG 不合规，报错让 AI 修。
"""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# PNG 阶梯：ICO 帧集（16~256）+ README/文档用的展示尺寸（20 是小尺寸辨识度验收档）
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
PNG_SIZES = [512, 256, 128, 64, 48, 32, 24, 20, 16]
PREVIEW_STEPS = [48, 32, 20]   # 预览页尺寸阶梯（验证 20px 可辨识）
MASTER = 512                    # Edge 只渲这一张高清源


def find_edge():
    """按常见路径探测 Edge；找不到时报错给出指引。"""
    for p in EDGE_CANDIDATES:
        if os.path.isfile(p):
            return p
    raise SystemExit("[svg2res] 未找到 Edge（msedge.exe）。确认已安装 Edge，"
                     "或把安装路径加进脚本 EDGE_CANDIDATES。")


def svg_meta(path):
    """解析 SVG 根尺寸。返回 (width, height)；只有 viewBox 返回 None 让其铺满窗口。"""
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        head = f.read(4096)
    m = re.search(r"<svg[^>]*>", head, re.S)
    if not m:
        raise SystemExit("[svg2res] %s 不是合法 SVG（找不到 <svg> 根）" % path)
    tag = m.group(0)
    w = re.search(r'\bwidth="([\d.]+)', tag)
    h = re.search(r'\bheight="([\d.]+)', tag)
    if w and h:
        return float(w.group(1)), float(h.group(1))
    if not re.search(r"\bviewBox=", tag):
        raise SystemExit("[svg2res] %s 缺 width/height 也缺 viewBox，先修 SVG" % path)
    return None, None


def svg_caption(path):
    """取 SVG 内第一个 HTML 注释作方案说明（AI 把语义写在头注释里）。"""
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read(8192)
    m = re.search(r"<!--\s*(.+?)\s*-->", text, re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()


def render_master(edge, svg_path, out_png, tmp_ud):
    """Edge headless 渲染 MASTER(512) 高清 PNG（透明底）。"""
    w, h = svg_meta(svg_path)
    url = "file:///" + os.path.abspath(svg_path).replace("\\", "/")
    cmd = [edge, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           "--no-first-run", "--disable-extensions",
           "--user-data-dir=" + tmp_ud,
           "--default-background-color=00000000"]
    if w and h:
        # SVG 有 CSS 尺寸：窗口=原尺寸，scale factor 放大到 MASTER
        k = MASTER / float(w)
        cmd += ["--window-size=%d,%d" % (round(w), round(h)),
                "--force-device-scale-factor=%.6f" % k]
    else:
        # 只有 viewBox：文档铺满窗口，窗口即输出尺寸
        cmd += ["--window-size=%d,%d" % (MASTER, MASTER)]
    cmd += ["--screenshot=" + out_png, url]
    r = subprocess.run(cmd, capture_output=True, timeout=90)
    if not os.path.isfile(out_png) or os.path.getsize(out_png) < 500:
        raise SystemExit("[svg2res] Edge 截图失败：%s\nstderr: %s"
                         % (svg_path, r.stderr.decode("utf-8", "replace")[:500]))


def cmd_convert(args):
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("[svg2res] convert 需要 Pillow：python -m pip install pillow")

    edge = find_edge()
    os.makedirs(args.out_dir, exist_ok=True)
    name = args.name or re.sub(r"\.svg$", "", os.path.basename(args.svg), flags=re.I)
    tmp_ud = tempfile.mkdtemp(prefix="edge_svg2res_")
    master_png = os.path.join(tmp_ud, "master.png")
    try:
        render_master(edge, args.svg, master_png, tmp_ud)
        img = Image.open(master_png).convert("RGBA")
        # 高清源若不是正方形或没缩到位，居中裁方 + 统一到 MASTER
        side = min(img.size)
        img = img.crop(((img.width - side) // 2, (img.height - side) // 2,
                        (img.width + side) // 2, (img.height + side) // 2))
        if img.size != (MASTER, MASTER):
            img = img.resize((MASTER, MASTER), Image.LANCZOS)

        pngs = []
        for s in PNG_SIZES:
            p = os.path.join(args.out_dir, "%s_%d.png" % (name, s))
            img.resize((s, s), Image.LANCZOS).save(p)
            pngs.append(p)
        ico_path = os.path.join(args.out_dir, name + ".ico")
        img.save(ico_path, format="ICO", sizes=ICO_SIZES)
    finally:
        shutil.rmtree(tmp_ud, ignore_errors=True)

    print("[svg2res] %s -> %s" % (os.path.basename(args.svg), args.out_dir))
    print("  ICO : %s（帧 %s）" % (ico_path,
          " ".join("%d" % s for s, _ in ICO_SIZES)))
    print("  PNG : " + " ".join(os.path.basename(p) for p in pngs))


def cmd_convert_dir(args):
    svgs = sorted(f for f in os.listdir(args.svg_dir) if f.lower().endswith(".svg"))
    if not svgs:
        raise SystemExit("[svg2res] %s 下没有 SVG" % args.svg_dir)
    for f in svgs:
        ns = argparse.Namespace(svg=os.path.join(args.svg_dir, f),
                                out_dir=os.path.join(args.out_dir, os.path.splitext(f)[0]),
                                name=os.path.splitext(f)[0])
        cmd_convert(ns)


PREVIEW_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>图标方案预览（svg2res 自动生成）</title>
<style>
  body{margin:0;padding:32px 40px;background:#FDF8F4;font-family:"Microsoft YaHei",system-ui,sans-serif;color:#3D3229;}
  h1{font-size:24px;margin:0 0 6px;}
  .sub{color:#8A7A6D;font-size:13px;margin:0 0 26px;line-height:1.8;}
  .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:20px;max-width:1080px;}
  .card{background:#fff;border-radius:16px;padding:20px 22px;box-shadow:0 2px 10px rgba(0,0,0,.08);}
  .head{display:flex;align-items:flex-start;gap:16px;margin-bottom:10px;}
  .head img{width:96px;height:96px;border-radius:22px;flex:none;}
  h2{margin:0;font-size:16px;}
  .sem{color:#8A7A6D;font-size:12.5px;line-height:1.7;margin:6px 0 0;}
  .file{color:#B0A294;font-size:11px;margin-top:8px;}
  .sizes{display:flex;align-items:center;gap:14px;padding:11px 14px;border-radius:12px;background:#FDF8F4;margin-top:10px;}
  .sizes.dark{background:#2B2320;}
  .sizes img{border-radius:8px;}
  .lab{font-size:11px;color:#8A7A6D;margin-right:auto;flex:none;}
  .sizes.dark .lab{color:#B9A79A;}
</style>
</head>
<body>
<h1>__TITLE__</h1>
<p class="sub">__N__ 款候选 · 由 svg2res.py 自动生成（语义取自各 SVG 头注释）·
浅底/深底 × 48/32/20px 阶梯，重点看 20px 是否仍可辨识 · 选定款跑 convert 转项目资源。</p>
<div class="grid">
__CARDS__
</div>
</body>
</html>
"""

CARD_TMPL = """  <div class="card">
    <div class="head">
      <img src="__FILE__" alt="__NAME__">
      <div>
        <h2>__NAME__</h2>
        <p class="sem">__SEM__</p>
        <p class="file">__FILE__</p>
      </div>
    </div>
    <div class="sizes"><span class="lab">浅底</span><img src="__FILE__" width="48" alt=""><img src="__FILE__" width="32" alt=""><img src="__FILE__" width="20" alt=""></div>
    <div class="sizes dark"><span class="lab">深底</span><img src="__FILE__" width="48" alt=""><img src="__FILE__" width="32" alt=""><img src="__FILE__" width="20" alt=""></div>
  </div>
"""


def cmd_preview(args):
    svgs = sorted(f for f in os.listdir(args.svg_dir) if f.lower().endswith(".svg"))
    if not svgs:
        raise SystemExit("[svg2res] %s 下没有 SVG" % args.svg_dir)
    cards = []
    for f in svgs:
        sem = svg_caption(os.path.join(args.svg_dir, f))
        cards.append(CARD_TMPL.replace("__FILE__", f)
                     .replace("__NAME__", os.path.splitext(f)[0])
                     .replace("__SEM__", sem or "（SVG 头注释里写方案语义，预览页自动引用）"))
    html = (PREVIEW_TMPL.replace("__TITLE__", args.title)
            .replace("__N__", str(len(svgs)))
            .replace("__CARDS__", "\n".join(cards)))
    out = os.path.join(args.svg_dir, args.out)
    with io.open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print("[svg2res] 预览页已生成：%s（%d 款，双击离线可看）" % (out, len(svgs)))


def main():
    ap = argparse.ArgumentParser(description="SVG 图标 -> 项目资源（PNG 阶梯 + 多帧 ICO）+ 方案预览页")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("preview", help="扫目录生成选款预览页")
    p1.add_argument("svg_dir")
    p1.add_argument("--out", default="preview.html")
    p1.add_argument("--title", default="图标方案预览")
    p1.set_defaults(func=cmd_preview)

    p2 = sub.add_parser("convert", help="单款 SVG 转 PNG 阶梯 + ICO")
    p2.add_argument("svg")
    p2.add_argument("out_dir")
    p2.add_argument("--name", default=None, help="资源基名（默认取文件名）")
    p2.set_defaults(func=cmd_convert)

    p3 = sub.add_parser("convert-dir", help="批量转换目录下全部 SVG")
    p3.add_argument("svg_dir")
    p3.add_argument("out_dir")
    p3.set_defaults(func=cmd_convert_dir)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
