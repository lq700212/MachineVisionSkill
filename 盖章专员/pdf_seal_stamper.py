#!/usr/bin/env python3
"""
PDF 公章添加工具 (PDF Seal Stamper) v1.0.0
=========================================
自动将公章盖到 PDF 合同上。智能定位（默认开启）：OCR 识别公章公司名，自动匹配
合同里该公司是甲方/乙方/卖方/买方等哪个角色，精准盖到该角色的盖章处；盖完自动
压平，公章与页面融为一体、不可被编辑软件单独编辑。

核心逻辑:
    1. 智能定位（默认）：OCR 公章公司名 → 匹配合同"角色: 公司名" → 定位该角色
       盖章处；任一步失败自动回退常规定位（参考章对称 → 关键词 → 默认位置）
    2. 从 PDF 中提取参考公章图片，用红色检测裁剪内容区域，按内容占比换算实际
       视觉大小（pts），确保新章与参考章视觉一致
    3. 裁剪新公章图片，去除透明 padding；RGB/JPG 自动转透明背景防白底遮挡
    4. 支持旋转角度（默认逆时针 20°），模拟真实盖章效果
    5. 压平防编辑（默认开启）：盖章页整页栅格化 + 重建隐形文字层，公章与页面
       融为一体，编辑软件无法单独选中/移动/删除公章；文字仍可搜索/复制

用法:
    python3 pdf_seal_stamper.py <合同PDF> [公章图片] [输出PDF] [选项]

参数:
    合同PDF       - 待盖章的合同 PDF 文件路径
    公章图片      - （可选）要添加的公章图片（支持 PNG/JPEG），默认使用脚本同目录下的"默认公章图片.png"
    输出PDF       - （可选）输出 PDF 文件路径，默认在原合同名后加"_已盖章"

选项:
    --side left|right    - 常规定位时新公章放在参考公章的左侧还是右侧，默认 right
    --rotate N           - 旋转角度（度），正值为逆时针，负值为顺时针，默认 20
    --offset-x N         - 水平偏移（pts），正值向右
    --offset-y N         - 垂直偏移（pts），正值向下
    --no-auto            - 关闭智能定位，回退常规定位
    --company 公司名     - 手动指定公章上的公司名（OCR 识别不准时兜底）
    --role 角色名        - 手动指定盖到哪个角色的盖章处（如 甲方/乙方/卖方/买方）
    --no-flatten         - 不压平，公章保留为独立图片对象（可被编辑软件选中修改，
                           有法律风险，仅应急/内部核对用）
    --dpi N              - 压平渲染分辨率，默认 300（越高越清晰、文件越大）
    --dry-run            - 只分析不生成，显示检测到的公章信息

示例:
    python3 pdf_seal_stamper.py contract.pdf
    python3 pdf_seal_stamper.py contract.pdf seal.png
    python3 pdf_seal_stamper.py contract.pdf seal.png output.pdf
    python3 pdf_seal_stamper.py contract.pdf seal.png --role 乙方
    python3 pdf_seal_stamper.py contract.pdf --rotate -15 --dry-run
"""

import argparse
import importlib.util
import os
import re
import subprocess
import sys
import io
import tempfile
from difflib import SequenceMatcher

# ============================================================
# 依赖自检与自动安装（启动时执行，先于第三方 import）
# 原则：核心依赖缺失→自动安装（国内镜像加速），装不上才退出并给手动命令；
#       智能定位依赖（OCR）缺失→自动安装，装不上不阻塞（智能定位自动降级）。
# ⚠️ 新增第三方依赖时必须登记到下面两张表，否则自动安装机制对它无效。
# ============================================================

PIP_MIRROR_ARGS = ["-i", "https://mirrors.aliyun.com/pypi/simple/",
                   "--trusted-host", "mirrors.aliyun.com"]

REQUIRED_DEPENDENCIES = [
    # (import 名, pip 包名)
    ("numpy", "numpy"),
    ("PIL", "pillow"),
    ("scipy", "scipy"),
    ("fitz", "pymupdf"),
    ("pypdf", "pypdf"),
    ("pdfplumber", "pdfplumber"),
    ("reportlab", "reportlab"),
]

OPTIONAL_DEPENDENCIES = [
    ("rapidocr_onnxruntime", "rapidocr_onnxruntime"),
    ("cv2", "opencv-python"),
]


def _missing(mod_name):
    return importlib.util.find_spec(mod_name) is None


def ensure_dependencies():
    missing = [(m, p) for m, p in REQUIRED_DEPENDENCIES + OPTIONAL_DEPENDENCIES
               if _missing(m)]
    if not missing:
        return
    print("🔍 首次运行依赖自检：缺少 " + ", ".join(p for _, p in missing))
    print("   自动安装中（阿里镜像源）...")
    still_missing = []
    for mod, pip_name in missing:
        r = subprocess.run([sys.executable, "-m", "pip", "install", pip_name] + PIP_MIRROR_ARGS,
                           capture_output=True, text=True)
        if _missing(mod):
            still_missing.append((mod, pip_name))
            print(f"  ⚠️  {pip_name} 自动安装失败")
    core_missing = [p for m, p in still_missing if (m, p) in REQUIRED_DEPENDENCIES]
    if core_missing:
        print("❌ 核心依赖自动安装失败，请手动执行后重试：")
        print(f"   pip install {' '.join(core_missing)} "
              f"{' '.join(PIP_MIRROR_ARGS)}")
        sys.exit(1)
    if still_missing:
        print("  ℹ️  智能定位依赖（OCR）不可用，本次运行将自动降级为常规定位；"
              "盖章主流程不受影响")


ensure_dependencies()

import fitz  # pymupdf
import numpy as np
from PIL import Image
from pypdf import PdfReader, PdfWriter
import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


# ============================================================
# 图片裁剪函数
# ============================================================

def crop_seal_rgba(pil_image):
    """RGBA 图片：用 alpha 通道裁剪"""
    alpha = np.array(pil_image.split()[3])
    mask = alpha > 10
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    if rows.any() and cols.any():
        rmin, rmax = np.where(rows)[0][[0, -1]]
        cmin, cmax = np.where(cols)[0][[0, -1]]
        return pil_image.crop((cmin, rmin, cmax + 1, rmax + 1))
    return pil_image


def rgb_to_transparent_rgba(pil_image):
    """
    将 RGB 公章图片转为透明背景 RGBA。
    用红色检测识别公章内容区域，非公章区域设为透明。
    返回 RGBA 模式的 PIL Image。
    """
    arr = np.array(pil_image).astype(np.float32)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

    # 红色区域：R 通道明显大于 G 和 B（与旧版裁剪阈值一致）
    red_mask = (r > 120) & (r > g * 1.3) & (r > b * 1.3)
    # 深色文字区域：公章文字/边框
    dark_mask = (r < 150) & (g < 150) & (b < 150) & (r > 30)
    seal_mask = red_mask | dark_mask

    # 对 mask 做轻微膨胀 + 高斯模糊，让边缘过渡更自然
    from scipy import ndimage
    seal_mask_uint8 = seal_mask.astype(np.uint8) * 255

    # 轻微膨胀 1px 填充边缘
    seal_mask_uint8 = ndimage.binary_dilation(seal_mask_uint8, iterations=1).astype(np.uint8) * 255

    # 高斯模糊 1.5px 让边缘柔和
    alpha = ndimage.gaussian_filter(seal_mask_uint8.astype(np.float32), sigma=1.5)
    alpha = np.clip(alpha, 0, 255).astype(np.uint8)

    # 组装 RGBA
    rgba = np.dstack([
        arr[:, :, 0].astype(np.uint8),
        arr[:, :, 1].astype(np.uint8),
        arr[:, :, 2].astype(np.uint8),
        alpha,
    ])
    return Image.fromarray(rgba, 'RGBA')


def crop_seal_rgb(pil_image):
    """RGB 图片：先转为透明 RGBA，再用 alpha 通道裁剪"""
    transparent = rgb_to_transparent_rgba(pil_image)
    return crop_seal_rgba(transparent)


def crop_seal_content(pil_image):
    """统一裁剪接口"""
    if pil_image.mode == 'RGBA':
        return crop_seal_rgba(pil_image)
    elif pil_image.mode == 'RGB':
        return crop_seal_rgb(pil_image)
    return pil_image


# ============================================================
# PDF 分析函数
# ============================================================

def analyze_pdf_seals(pdf_path):
    """
    分析 PDF 中所有图片，识别公章（红色圆形印章）。
    返回 list[dict]
    """
    results = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            for img_idx, img in enumerate(page.images):
                w, h = img['width'], img['height']
                x0, top = img['x0'], img['top']
                x1, bottom = img['x1'], img['bottom']

                is_seal = (
                    abs(w - h) < 30 and
                    w > 50 and h > 50 and
                    w < 250 and h < 250
                )

                stream = img.get('stream', {})
                results.append({
                    'index': len(results),
                    'page': page_idx + 1,
                    'page_width': page.width,
                    'page_height': page.height,
                    'x0': x0, 'y0': top,
                    'x1': x1, 'y1': bottom,
                    'width': w, 'height': h,
                    'center_x': (x0 + x1) / 2,
                    'center_y': (top + bottom) / 2,
                    'pixel_width': stream.get('Width', 0),
                    'pixel_height': stream.get('Height', 0),
                    'is_seal': is_seal,
                    'name': img.get('name', f'img_{img_idx}'),
                })

    return results


def find_keyword_blocks(pdf_path, keywords, cluster_distance=100, max_word_width=200):
    """
    在 PDF 中搜索包含关键词的文字块，用于定位盖章位置。

    参数:
        pdf_path: PDF 文件路径
        keywords: 关键词列表，如 ['签章', '公章', '盖章']
        cluster_distance: 聚类距离（pts），用于将附近的关键词归为同一文字块
        max_word_width: 关键词词语的最大宽度（pts），超过此宽度的视为正文行，予以过滤

    返回:
        list[dict]: 每个文字块的信息，包含 page, x0, y0, x1, y1, center_x, center_y, side, keywords_found 等
    """
    blocks = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            all_words = page.extract_words()
            if not all_words:
                continue

            # 找到包含关键词的词语，过滤掉过宽的正文行
            kw_words = []
            for w in all_words:
                word_width = w['x1'] - w['x0']
                if word_width > max_word_width:
                    continue  # 过滤正文长行
                for kw in keywords:
                    if kw in w['text']:
                        kw_words.append(w)
                        break

            if not kw_words:
                continue

            # 将距离较近的关键词聚类为同一文字块
            clusters = []
            used = set()

            for i in range(len(kw_words)):
                if i in used:
                    continue
                cluster = [kw_words[i]]
                used.add(i)

                # 扩展聚类：找到与聚类中任一词语接近的其他关键词
                changed = True
                while changed:
                    changed = False
                    for j in range(len(kw_words)):
                        if j in used:
                            continue
                        for cw in cluster:
                            dx = abs((kw_words[j]['x0'] + kw_words[j]['x1']) / 2 -
                                     (cw['x0'] + cw['x1']) / 2)
                            dy = abs((kw_words[j]['top'] + kw_words[j]['bottom']) / 2 -
                                     (cw['top'] + cw['bottom']) / 2)
                            if dx < cluster_distance * 2 and dy < cluster_distance:
                                cluster.append(kw_words[j])
                                used.add(j)
                                changed = True
                                break

                clusters.append(cluster)

            # 计算每个聚类的包围盒
            for cluster_words in clusters:
                min_x = min(w['x0'] for w in cluster_words)
                max_x = max(w['x1'] for w in cluster_words)
                min_y = min(w['top'] for w in cluster_words)
                max_y = max(w['bottom'] for w in cluster_words)

                center_x = (min_x + max_x) / 2
                side = 'left' if center_x < page.width / 2 else 'right'

                blocks.append({
                    'page': page_idx + 1,
                    'x0': min_x,
                    'y0': min_y,
                    'x1': max_x,
                    'y1': max_y,
                    'center_x': center_x,
                    'center_y': (min_y + max_y) / 2,
                    'width': max_x - min_x,
                    'height': max_y - min_y,
                    'side': side,
                    'page_width': page.width,
                    'page_height': page.height,
                    'keywords_found': [w['text'] for w in cluster_words],
                })

    return blocks


def extract_ref_seal_from_pdf(pdf_path, seal_info):
    """
    从 PDF 中提取参考公章的原始图片数据，并裁剪内容区域。
    返回 (cropped_pil_image, crop_ratio_w, crop_ratio_h)
    其中 crop_ratio = 裁剪后内容像素 / 原始图片像素
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[seal_info['page'] - 1]
        images = page.get_images(full=True)

        # 找到匹配的图片（通过像素尺寸匹配）
        target_pw = seal_info['pixel_width']
        target_ph = seal_info['pixel_height']

        for img_info in images:
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            if (base_image['width'] == target_pw and
                    base_image['height'] == target_ph):
                # 找到了！
                pil_img = Image.open(io.BytesIO(base_image['image']))
                original_w, original_h = pil_img.size
                cropped = crop_seal_content(pil_img)
                crop_w, crop_h = cropped.size

                ratio_w = crop_w / original_w if original_w > 0 else 1.0
                ratio_h = crop_h / original_h if original_h > 0 else 1.0

                doc.close()
                return cropped, ratio_w, ratio_h

        doc.close()
    except Exception as e:
        print(f"  ⚠️  提取参考公章图片失败: {e}")

    return None, 1.0, 1.0


# ============================================================
# 防编辑压平
# ============================================================

def flatten_stamped_page(pdf_path, page_number, dpi=300, jpeg_quality=92):
    """
    将盖章页压平为"整页位图 + 隐形文字层"，使公章与页面融为一体、不可单独编辑。

    为什么需要压平（根因）：
        步骤5的叠加方式会把公章作为独立图片 XObject 写进页面，PDF 编辑软件
        （Acrobat/福昕/WPS 等）可以把它单独选中、移动、删除——有法律风险。
        压平后整页视觉内容变成一张位图，公章成为页面像素的一部分，
        任何编辑器都无法把公章作为独立对象操作。

    做法：
        1. 盖章页按 dpi 渲染为位图（JPEG 压缩，体积可控）
        2. 提取该页原有文字 page.get_text("words")
        3. 重建该页：插入整页位图 + 以 render_mode=3（隐形）重排原文字
           → 视觉 100% 来自位图；文字层仍在（可搜索/可复制），只是不可见不可改
        4. 其余页经 insert_pdf 原样保留，不压平、页数页序不变
    """
    # 坐标系说明：此处 fitz 的 words/rect 均为顶部原点坐标系，重建页面也用
    # fitz 顶部原点坐标系，全程无跨界换算
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_number - 1]
        page_rect = page.rect
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        # 经 PIL 编码 JPEG：质量参数可控，且不依赖 pymupdf 版本的 tobytes 扩展
        stride = getattr(pix, "stride", pix.width * 3)
        pil_img = Image.frombuffer("RGB", (pix.width, pix.height), pix.samples,
                                   "raw", "RGB", stride, 1)
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=jpeg_quality)
        page_jpeg = buf.getvalue()
        words = page.get_text("words")
    finally:
        doc.close()

    src = fitz.open(pdf_path)
    out = fitz.open()
    try:
        for i in range(len(src)):
            if i == page_number - 1:
                new_page = out.new_page(width=page_rect.width, height=page_rect.height)
                new_page.insert_image(new_page.rect, stream=page_jpeg)
                # 重建隐形文字层：按原词位置重排，render_mode=3 完全不可见
                for w in words:
                    x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
                    if not text.strip():
                        continue
                    fontsize = max(y1 - y0, 1.0)
                    # 基线近似取词框底部略上；隐形文字层只求可搜索复制，不求逐像素对齐
                    try:
                        new_page.insert_text(
                            fitz.Point(x0, y1 - fontsize * 0.18), text,
                            fontsize=fontsize, fontname="china-s",
                            render_mode=3)
                    except Exception:
                        # 个别词字符不支持时跳过，不影响整页压平
                        continue
            else:
                out.insert_pdf(src, from_page=i, to_page=i)
        out_bytes = out.tobytes(garbage=3, deflate=True)
    finally:
        out.close()
        src.close()

    # 原子替换输出文件（Windows 瞬时文件锁重试见 _write_bytes_retry）
    tmp_path = pdf_path + ".flattening.tmp"
    _write_bytes_retry(tmp_path, out_bytes)
    os.replace(tmp_path, pdf_path)


# ============================================================
# 智能定位：公章 OCR + 合同角色匹配
# 链路：公章图 → 极坐标展开(环形文字拉直) → rec-only 分段识别
#       → 清洗出公司名 → 与合同"角色:公司名"对匹配 → 定位该角色盖章处
# ============================================================

# 无参考章时的默认章宽(pts)：定位合成块与碰撞检查共用，勿双写魔数（曾各写125失同步）
SEAL_DEFAULT_SIZE = 125.0
# 公章图片上的组织名称后缀（截断噪声用）
_ORG_SUFFIXES = ("公司", "厂", "中心", "事务所", "研究院", "研究所", "大学",
                 "学院", "医院", "银行", "集团", "合作社", "营业部", "经营部")
# 噪声词：识别出的文本含这些词的片段不是公司名
_NOISE_WORDS = ("合同专用章", "专用章", "公章", "印章", "财务专用章", "发票专用章",
                "合同章", "检验", "编号")
# 合同常见签署角色（按需可扩充）
_CONTRACT_ROLES = ("甲方", "乙方", "丙方", "丁方", "卖方", "买方", "供方", "需方",
                   "出租方", "承租方", "发包方", "承包方", "发包人", "承包人",
                   "委托方", "受托方", "委托人", "受托人", "招标人", "投标人",
                   "借款人", "贷款人", "用人单位", "劳动者")
# 行内"角色:公司名"正则（容忍角色内空格、括注、全半角冒号）。
# 角色后允许 0~4 字修饰（"买方名称 ：""供方单位："等真实合同写法），但 group(1)
# 只捕获角色词本身——修饰词进了 role 会污染后续所有搜索关键词（曾犯）。
# 公司名部分用字符级 negative-lookahead 断言：一旦走到下一个"角色…："序列立即停。
# 为什么不用可选组+lookahead：空公司名栏（"买方名称 ："后空白，后跟"卖方名称 ："）
# 会因回溯把下一段整段吞成本栏公司名（曾致匹配错角色、章盖到对方签字栏）。
# 改用本写法后空栏直接整体匹配失败（空栏本就不该提取出签署方）。
_ROLE_MOD = r"[名称单位]{0,4}\s*(?:[（(][^（）()]{0,12}[）)])?\s*[：:]"
_ROLE_HEAD = "(?:" + "|".join(_CONTRACT_ROLES) + r")" + _ROLE_MOD
_PARTY_LINE_RE = re.compile("(" + "|".join(_CONTRACT_ROLES) + r")" + _ROLE_MOD
                            + r"\s*((?:(?!" + _ROLE_HEAD + ").)+)")


def _write_bytes_retry(path, data, attempts=4, delay=0.5):
    """Windows 下目标文件可能被杀毒/索引/预览窗格瞬时锁住（PermissionError，
    曾偶发致整个盖章失败），重试写出。所有最终 PDF 落盘必须走这里。"""
    import time
    for attempt in range(attempts):
        try:
            with open(path, "wb") as f:
                f.write(data)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


def _lazy_ocr_engine():
    """懒加载 rec-only 识别引擎；OCR 依赖不可用返回 None（智能定位自动降级）"""
    try:
        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR(use_text_det=False, use_cls=False)
    except Exception:
        return None


def _imread_bgr(path):
    """cv2.imread 不支持中文路径，经 PIL 中转（RGB→BGR）"""
    pil = Image.open(path).convert("RGB")
    import cv2
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def _red_mask(bgr):
    r = bgr[:, :, 2].astype(int)
    g = bgr[:, :, 1].astype(int)
    b = bgr[:, :, 0].astype(int)
    return (r > 120) & (r > g * 1.3) & (r > b * 1.3)


def _polar_unwrap(bgr, start_deg, band=(0.58, 0.92), out_w=2400):
    """以红像素质心为圆心做极坐标展开，把环形排列的公司名拉直成横排。
    轴向关键（曾因写反而整行镜像）：输出顶行=外半径（字头朝外的公章文字展开后正立），
    列=角度顺时针。start_deg 为展开缝的起始角，用于多起始角避开文字被切断。"""
    import cv2
    red = _red_mask(bgr)
    ys, xs = np.nonzero(red)
    if ys.size < 100:
        return None
    cy, cx = ys.mean(), xs.mean()
    max_r = np.sqrt(((ys - cy) ** 2 + (xs - cx) ** 2).max())
    r0, r1 = max_r * band[0], max_r * band[1]
    us = np.arange(out_w, dtype=np.float32)
    vs = np.arange(max(int(r1 - r0), 40), dtype=np.float32)
    theta = start_deg + (us / out_w) * 2 * np.pi
    rr = r1 - (r1 - r0) * (vs / vs.size)  # 顶行=外半径
    tt, rgrid = np.meshgrid(theta, rr)
    map_x = (cx + rgrid * np.cos(tt)).astype(np.float32)
    map_y = (cy + rgrid * np.sin(tt)).astype(np.float32)
    return cv2.remap(bgr, map_x, map_y, cv2.INTER_LINEAR)


def _crop_main_text_row(flat):
    """展开图中按红像素垂直投影裁出主文字行（公司名行是红像素最多的行带）"""
    import cv2
    red = _red_mask(flat)
    counts = red.sum(axis=1).astype(float)
    if counts.max() < 20:
        return None
    peak = int(counts.argmax())
    thr_lo = counts.max() * 0.08
    top = peak
    while top > 0 and counts[top - 1] > thr_lo:
        top -= 1
    bot = peak
    while bot < len(counts) - 1 and counts[bot + 1] > thr_lo:
        bot += 1
    return flat[top:bot + 1]


def _rec_line_segments(rec_only, line_img, seg_chars=7):
    """行图缩到高48px后按字间隙切段分别 rec 再顺序拼接。
    为什么要切：rec 输入宽度被压到 ~320px，整行十几字会被压扁丢字（实测只出前8字）。
    为什么按字间隙切：等宽硬切会把字切成两半导致识别错字（实测"光电"→"光中"），
    在红像素列投影的空隙处下刀保证每段都是完整字，拼接无需去重。"""
    import cv2
    h, w = line_img.shape[:2]
    if h < 8 or w < 32:
        return ""
    scale = 48.0 / h
    line48 = cv2.resize(line_img, (max(int(w * scale), 32), 48))
    W = line48.shape[1]
    seg_w = 48 * seg_chars
    if W <= seg_w * 1.2:
        res, _ = rec_only(line48)
        return res[0][1] if res else ""
    red = _red_mask(line48)
    col = red.sum(axis=0).astype(float)
    gap_thr = max(col.max() * 0.06, 1.0)
    is_gap = col <= gap_thr

    def nearest_gap(target, lo, hi):
        cands = [i for i in range(max(lo, 0), min(hi, W)) if is_gap[i]]
        return min(cands, key=lambda i: abs(i - target)) if cands else target

    pieces = []
    cur = 0
    while cur < W:
        end_target = cur + seg_w
        if end_target >= W - 24:      # 剩余不足一字的宽度并入本段
            end = W
        else:
            end = nearest_gap(end_target, cur + seg_w - 24, cur + seg_w + 24)
        seg = line48[:, cur:end]
        if seg.shape[1] >= 8:
            res, _ = rec_only(seg)
            if res:
                pieces.append(res[0][1])
        cur = end
    return "".join(pieces)


def _clean_company_text(text):
    """清洗 OCR/合同里的公司名：去噪声词、截断到组织后缀、去尾部标点"""
    if not text:
        return None
    for w in _NOISE_WORDS:
        text = text.replace(w, "")
    text = re.sub(r"（以下简称[^）]*）|\([^)]*简称[^)]*\)", "", text)
    text = re.sub(r"[0-9A-Za-z]{4,}$", "", text)          # 尾部防伪码/编号
    text = re.sub(r"^[\s\-—·:：,，。;；]+|[\s\-—·,，。;；]+$", "", text)
    # 截断到最后一个组织后缀的末尾（"…科技有限公司860"→"…科技有限公司"）
    cut = -1
    for suf in _ORG_SUFFIXES:
        pos = text.rfind(suf)
        if pos >= 0:
            cut = max(cut, pos + len(suf))
    if cut > 0:
        text = text[:cut]
    text = text.strip()
    if len(text) < 4:
        return None
    if not any("\u4e00" <= ch <= "\u9fff" for ch in text):
        return None  # 纯数字/字母（电话、账号、编号）不是公司名
    return text


def ocr_seal_company(seal_image_path, rec_only):
    """OCR 公章图片，返回清洗后的公司名（识别不出返回 None）。
    多起始角展开：环形文字被展开缝切断时换角即可完整；结果投票取最稳。"""
    raw_candidates = []
    try:
        bgr = _imread_bgr(seal_image_path)
    except Exception as e:
        print(f"  ⚠️  公章图片读取失败: {e}")
        return None
    for start in (0, 90, 180, 270):
        flat = _polar_unwrap(bgr, np.deg2rad(start))
        if flat is None:
            continue
        line = _crop_main_text_row(flat)
        if line is None:
            continue
        text = _rec_line_segments(rec_only, line)
        cleaned = _clean_company_text(text)
        if cleaned:
            raw_candidates.append(cleaned)
    if not raw_candidates:
        return None
    # 投票：出现次数最多 → 平票按候选质量评分决胜。
    # 为什么不用"平票取最长"：带噪声的候选（展开缝切进的杂字/防伪数字）往往更长，
    # 实测会击败干净候选；含完整组织后缀+汉字占比高的候选才是公司名（曾犯）。
    counter = {}
    for c in raw_candidates:
        counter[c] = counter.get(c, 0) + 1

    def _score(t):
        s = 0.0
        if any(suf in t for suf in _ORG_SUFFIXES):
            s += 10.0
            if t.endswith(_ORG_SUFFIXES):
                s += 3.0
        s += 10.0 * sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff") / max(len(t), 1)
        if 6 <= len(t) <= 20:
            s += 2.0
        return s

    best = sorted(counter.items(), key=lambda kv: (kv[1], _score(kv[0])), reverse=True)
    return best[0][0]


def extract_contract_parties(pdf_path):
    """逐页逐行提取合同签署方："角色: 公司名"对。
    返回 [{role, company, page}, ...]；提取不到返回空列表。

    两个真实合同踩坑点（已固化）：
    1. 角色栏常带修饰词（"买方名称 ："），正则需容忍角色后跟 0~4 字修饰；
    2. 一行常有多个"角色：公司名"对（"需方： A 供方： B"），必须 finditer 全取
       并在每个公司名于下一个角色词处截断——match 整行贪婪会把两个公司名粘成
       一个，导致"供方"的公司名里混着"苏州华际…"而误匹配（曾犯）。"""
    parties = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            for line in text.splitlines():
                for m in _PARTY_LINE_RE.finditer(line):
                    role = m.group(1)
                    company = _clean_company_text(m.group(2))
                    if company:
                        parties.append({"role": role, "company": company,
                                        "page": page_idx + 1})
    return parties


def match_seal_to_party(company, parties):
    """公章公司名 ↔ 合同签署方模糊匹配（OCR 可能有错字，容忍单字差异）。
    返回最佳 party 或 None。判定：互相包含，或相似度 ≥ 0.55。"""
    if not company or not parties:
        return None
    best, best_score = None, 0.0
    for p in parties:
        a, b = company, p["company"]
        if a in b or b in a:
            score = 1.0
        else:
            score = SequenceMatcher(None, a, b).ratio()
        if score > best_score:
            best, best_score = p, score
    if best and best_score >= 0.55:
        return best
    return None


# 裸签章栏关键词（"签章： 签章："订购单式/盖章/公章，全半角冒号），多策略共用
_SEALMARK_KWS = ("签章：", "签章:", "盖章：", "盖章:", "公章：", "公章:")


def find_role_stamp_block(pdf_path, role, company=None):
    """定位合同中"该角色的盖章处"，三级策略逐级降级（返回 block 或 None）。

    真实合同的三种签署区形态（缺一不可，全部实测）：
    1. 明确盖章栏："需方(签章)：" / "甲方（盖章）：" —— 全半角括号、盖章/公章/签章
       三种叫法都要搜（曾只搜"盖章"导致"需方(签章)"漏检）；
    2. 裸签章栏+列对齐："签章：  签章："（订购单常见，签署栏不带角色名）——用角色
       文字块与裸签章块**同列配对**；必须排除属于其他角色的盖章栏（报价单只有
       "买方签字/盖章"，卖方的章绝不能盖过去）；
    3. 公司名同行："卖方名称：苏州华际…"（报价单卖方无盖章栏）——盖在公司名右侧。
    """
    # ---- 策略1：明确盖章栏 ----
    kws = []
    for mark in ("盖章", "公章", "签章"):
        kws += [f"{role}（{mark}", f"{role}({mark}", f"{role}{mark}"]
    blocks = find_keyword_blocks(pdf_path, kws)
    if blocks:
        max_page = max(b["page"] for b in blocks)
        return _pick_block(blocks, max_page), "明确盖章栏"

    # ---- 策略2：裸签章栏 + 角色列对齐（排除其他角色的盖章栏）----
    all_roles = list(_CONTRACT_ROLES)
    other_roles = [r for r in all_roles if r != role]
    sealmark_kws = _SEALMARK_KWS
    mark_blocks = [b for b in find_keyword_blocks(pdf_path, sealmark_kws)
                   if not any(r in "".join(b["keywords_found"]) for r in other_roles)]
    role_blocks = find_keyword_blocks(pdf_path, [role])
    if mark_blocks and role_blocks:
        max_page = max(b["page"] for b in mark_blocks)
        best, best_dist = None, None
        for mb in [b for b in mark_blocks if b["page"] == max_page]:
            # 只认角色块正下方（y 更大）且水平距离最近的配对
            above = [rb for rb in role_blocks
                     if rb["page"] == mb["page"] and rb["center_y"] < mb["center_y"]]
            if not above:
                continue
            rb = min(above, key=lambda r: abs(r["center_x"] - mb["center_x"]))
            dist = abs(rb["center_x"] - mb["center_x"])
            if best_dist is None or dist < best_dist:
                best, best_dist = mb, dist
        if best is not None and best_dist < best["page_width"] * 0.35:
            return best, "列对齐裸签章栏"

    # ---- 策略2.5：对侧对称（本角色无盖章栏，但其他角色的盖章栏存在）----
    # 真实习惯（用户口述+报价单实测校准）：买卖双方章上下对齐（同一水平带），
    # 水平位置取本角色关键字（"卖方开户行"/"卖方名称"）所在区域。
    # 实例：报价单"买方签字/盖章："y=392 在右，"卖方开户行：…"y=380 在左
    # → 章中心=(卖方关键字块x, 买方盖章栏y)，即日期附近的左侧区域。
    # ⚠️ 必须做碰撞避让（曾犯）：同模板两版文档底部布局可能不同——"剔除版"开户行
    # 行与买方盖章栏几乎同片区域，不避让会把章压到"买方签字/盖章"文字上。
    # 避让优先级：保持同高水平左移 > 垂直上移（用户偏好"上下对齐"优先保）。
    if other_marks := [b for b in find_keyword_blocks(pdf_path, sealmark_kws)
                       if any(r in "".join(b["keywords_found"]) for r in other_roles)]:
        max_page = max(b["page"] for b in other_marks)
        om = _pick_block([b for b in other_marks if b["page"] == max_page], max_page)
        role_blocks = find_keyword_blocks(pdf_path, [role])
        # 本角色关键字块中，取与他角色盖章栏同一水平带（±60pts）距离最近者
        band = om["page_height"] * 0.07  # 同高水平带宽度随页面尺寸缩放
        near = [rb for rb in role_blocks
                if rb["page"] == om["page"] and abs(rb["center_y"] - om["center_y"]) < band]
        if near:
            rb = min(near, key=lambda r: abs(r["center_y"] - om["center_y"]))
            half = SEAL_DEFAULT_SIZE / 2
            cx, cy = (rb["x0"] + rb["x1"]) / 2, om["center_y"]

            def _hits_other(ox, oy, pad=4):
                r = (ox - half, oy - half, ox + half, oy + half)
                return not (r[2] < om["x0"] - pad or r[0] > om["x1"] + pad or
                            r[3] < om["y0"] - pad or r[1] > om["y1"] + pad)

            if _hits_other(cx, cy):
                # 避让1：水平平移到他角色盖章栏左侧，保持同高
                cx2 = om["x0"] - 8 - half
                if cx2 - half > 0:
                    cx = cx2
                # 避让2：仍相交则垂直平移到他角色盖章栏上方
                if _hits_other(cx, cy):
                    cx = (rb["x0"] + rb["x1"]) / 2
                    cy = om["y0"] - 8 - half
            # 合成块=以目标中心为中心、章宽为宽的方块：保证定位走骑压分支精确落点
            synthetic = dict(rb)
            synthetic.update({
                "x0": cx - half, "x1": cx + half, "center_x": cx,
                "y0": cy - 10, "y1": cy + 10, "center_y": cy,
                "page": om["page"],
            })
            return synthetic, "对侧对称(与他角色盖章栏同高,本角色列)"

    # ---- 策略3：公司名同行（该角色无盖章栏时，盖在其公司名文字右侧）----
    if company:
        probe = company[:10]  # 公司名前10字做探针（整名可能因换行/空格断开）
        # 词宽放宽到400：表格栏"卖方名称：XX公司"整词常超默认200被滤（曾犯→策略失效）
        blocks = find_keyword_blocks(pdf_path, [probe], max_word_width=400)
        # 排除页眉抬头区（顶部10%，页眉公司名 center_y≈46/842）：页眉不是签署区。
        # 曾用12%误杀表格首行（报价单"卖方名称"行 center_y=96 与页眉高度重叠，曾犯）
        blocks = [b for b in blocks if b["center_y"] > b["page_height"] * 0.10]
        if blocks:
            max_page = max(b["page"] for b in blocks)
            # 取最靠下（内容尾部方向）的候选：越靠下越接近签署区
            same_page = [b for b in blocks if b["page"] == max_page]
            best = max(same_page, key=lambda b: b["center_y"])
            return best, "公司名同行(无该角色盖章栏,建议人工确认)"

    return None, None


def _pick_block(blocks, max_page):
    """同页多个候选块时：左侧优先（与常规定位偏好一致）"""
    same_page = [b for b in blocks if b["page"] == max_page]
    same_page.sort(key=lambda b: b["center_x"])
    return same_page[0]


def build_forbidden_zones(pdf_path, my_role, my_company):
    """动态构建落点禁忌区——所有定位策略共用的"动态判断"层，适配任意文档布局：
      1) 其他角色的盖章/签字栏（章绝不能压对方的盖章栏文字）
      2) 其他角色公司名的文字位置（章压到对方公司名上法律观感极差）
    盖章骑压"本角色"的锚点文字（自己的盖章栏/公司名/开户行）是真实习惯，属合法，
    故不在禁忌区内。返回 [(x0,y0,x1,y1), ...]（顶部原点坐标）。
    文本层缺失（扫描件）时各搜索自然为空 → 禁忌区为空 → 避让自动跳过（诚实降级）。"""
    zones = []
    other_roles = [r for r in _CONTRACT_ROLES if r != my_role]
    for b in find_keyword_blocks(pdf_path, _SEALMARK_KWS):
        if any(r in "".join(b["keywords_found"]) for r in other_roles):
            zones.append((b["x0"], b["y0"], b["x1"], b["y1"]))
    if my_company:
        for p in extract_contract_parties(pdf_path):
            if p["role"] == my_role:
                continue
            # 同一公司挂在两个角色栏下（罕见）不构成禁忌
            if p["company"] in my_company or my_company in p["company"]:
                continue
            for b in find_keyword_blocks(pdf_path, [p["company"][:10]],
                                         max_word_width=400):
                zones.append((b["x0"], b["y0"], b["x1"], b["y1"]))
    return zones


def adjust_avoid_forbidden(cx, cy, half_w, half_h, forbidden, page_w, page_h):
    """落点禁忌区动态避让：章矩形与任一禁忌区相交时，以锚点为中心按半章宽步长
    网格搜索最近的无碰撞位置（纯水平避让优先——尽量保住"同高对齐"等已有偏好，
    范围±1.5章宽）；搜索不到返回原位由调用方警告人工确认。
    返回 (cx, cy, moved)。"""
    def hits(ox, oy):
        r = (ox - half_w, oy - half_h, ox + half_w, oy + half_h)
        for z in forbidden:
            if not (r[2] < z[0] - 4 or r[0] > z[2] + 4 or
                    r[3] < z[1] - 4 or r[1] > z[3] + 4):
                return True
        return False

    if not forbidden or not hits(cx, cy):
        return cx, cy, False
    step = max(half_w, 10)
    span = max(int(1.5 * half_w * 2 / step), 1)
    best = None
    for dy in range(0, span + 1):
        for dx in range(0, span + 1):
            for sx in ({0} if dx == 0 else (-1, 1)):
                for sy in ({0} if dy == 0 else (-1, 1)):
                    nx, ny = cx + sx * dx * step, cy + sy * dy * step
                    if (nx - half_w < 8 or ny - half_h < 8 or
                            nx + half_w > page_w - 8 or ny + half_h > page_h - 8):
                        continue
                    if not hits(nx, ny):
                        d = dx * dx + dy * dy
                        if best is None or d < best[0]:
                            best = (d, nx, ny)
        if best:
            break
    if best:
        return best[1], best[2], True
    return cx, cy, False


# ============================================================
# 主处理函数
# ============================================================

def process_seal(pdf_path, seal_image_path, output_path=None,
                 side='right', rotate=20, offset_x=0, offset_y=0,
                 dry_run=False, keywords=None, flatten=True, dpi=300,
                 auto=True, company_hint=None, role_hint=None):
    """
    核心处理流程：
    1. 分析 PDF → 找到已有公章的位置和尺寸
    2. 智能定位（默认开启）→ OCR 公章公司名 → 匹配合同"角色:公司名"
       → 定位该角色盖章处；任一步失败自动回退常规定位
    3. 提取参考公章图片 → 裁剪内容区域，计算实际视觉大小
    4. 处理新公章 → 裁剪 padding，以参考公章内容实际视觉大小放置
    5. 计算位置 → 按对称/角色/关键词规则放置
    6. 生成覆盖层 → 合并到原始 PDF（支持旋转）
    7. 压平盖章页（默认开启）→ 公章不可被编辑软件单独编辑
    """
    print(f"合同 PDF:  {pdf_path}")
    print(f"公章图片:  {seal_image_path}")

    # ---- 步骤 1: 分析 PDF 中已有公章 ----
    print("\n" + "─" * 55)
    print("【步骤 1】分析 PDF 中已有公章")
    print("─" * 55)

    all_images = analyze_pdf_seals(pdf_path)
    existing_seals = [s for s in all_images if s['is_seal']]

    print(f"  检测到 {len(all_images)} 个图片，其中 {len(existing_seals)} 个被识别为公章：")
    for s in all_images:
        tag = "公章" if s['is_seal'] else "其他"
        print(f"    [{tag}] 位置=({s['x0']:.0f},{s['y0']:.0f})-({s['x1']:.0f},{s['y1']:.0f})  "
              f"尺寸={s['width']:.1f}x{s['height']:.1f} pts  "
              f"像素={s['pixel_width']}x{s['pixel_height']}")

    positioning_mode = 'seal'  # 定位模式: auto(=keyword计算) / seal / keyword / default

    # ---- 智能定位（auto 默认开启）：给一枚公章就知道盖哪 ----
    # 链路：OCR 公章公司名 → 匹配合同"角色: 公司名" → 定位该角色盖章处。
    # 任何一步失败只警告并回退常规定位，绝不阻塞盖章主流程。
    auto_matched = False
    if auto:
        print("\n  → 智能定位：识别公章公司名 → 匹配合同角色 → 定位该角色盖章处")
        role = role_hint
        company = None
        if role:
            print(f"  → 使用手动指定角色: {role}")
        else:
            rec_only = _lazy_ocr_engine()
            if company_hint:
                company = company_hint
                print(f"  → 使用手动指定公司名: {company}")
            elif rec_only is None:
                print("  ⚠️  OCR 依赖不可用且未指定 --company，无法识别公章公司名")
            else:
                company = ocr_seal_company(seal_image_path, rec_only)
                if company:
                    print(f"  → 公章公司名: {company}")
                else:
                    print("  ⚠️  公章公司名 OCR 失败（可人工看图后用 --company 指定）")

        party = None
        if role:
            party = {"role": role, "company": None}  # 手动角色无公司名，策略3不适用
        elif company:
            parties = extract_contract_parties(pdf_path)
            if parties:
                print("  → 合同签署方:")
                for p in parties:
                    print(f"      [{p['role']}] {p['company']} (第{p['page']}页)")
                party = match_seal_to_party(company, parties)
                if party:
                    print(f"  → 公章匹配到角色: {party['role']}（{party['company']}）")
                else:
                    print("  ⚠️  公章公司名与合同签署方均不匹配（相似度过低）")
            else:
                print("  ⚠️  合同未提取到'角色: 公司名'信息（可人工判断后用 --role 指定）")

        if party:
            block, strategy = find_role_stamp_block(
                pdf_path, party["role"], party.get("company"))
            if block:
                seal_size = SEAL_DEFAULT_SIZE
                reference = {
                    'x0': block['center_x'] - seal_size / 2,
                    'y0': block['center_y'] - seal_size / 2,
                    'x1': block['center_x'] + seal_size / 2,
                    'y1': block['center_y'] + seal_size / 2,
                    'width': seal_size,
                    'height': seal_size,
                    'center_x': block['center_x'],
                    'center_y': block['center_y'],
                    'page_width': block['page_width'],
                    'page_height': block['page_height'],
                    'page': block['page'],
                    'pixel_width': 0,
                    'pixel_height': 0,
                    'kw_x0': block['x0'],
                    'kw_y0': block['y0'],
                    'kw_x1': block['x1'],
                    'kw_y1': block['y1'],
                }
                positioning_mode = 'keyword'  # 定位计算与关键词模式相同：章左缘对齐文字右缘
                side_label = '左侧' if block['center_x'] < block['page_width'] / 2 else '右侧'
                print(f"  → 智能定位成功（策略：{strategy}）：{side_label}"
                      f"「{party['role']}」盖章处，第 {block['page']} 页")
                auto_matched = True
            else:
                print(f"  ⚠️  合同中未找到「{party['role']}」的盖章位置")

        if not auto_matched:
            print("  → 智能定位未成功，回退常规定位（参考章对称 → 关键词 → 默认）")

    if not auto_matched:
        if not existing_seals:
            positioning_mode = 'default'

            if keywords:
                print("\n  → 未检测到已有公章，尝试通过关键词定位...")
                kw_blocks = find_keyword_blocks(pdf_path, keywords)

                if kw_blocks:
                    # 按优先级排序：左侧优先，同侧页面从后往前
                    left_blocks = [b for b in kw_blocks if b['side'] == 'left']
                    right_blocks = [b for b in kw_blocks if b['side'] == 'right']
                    candidate_blocks = left_blocks + right_blocks

                    # 优先选择最后一页（签名通常在最后一页）
                    max_page = max(b['page'] for b in candidate_blocks)
                    candidate_blocks = [b for b in candidate_blocks if b['page'] == max_page]

                    if candidate_blocks:
                        block = candidate_blocks[0]  # 左侧优先
                        # 默认公章尺寸约 125 pts
                        seal_size = SEAL_DEFAULT_SIZE
                        reference = {
                            'x0': block['center_x'] - seal_size / 2,
                            'y0': block['center_y'] - seal_size / 2,
                            'x1': block['center_x'] + seal_size / 2,
                            'y1': block['center_y'] + seal_size / 2,
                            'width': seal_size,
                            'height': seal_size,
                            'center_x': block['center_x'],
                            'center_y': block['center_y'],
                            'page_width': block['page_width'],
                            'page_height': block['page_height'],
                            'page': block['page'],
                            'pixel_width': 0,
                            'pixel_height': 0,
                            # 关键词文字块的实际边界（用于定位）
                            'kw_x0': block['x0'],
                            'kw_y0': block['y0'],
                            'kw_x1': block['x1'],
                            'kw_y1': block['y1'],
                        }
                        positioning_mode = 'keyword'
                        side_label = '左侧' if block['side'] == 'left' else '右侧'
                        print(f"  → 关键词定位成功！匹配到{side_label}文字块: {block['keywords_found']}")
                        print(f"  → 文字区域: ({block['x0']:.0f}, {block['y0']:.0f}) → "
                              f"({block['x1']:.0f}, {block['y1']:.0f})")
                        print(f"  → 公章中心: ({block['center_x']:.1f}, {block['center_y']:.1f})")

            if positioning_mode == 'default':
                print("\n  ⚠️  关键词定位失败，使用默认位置（右下角签名区）。")
                reference = {
                    'x0': 255, 'y0': 485, 'x1': 382, 'y1': 610,
                    'width': 126.7, 'height': 124.2,
                    'center_x': 318.5, 'center_y': 547.5,
                    'page_width': 595.2, 'page_height': 841.9,
                    'page': 1, 'pixel_width': 0, 'pixel_height': 0,
                }
        else:
            reference = existing_seals[0]
            print(f"\n  → 参考公章: #{reference['index']} "
                  f"尺寸={reference['width']:.1f}x{reference['height']:.1f} pts")

    ref_w = reference['width']
    ref_h = reference['height']
    page_w = reference['page_width']
    page_h = reference['page_height']

    # ---- 步骤 2: 提取参考公章图片，分析内容区域 ----
    print("\n" + "─" * 55)
    print("【步骤 2】提取参考公章图片，分析内容区域")
    print("─" * 55)

    if existing_seals:
        ref_cropped_img, ref_ratio_w, ref_ratio_h = extract_ref_seal_from_pdf(
            pdf_path, reference)
        if ref_cropped_img:
            print(f"  参考公章原始像素: {reference['pixel_width']}x{reference['pixel_height']}")
            print(f"  参考公章内容像素: {ref_cropped_img.size[0]}x{ref_cropped_img.size[1]}")
            print(f"  内容占比: w={ref_ratio_w:.3f}, h={ref_ratio_h:.3f}")
            # 参考公章内容在 PDF 中的实际视觉大小
            ref_content_w = ref_w * ref_ratio_w
            ref_content_h = ref_h * ref_ratio_h
            print(f"  参考公章内容在 PDF 中的实际大小: {ref_content_w:.1f} x {ref_content_h:.1f} pts")
        else:
            print(f"  ⚠️  无法提取参考公章图片，使用渲染尺寸作为目标")
            ref_content_w = ref_w
            ref_content_h = ref_h
    else:
        ref_content_w = ref_w
        ref_content_h = ref_h

    # ---- 步骤 3: 确定目标位置 ----
    print("\n" + "─" * 55)
    print("【步骤 3】计算目标位置")
    print("─" * 55)

    if positioning_mode == 'keyword':
        # 关键词/智能定位：默认章左缘对齐关键词文字块右缘（右侧空白处）；
        # 长文字块（含公司名的签署行，块宽≥章宽90%）改骑压式——章中心骑在文字块上，
        # 模拟真实盖章压字。曾犯：对"需方(签章)：XX公司"长行仍外排，章被推出
        # 文本区贴页边（购销合同实测用户指出）。
        kw_x0 = reference.get('kw_x0', reference['x0'])
        kw_x1 = reference.get('kw_x1', reference['x1'])
        kw_y0 = reference.get('kw_y0', reference['y0'])
        kw_y1 = reference.get('kw_y1', reference['y1'])
        block_w = kw_x1 - kw_x0
        if block_w >= ref_content_w * 0.9:
            target_cx = (kw_x0 + kw_x1) / 2 + offset_x
            target_cy = reference['center_y'] + offset_y
            print(f"  文字块较宽（{block_w:.0f}pts），骑压式盖章（模拟真实压字）")
        else:
            target_cx = kw_x1 + ref_content_w / 2 + offset_x
            target_cy = reference['center_y'] + offset_y
            print(f"  公章左侧对齐文字右侧")
        mode_label = "智能定位（公章OCR→角色匹配）" if auto_matched else "关键词定位"
        print(f"  定位模式: {mode_label}")
        print(f"  关键词文字块: ({kw_x0:.1f}, {kw_y0:.1f}) → ({kw_x1:.1f}, {kw_y1:.1f})")
        print(f"  目标中心: ({target_cx:.1f}, {target_cy:.1f})")
    elif positioning_mode == 'seal':
        # 已有公章定位：对称计算
        if side == 'right':
            page_center = page_w / 2
            target_cx = page_center + (page_center - reference['center_x'])
            target_cy = reference['center_y']
        elif side == 'left':
            target_cx = reference['center_x']
            target_cy = reference['center_y']
        else:
            target_cx = reference['center_x']
            target_cy = reference['center_y']

        target_cx += offset_x
        target_cy += offset_y

        print(f"  参考公章中心: ({reference['center_x']:.1f}, {reference['center_y']:.1f})")
        print(f"  目标侧: {side}")
        print(f"  目标中心:   ({target_cx:.1f}, {target_cy:.1f})")
    else:
        # 默认定位
        if side == 'right':
            page_center = page_w / 2
            target_cx = page_center + (page_center - reference['center_x'])
            target_cy = reference['center_y']
        elif side == 'left':
            target_cx = reference['center_x']
            target_cy = reference['center_y']
        else:
            target_cx = reference['center_x']
            target_cy = reference['center_y']

        target_cx += offset_x
        target_cy += offset_y

        print(f"  参考位置中心: ({reference['center_x']:.1f}, {reference['center_y']:.1f})")
        print(f"  目标侧: {side}")
        print(f"  目标中心:   ({target_cx:.1f}, {target_cy:.1f})")

    # 页面边界保护（所有定位模式通用）：章任何情况下不得超出页面
    # （曾见购销合同章贴页边悬在文本区外，用户指出）
    edge = 8
    half_w, half_h = ref_content_w / 2, ref_content_h / 2
    clamped_cx = max(min(target_cx, page_w - edge - half_w), edge + half_w)
    clamped_cy = max(min(target_cy, page_h - edge - half_h), edge + half_h)
    if (clamped_cx, clamped_cy) != (target_cx, target_cy):
        print(f"  ⚠️  目标位置越界，已收进页面范围: ({clamped_cx:.1f}, {clamped_cy:.1f})")
    target_cx, target_cy = clamped_cx, clamped_cy

    # 落点禁忌区动态避让（所有智能定位策略共用的"动态判断"层）：
    # 现场计算"对方盖章栏/对方公司名"禁忌区，章压到就在锚点附近自动挪开。
    # 仅智能定位启用——回退模式无法确定"我方是谁"，无从构建禁忌区（保持警告交付）。
    if auto_matched:
        forbidden = build_forbidden_zones(pdf_path, party["role"], party.get("company"))
        ncx, ncy, moved = adjust_avoid_forbidden(
            target_cx, target_cy, ref_content_w / 2, ref_content_h / 2,
            forbidden, page_w, page_h)
        if moved:
            print(f"  ⚠️  落点压到他角色盖章栏/公司名，已自动避让: "
                  f"({target_cx:.0f},{target_cy:.0f}) → ({ncx:.0f},{ncy:.0f})")
            target_cx, target_cy = ncx, ncy

    # ---- 步骤 4: 处理新公章图片 ----
    print("\n" + "─" * 55)
    print("【步骤 4】处理新公章图片")
    print("─" * 55)

    new_seal = Image.open(seal_image_path)
    print(f"  原始图片: {new_seal.size[0]}x{new_seal.size[1]}, 模式={new_seal.mode}")

    if new_seal.mode == 'RGB':
        print(f"  → RGB 图片，转为透明背景 RGBA ...")
    cropped = crop_seal_content(new_seal)
    print(f"  裁剪后:   {cropped.size[0]}x{cropped.size[1]}, 模式={cropped.mode}")

    # 新公章以参考公章内容区域的实际视觉大小放置
    # 确保无论使用哪个公章图片，内容区域大小一致
    new_w = ref_content_w
    new_h = ref_content_h

    print(f"  目标放置尺寸（内容区域）: {new_w:.1f} x {new_h:.1f} pts")

    # 旋转角度
    print(f"  旋转角度: {rotate}°（{'逆时针' if rotate > 0 else '顺时针' if rotate < 0 else '无旋转'}）")

    if dry_run:
        print("\n" + "─" * 55)
        print("🔍 DRY RUN — 不生成文件，仅展示分析结果")
        print("─" * 55)
        print(f"\n如果执行，新公章将被放置在:")
        print(f"  位置: ({target_cx - new_w/2:.1f}, {target_cy - new_h/2:.1f})")
        print(f"  尺寸: {new_w:.1f} x {new_h:.1f} pts")
        print(f"  旋转: {rotate}°")
        return None

    # ---- 步骤 5: 生成最终 PDF ----
    print("\n" + "─" * 55)
    print("【步骤 5】生成最终 PDF")
    print("─" * 55)

    # 保存裁剪后的公章图片
    cropped_path = tempfile.mktemp(suffix='.png')
    cropped.save(cropped_path)

    # 创建叠加层 PDF（与原始 PDF 同尺寸，仅含公章）
    overlay_path = tempfile.mktemp(suffix='.pdf')
    c = canvas.Canvas(overlay_path, pagesize=(page_w, page_h))

    # 公章在 reportlab 坐标系中的中心位置（reportlab 原点在左下角）
    seal_center_x = target_cx
    seal_center_y = page_h - target_cy  # 转换：PDF 顶坐标 → reportlab 底坐标

    # 使用 saveState/restoreState 实现旋转
    c.saveState()
    c.translate(seal_center_x, seal_center_y)
    c.rotate(rotate)  # 正值为逆时针，负值为顺时针（向左旋转）
    # 绘制公章（以中心为原点）
    c.drawImage(cropped_path,
                -new_w / 2, -new_h / 2,
                width=new_w, height=new_h,
                mask='auto')
    c.restoreState()
    c.save()

    # 合并到原始 PDF
    reader_original = PdfReader(pdf_path)
    reader_overlay = PdfReader(overlay_path)
    writer = PdfWriter()

    for i, page in enumerate(reader_original.pages):
        if i == reference['page'] - 1:
            overlay_page = reader_overlay.pages[0]
            page.merge_page(overlay_page)
        writer.add_page(page)

    if output_path is None:
        base = os.path.splitext(pdf_path)[0]
        output_path = f"{base}_已盖章.pdf"

    buf = io.BytesIO()
    writer.write(buf)
    try:
        _write_bytes_retry(output_path, buf.getvalue())
    except PermissionError:
        # 目标被持续占用（资源管理器预览/杀软长扫描），换名落盘保证盖章不白跑
        import time as _time
        alt = f"{os.path.splitext(output_path)[0]}_{_time.strftime('%H%M%S')}.pdf"
        _write_bytes_retry(alt, buf.getvalue())
        output_path = alt
        print(f"  ⚠️  目标文件被其他程序占用，已改写到: {alt}")
        print("      （关闭占用它的程序如预览窗格后，可重命名为原输出名，或删除旧文件重跑）")

    # 清理临时文件
    os.unlink(cropped_path)
    os.unlink(overlay_path)

    # 实际位置（以 PDF 坐标系）
    seal_x = target_cx - new_w / 2
    seal_y = target_cy - new_h / 2

    print(f"  输出: {output_path}")
    print(f"  公章位置: ({seal_x:.1f}, {seal_y:.1f}) → "
          f"({seal_x + new_w:.1f}, {seal_y + new_h:.1f})")
    print(f"  公章尺寸: {new_w:.1f} x {new_h:.1f} pts")
    print(f"  旋转角度: {rotate}°")

    # ---- 步骤 6: 压平防编辑（默认开启）----
    print("\n" + "─" * 55)
    print("【步骤 6】压平防编辑")
    print("─" * 55)

    if flatten:
        flatten_stamped_page(output_path, reference['page'], dpi=dpi)
        print(f"  盖章页（第 {reference['page']} 页）已压平: "
              f"整页位图({dpi}dpi) + 隐形文字层（文字仍可搜索/复制）")
        print("  → 公章与页面融为一体，编辑软件无法单独选中/移动/删除公章")
    else:
        print("  ⚠️  未压平（--no-flatten）：公章仍是页面内独立图片对象，"
              "可被编辑软件选中/移动/删除，存在法律风险，仅限应急/内部核对使用")

    return output_path


# ============================================================
# 命令行入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='PDF 公章添加工具 v1.0.0 — 智能定位 + 防编辑压平',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 pdf_seal_stamper.py contract.pdf
  python3 pdf_seal_stamper.py contract.pdf seal.png
  python3 pdf_seal_stamper.py contract.pdf seal.png output.pdf
  python3 pdf_seal_stamper.py contract.pdf --rotate -15
  python3 pdf_seal_stamper.py contract.pdf --dry-run
        """
    )
    parser.add_argument('pdf', help='合同 PDF 文件路径')
    parser.add_argument('seal', nargs='?', default=None,
                        help='公章图片路径（可选，默认使用脚本同目录下的"默认公章图片.png"）')
    parser.add_argument('output', nargs='?', default=None, help='输出 PDF 路径（可选）')
    parser.add_argument('--side', choices=['left', 'right'], default='right',
                        help='放置侧（默认: right）')
    parser.add_argument('--rotate', type=float, default=20,
                        help='旋转角度（度），正值=逆时针（向左旋转），负值=顺时针，默认 20')
    parser.add_argument('--offset-x', type=float, default=0,
                        help='水平偏移 pts（正值=右移）')
    parser.add_argument('--offset-y', type=float, default=0,
                        help='垂直偏移 pts（正值=下移）')
    parser.add_argument('--dry-run', action='store_true',
                        help='仅分析，不生成文件')
    parser.add_argument('--no-flatten', action='store_true',
                        help='不压平，公章保留为独立图片对象（可被编辑软件选中修改，'
                             '有法律风险，仅应急/内部核对用）')
    parser.add_argument('--dpi', type=int, default=300,
                        help='压平渲染分辨率，默认 300（越高越清晰、文件越大）')
    parser.add_argument('--no-auto', action='store_true',
                        help='关闭智能定位（OCR识别公章→匹配合同角色），回退常规定位')
    parser.add_argument('--company', type=str, default=None,
                        help='手动指定公章上的公司名（OCR 识别不准时兜底）')
    parser.add_argument('--role', type=str, default=None,
                        help='手动指定盖到哪个角色的盖章处，如 甲方/乙方/卖方/买方'
                             '（跳过 OCR 与角色匹配）')
    parser.add_argument('--keywords', type=str, default='签章,公章,盖章',
                        help='常规定位的关键词，多个用逗号分隔（默认: 签章,公章,盖章）')

    args = parser.parse_args()

    # 解析关键词
    keywords = [kw.strip() for kw in args.keywords.split(',')]

    # 如果未指定公章，使用默认公章
    if args.seal is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        args.seal = os.path.join(script_dir, '默认公章图片.png')
        print(f"ℹ️  未指定公章图片，使用默认公章: {args.seal}")

    for path, name in [(args.pdf, '合同 PDF'), (args.seal, '公章图片')]:
        if not os.path.exists(path):
            print(f"❌ {name} 不存在: {path}")
            sys.exit(1)

    process_seal(
        pdf_path=args.pdf,
        seal_image_path=args.seal,
        output_path=args.output,
        side=args.side,
        rotate=args.rotate,
        offset_x=args.offset_x,
        offset_y=args.offset_y,
        dry_run=args.dry_run,
        keywords=keywords,
        flatten=not args.no_flatten,
        dpi=args.dpi,
        auto=not args.no_auto,
        company_hint=args.company,
        role_hint=args.role,
    )


if __name__ == '__main__':
    main()