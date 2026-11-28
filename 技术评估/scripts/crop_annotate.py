# -*- coding: utf-8 -*-
"""crop_annotate：按 project.json 批量裁剪、缩放、标注截图。

设计原则：截图只保留有用区域，右侧加白边写标签，不遮挡界面内容。

project.json 的 images 配置：
{
  "images": [
    {
      "src": "assets/raw/img_001.jpg",
      "out": "assets/ui_annotated.png",
      "crop": [165, 510, 1190, 1240],     // 可选，[x1,y1,x2,y2]
      "scale": 1.5,                        // 可选，放大倍数
      "side": 330,                         // 可选，右侧标签栏宽度
      "font_size": 21,                     // 可选
      "annotations": [
        {
          "box": [45, 560],                // [y1, y2]，横向铺满图片
          "color": "#1E6EDC",              // 可选
          "label": "10.63.11.x 工厂内网",
          "sub": "设备一 ~ 设备四",
          "label_y": 300                   // 标签在右栏的垂直位置
        }
      ]
    }
  ]
}

用法：python crop_annotate.py --config project.json
"""
import argparse
import json
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("[FAIL] 缺少 Pillow：pip install pillow")
    sys.exit(1)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def load_font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def hex_rgb(s, default=(30, 110, 220)):
    s = (s or "").strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return default


def process(item, base_dir):
    src = item["src"]
    if not os.path.isabs(src):
        src = os.path.join(base_dir, src)
    if not os.path.exists(src):
        print(f"  [FAIL] 原图不存在：{src}")
        return None

    out = item.get("out")
    if not out:
        print("  [FAIL] 缺少 out")
        return None
    if not os.path.isabs(out):
        out = os.path.join(base_dir, out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    im = Image.open(src).convert("RGB")
    orig_w, orig_h = im.width, im.height
    crop = item.get("crop")
    if crop:
        x1, y1, x2, y2 = crop
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(im.width, x2), min(im.height, y2)
        if x2 <= x1 or y2 <= y1:
            print(f"  [FAIL] crop 越界：{crop}")
            return None
        ratio = ((x2 - x1) * (y2 - y1)) / float(orig_w * orig_h)
        if ratio > 0.95:
            print(f"  [WARN] crop 占原图 {ratio:.0%}，可能没裁干净；请目检输出图")
        im = im.crop((x1, y1, x2, y2))
    else:
        print("  [WARN] 未配置 crop，整张原图直接输出；请确认没有桌面/任务栏/显示器边框")

    scale = float(item.get("scale", 1.0))
    if scale != 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)

    annotations = item.get("annotations") or []
    side = int(item.get("side", 0)) if annotations else 0
    if side > 0:
        canvas = Image.new("RGB", (im.width + side, im.height), "white")
    else:
        canvas = Image.new("RGB", (im.width, im.height), "white")
    canvas.paste(im, (0, 0))

    if annotations:
        canvas = canvas.convert("RGBA")
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        f_title = load_font(int(item.get("font_size", 21)))
        f_small = load_font(int(item.get("sub_font_size", 16)))
        cw = im.width

        for ann in annotations:
            rect = ann.get("rect")
            if rect:
                x1, y1, x2, y2 = [int(v) for v in rect]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(cw, x2), min(im.height, y2)
                if x2 <= x1 or y2 <= y1:
                    print(f"  [WARN] rect 越界，跳过：{rect}")
                    continue
            else:
                box = ann.get("box") or [0, im.height]
                x1, x2 = 3, cw - 3
                y1, y2 = int(box[0]), int(box[1])
                y1, y2 = max(0, y1), min(im.height, y2)
                if y2 <= y1:
                    print(f"  [WARN] box 越界，跳过：{box}")
                    continue
            color = hex_rgb(ann.get("color"))
            label = ann.get("label", "")
            sub = ann.get("sub", "")
            label_y = int(ann.get("label_y", (y1 + y2) // 2))

            d.rounded_rectangle([x1, y1, x2, y2], radius=9,
                                fill=color + (26,), outline=color + (235,), width=3)
            cy = (y1 + y2) // 2
            d.line([(x2, cy), (cw + 12, cy), (cw + 12, label_y), (cw + 22, label_y)],
                   fill=color + (235,), width=2)
            if label:
                d.text((cw + 30, label_y - 27), label, font=f_title, fill=(25, 25, 25, 255))
            if sub:
                d.text((cw + 30, label_y + 3), sub, font=f_small, fill=(95, 95, 95, 255))

        canvas = Image.alpha_composite(canvas, overlay).convert("RGB")

    canvas.save(out, quality=95)
    print(f"  [OK] {out}  {canvas.width}x{canvas.height}")
    return out


def main():
    ap = argparse.ArgumentParser(description="批量裁剪与标注截图")
    ap.add_argument("--config", default="project.json", help="project.json 路径")
    ap.add_argument("--only", default="", help="只处理 out 文件名包含此关键字的图片")
    args = ap.parse_args()

    cfg_path = os.path.abspath(args.config)
    if not os.path.exists(cfg_path):
        print(f"[FAIL] 配置不存在：{cfg_path}")
        return 1
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)

    base_dir = os.path.dirname(cfg_path)
    images = cfg.get("images") or []
    if not images:
        print("[WARN] project.json 里没有 images 配置")
        return 2

    ok = 0
    for item in images:
        if args.only and args.only not in (item.get("out") or ""):
            continue
        print(f"[PROCESS] {item.get('src')}")
        if process(item, base_dir):
            ok += 1

    print(f"[DONE] {ok}/{len(images)} 张处理成功")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
