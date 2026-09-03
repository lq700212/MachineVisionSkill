#!/usr/bin/env python3
"""
PDF 公章添加工具 (PDF Seal Stamper) v1.2.1
=========================================
自动将公章盖到合同文件上——支持文本版 PDF、扫描件 PDF（无文本层）、图片文件
（png/jpg/jpeg/bmp/webp）、Excel 工作簿（xlsx/xls/xlsm/xlsb）四类输入。
智能定位（默认开启）：OCR 识别公章公司名，自动匹配合同里该公司是
甲方/乙方/卖方/买方等哪个角色，精准盖到该角色的盖章处；盖完自动压平，公章与
页面融为一体、不可被编辑软件单独编辑。

扫描件/图片的处理设计（v1.1.0 新增）：不新写定位逻辑，而是先把输入规范化为
"整页位图 + OCR 隐形文字层"的 PDF——之后智能定位/角色匹配/禁忌区避让/骑压/
压平与原管线完全共用（详见 normalize_input）。图片输入默认输出同格式图片，
也可显式指定 .pdf 输出。

Excel 的处理设计（v1.2.0 新增）：对 Excel 输入，第 0 步先调用本机 Excel COM
执行「另存为 PDF」（导出所有可见工作表、保持原页面设置/分页/打印区域，与人工
在 Office 中另存为 PDF 等价），得到文本版 PDF 后**整体替换输入**走原管线——
定位/盖章/压平与 PDF 输入零差异（详见 convert_excel_to_pdf）。输出固定为 PDF。

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
    python3 pdf_seal_stamper.py <合同文件> [公章图片] [输出文件] [选项]

参数:
    合同文件      - 待盖章的合同：PDF（文本版或扫描件）、图片（png/jpg/jpeg/bmp/webp）、
                    Excel 工作簿（xlsx/xls/xlsm/xlsb，自动转 PDF 后盖章）
    公章图片      - （可选）要添加的公章图片（支持 PNG/JPEG），默认使用脚本同目录下的"默认公章图片.png"
    输出文件      - （可选）输出文件路径（Excel/PDF 输入默认 .pdf；图片输入默认输出同格式图片）

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
    python3 pdf_seal_stamper.py quote.xlsx           # Excel：自动转 PDF 后盖章
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
# 输出编码固定（v1.2.1 稳定性补丁，首要防线）
# 根因：脚本大量打印 emoji/制表符（ℹ️/⚠️/❌/🔍/─），Windows GBK 控制台下
# print 即抛 UnicodeEncodeError，整个盖章直接崩溃（exit=1）；且测试以 utf-8
# 解码子进程输出，编码不确定则中文断言全灭。必须在任何 print（含依赖自检）
# 之前把 stdout/stderr 固定为 utf-8，errors=replace 保证任何 print 永不崩。
# ============================================================

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass  # 非标准 stdout（如被重定向为 StringIO）无 reconfigure，忽略即可

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
    # Excel→PDF 转换（v1.2.0）：只有 Excel 输入才需要；缺失时自动安装，
    # 装不上仅影响 Excel 输入（PDF/扫描件/图片不受影响）
    ("win32com", "pywin32"),
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
    if seal_mask.sum() < max(100, seal_mask.size * 0.005):
        # 非红色章（蓝/黑章）或红色过少：按红色检测生成的 alpha 近乎全透明，
        # 章盖上去将不可见——这是最坏结果。此时宁可保留原图不透明
        # （章稍大但可见），绝不交出隐形章。
        return pil_image.convert("RGBA")

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
    """统一裁剪接口（P/L/LA/CMYK 等非常见模式先归一化：原样返回会导致
    白底遮挡合同文字或后续绘制异常；归一化失败才原样返回，不抛异常）"""
    if pil_image.mode == 'RGBA':
        return crop_seal_rgba(pil_image)
    if pil_image.mode == 'RGB':
        return crop_seal_rgb(pil_image)
    if pil_image.mode in ('LA', 'PA'):
        try:
            return crop_seal_rgba(pil_image.convert('RGBA'))
        except Exception:
            return pil_image
    # P/L/CMYK 等：先转 RGB 再走红色检测转透明（非红章由兜底保证不透明可见）
    try:
        return crop_seal_rgb(pil_image.convert('RGB'))
    except Exception:
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


def find_keyword_blocks(pdf_path, keywords, cluster_distance=100, max_word_width=300):
    """
    在 PDF 中搜索包含关键词的文字块，用于定位盖章位置。

    参数:
        pdf_path: PDF 文件路径
        keywords: 关键词列表，如 ['签章', '公章', '盖章']
        cluster_distance: 聚类距离（pts），用于将附近的关键词归为同一文字块
        max_word_width: 关键词词语的最大宽度（pts），超过此宽度的视为正文行，予以过滤。
            200→300（v1.1.1）：扫描件 OCR 文字层按"整行"写入，"单位（盖章）/
            承诺人（签名）："式签名栏整行宽约 213pts，阈值 200 会把它误当正文
            过滤掉，关键词定位落空；正文贯穿行通常 ≥380pts，300 足以区分。

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
                    # 命中词明细（text+坐标）：骑压分支按关键词在块内的字符
                    # 位置精确对齐章中心用（v1.1.1）
                    'kw_words': [(w['text'], w['x0'], w['x1']) for w in cluster_words],
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

    # 原子替换输出文件（Windows 预览窗格/杀软可能锁住目标，带重试；持续锁则
    # 清理 tmp 后抛异常由上层转友好提示，不留半成品孤儿文件）
    tmp_path = pdf_path + ".flattening.tmp"
    try:
        _write_bytes_retry(tmp_path, out_bytes)
        _replace_retry(tmp_path, pdf_path)
    except Exception:
        _cleanup_tmp(tmp_path)
        raise


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


def _cleanup_tmp(path):
    """清理规范化/中间临时文件；被占用时只警告不阻塞（下次运行不受影响）"""
    if not path:
        return
    try:
        os.unlink(path)
    except OSError:
        print(f"  ⚠️  临时文件未能删除（可能被占用），可稍后手动删除: {path}")


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


def _replace_retry(src, dst, attempts=4, delay=0.5):
    """os.replace 的 Windows 文件锁重试版（预览窗格常锁住输出 PDF）。
    持续锁住则抛异常，由调用方清理临时文件后转友好提示，不留孤儿 tmp。"""
    import time
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


def _last_page_size(pdf_path):
    """返回 (末页宽pts, 末页高pts, 末页号)。失败退回 A4/第1页，绝不抛异常。
    用途：默认兜底定位必须按文档实际尺寸与末页（签署区在末页）计算，
    写死 A4 第一页会在非 A4/多页文档上盖错地方。"""
    try:
        doc = fitz.open(pdf_path)
        try:
            n = max(len(doc) - 1, 0)
            r = doc[n].rect
            return r.width, r.height, n + 1
        finally:
            doc.close()
    except Exception:
        return 595.2, 841.9, 1


def _lazy_ocr_engine():
    """懒加载 rec-only 识别引擎；OCR 依赖不可用返回 None（智能定位自动降级）"""
    try:
        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR(use_text_det=False, use_cls=False)
    except Exception:
        return None


def _need_cv2():
    """取 cv2 模块；缺失返回 None（调用方诚实降级，绝不因 import 崩溃）。
    根因：OPTIONAL 里只判了 rapidocr 未单独判 cv2，opencv 装不上时
    _polar_unwrap 等处的 import cv2 直接抛 ImportError 崩全程。"""
    try:
        import cv2
        return cv2
    except Exception:
        return None


def _imread_bgr(path):
    """cv2.imread 不支持中文路径，经 PIL 中转（RGB→BGR）。
    RGBA 图先以白底合成：透明 padding 底下的 RGB 可能是红/黑，直接丢 alpha
    会污染红像素质心与极坐标展开。cv2 缺失或图片无法解码返回 None（上层降级，
    不抛异常）。"""
    try:
        pil = Image.open(path)
    except Exception:
        return None
    try:
        if pil.mode == "RGBA":
            bg = Image.new("RGB", pil.size, (255, 255, 255))
            bg.paste(pil, mask=pil.split()[3])
            pil = bg
        else:
            pil = pil.convert("RGB")
    except Exception:
        return None
    cv2 = _need_cv2()
    if cv2 is None:
        return None
    try:
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def _red_mask(bgr):
    r = bgr[:, :, 2].astype(int)
    g = bgr[:, :, 1].astype(int)
    b = bgr[:, :, 0].astype(int)
    return (r > 120) & (r > g * 1.3) & (r > b * 1.3)


def _polar_unwrap(bgr, start_deg, band=(0.58, 0.92), out_w=2400):
    """以红像素质心为圆心做极坐标展开，把环形排列的公司名拉直成横排。
    轴向关键（曾因写反而整行镜像）：输出顶行=外半径（字头朝外的公章文字展开后正立），
    列=角度顺时针。start_deg 为展开缝的起始角，用于多起始角避开文字被切断。
    cv2 缺失或输入无效返回 None（上层换角度/降级，不抛异常）。"""
    cv2 = _need_cv2()
    if cv2 is None or bgr is None:
        return None
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
    """展开图中按红像素垂直投影裁出主文字行（公司名行是红像素最多的行带）。
    flat 无效返回 None（上层换角度，不抛异常）。"""
    if flat is None:
        return None
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
    在红像素列投影的空隙处下刀保证每段都是完整字，拼接无需去重。
    cv2 缺失或输入无效返回 ""（上层视为该角度无结果，不抛异常）。"""
    cv2 = _need_cv2()
    if cv2 is None or line_img is None:
        return ""
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
    if bgr is None:
        # cv2 缺失 / 图片损坏或格式不支持：极坐标 OCR 做不了，交 --company 兜底
        print("  ⚠️  公章图片无法解析（cv2 缺失或图片损坏），"
              "可用 --company \"公司名\" 手动指定后重试")
        return None
    for start in (0, 90, 180, 270):
        try:
            flat = _polar_unwrap(bgr, np.deg2rad(start))
            if flat is None:
                continue
            line = _crop_main_text_row(flat)
            if line is None:
                continue
            text = _rec_line_segments(rec_only, line)
        except Exception:
            continue  # 单角度失败换下一个角度，绝不因一角崩全程
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
    # 词宽 400（同策略3）：签署行常带公司名，整词宽易超默认 300 被滤，
    # 曾致长签署行的明确盖章栏漏检
    blocks = find_keyword_blocks(pdf_path, kws, max_word_width=400)
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
            # 只认角色块正下方（y 更大）且距离最近的配对；用二维欧氏距离
            # （曾只比水平距离：正文段落里同列的角色词会抢赢签署区近邻）
            above = [rb for rb in role_blocks
                     if rb["page"] == mb["page"] and rb["center_y"] < mb["center_y"]]
            if not above:
                continue
            rb = min(above, key=lambda r: ((r["center_x"] - mb["center_x"]) ** 2
                                           + (r["center_y"] - mb["center_y"]) ** 2) ** 0.5)
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
            # 合成块=以目标中心为中心、章宽为宽的方块：保证定位走骑压分支精确落点；
            # kw_words 必须清空（合成块无关键词明细，骑压分支退回块中心——
            # 若复用角色块的词明细，角色文本恰含"盖章"时会把章拽偏）
            synthetic = dict(rb)
            synthetic.update({
                "x0": cx - half, "x1": cx + half, "center_x": cx,
                "y0": cy - 10, "y1": cy + 10, "center_y": cy,
                "page": om["page"],
                "kw_words": [],
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
    # 他角色的明确盖章栏（"甲方（盖章）："式冒号在括号外，不含"盖章："子串，
    # 上面的裸栏搜索扫不到——曾漏导致章压到对方明确栏文字上）
    for r in other_roles:
        rkws = []
        for mark in ("盖章", "公章", "签章"):
            rkws += [f"{r}（{mark}", f"{r}({mark}", f"{r}{mark}"]
        for b in find_keyword_blocks(pdf_path, rkws, max_word_width=400):
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
    """落点禁忌区动态避让：章中心落入任一禁忌区时，以锚点为中心按半章宽步长
    网格搜索最近的中心合法位（纯水平避让优先——尽量保住"同高对齐"等已有偏好，
    范围±1.5章宽）；搜索不到返回原位由调用方警告人工确认。
    返回 (cx, cy, moved)。
    命中语义只看章中心（v1.2.1）：整章矩形相交太严——上下紧排的双方签署栏
    （如甲方栏 y=620、乙方栏 y=660，间距仅 40pts），125pts 的章骑压本方栏时
    必然与对方栏矩形相交，那是正常压字；只有"章中心盖到对方栏/名上"才算真压
    区（曾用矩形相交把章从乙方栏赶走 62pts，回归失败）。"""
    def hits(ox, oy):
        for z in forbidden:
            if (z[0] - 4 <= ox <= z[2] + 4 and
                    z[1] - 4 <= oy <= z[3] + 4):
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
# 输入规范化：图片 / 扫描件 PDF → "整页位图 + OCR 隐形文字层" PDF
# 设计要点（v1.1.0）：不新写定位逻辑！扫描件/图片先规范化为与文本版合同
# 同构的 PDF（位图承载视觉 + render_mode=3 隐形文字层承载可提取文本），
# 之后智能定位/角色匹配/禁忌区避让/骑压/压平全部零改动复用原管线。
# ============================================================

# 支持的图片输入格式（第一个参数）
IMAGE_INPUT_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
# 支持的 Excel 输入格式（v1.2.0）：第 0 步先经 Excel COM 转 PDF 再走原盖章管线
EXCEL_INPUT_EXTS = ('.xlsx', '.xls', '.xlsm', '.xlsb')
# 图片输入的页面规格化宽度（pts，≈A4 宽）。为什么要规格化：图片像素尺寸差异巨大
# （手机拍照 3000px+），若按 1px=1pt 建页，默认章宽 125pts 占比会严重失调；
# 统一规格化到 595pts 宽后，默认章宽占比与文本版合同一致，渲染回图片时再按
# 原图宽度等比放大，章在输出图片中的占比与 PDF 中相同。
NORMALIZED_PAGE_W = 595.0
# 扫描件判定阈值：任一页文本字符数达到该值即视为"文本版 PDF"走原管线；
# 全部页低于该值判定为扫描件（无文本层，必须 OCR 建文字层才能智能定位）。
SCAN_TEXT_MIN_CHARS = 20
# 扫描件 OCR 渲染分辨率：150dpi 兼顾速度与中文小字识别率（压平另有自己的 dpi）
SCAN_OCR_DPI = 150


def _lazy_full_ocr_engine():
    """懒加载整页 OCR 引擎（带文字检测 det，用于扫描件/图片的全文识别）。
    与公章识别的 rec-only 引擎是两种用途，不可混用：公章环形大字 det 失灵必须
    rec-only；页面正文是规整横排小字，必须带 det 才能正确分行/定位。
    OCR 依赖不可用返回 None（降级为无文字层，定位落默认位置并警告）。"""
    try:
        from rapidocr_onnxruntime import RapidOCR
        # det_box_thresh 0.5→0.3、unclip 1.6→2.0：提高弱对比文字行检出召回。
        # 根因（v1.1.1 实测）：扫描件签名栏"单位（盖章）/承诺人（签名）："整行
        # det 得分仅 0.77 分、但 box_thresh 默认 0.5 时该行检测框直接被丢弃，
        # OCR 文字层缺失该行 → 关键词"盖章"搜索落空 → 定位落到默认右下角。
        # 降低阈值后该行稳定检出；正文长行仍会被 max_word_width 过滤，不误伤。
        # 注意：rapidocr_onnxruntime 新版 API 传任何 det_* 参数时必须显式带
        # det_model_path=None（否则其参数合并逻辑 KeyError: 'model_path'）。
        return RapidOCR(det_model_path=None, det_box_thresh=0.3,
                        det_unclip_ratio=2.0)
    except Exception:
        return None


def detect_input_kind(path):
    """识别输入类型，返回 'image' / 'pdf-scan' / 'pdf-text' / 'excel'。
    PDF 打不开（损坏/加密/根本不是 PDF）时抛 RuntimeError 由上层转友好提示，
    不直接甩 traceback 给用户。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_INPUT_EXTS:
        return 'image'
    if ext in EXCEL_INPUT_EXTS:
        return 'excel'
    try:
        doc = fitz.open(path)
    except Exception as e:
        raise RuntimeError(f"文件无法作为 PDF 打开（可能已损坏、被加密或并非 PDF）: {e}")
    try:
        for page in doc:
            if len(page.get_text().strip()) >= SCAN_TEXT_MIN_CHARS:
                return 'pdf-text'
        return 'pdf-scan'
    finally:
        doc.close()


def convert_excel_to_pdf(excel_path, out_pdf_path, wait_sec=30):
    """
    Excel → PDF（v1.2.0）：调用本机 Office Excel COM 执行「另存为 PDF」——
    导出所有可见工作表、保持原页面设置/分页/打印区域，与人工在 Excel 中
    「另存为 PDF」完全等价。转出的 PDF 是文本版（文字可提取），之后盖章
    主流程直接复用文本版 PDF 管线，无需再 OCR。

    失败时抛 RuntimeError（由调用方转成可行动的报错 — 铁律9：失败分支
    自带下一步指引）。铁律：COM 对象必须在 finally 中 Close + Quit + 释放
    COM 引用，否则 excel.exe 进程会残留占用文件。

    pywin32 包缺失或本机未安装 Office Excel 都会使 win32com.Dispatch 失败
    ——调用方已捕获并提示"手动另存为 PDF 后重跑"的兜底路径。
    """
    if _missing('win32com'):
        raise RuntimeError("缺少 pywin32（Excel→PDF 转换需要），请先执行："
                           "pip install pywin32 -i https://mirrors.aliyun.com/pypi/simple/")
    excel = None
    wb = None
    try:
        import win32com.client
        # COM 按 Excel 进程默认目录解析相对路径：必须传绝对路径，
        # 否则用户用相对路径调用时 Workbooks.Open 会打开失败（曾犯）。
        excel_path_abs = os.path.abspath(excel_path)
        out_pdf_abs = os.path.abspath(out_pdf_path)
        excel = win32com.client.DispatchEx('Excel.Application')
        excel.Visible = False
        excel.DisplayAlerts = False   # 避免宏安全等弹窗阻塞导出
        wb = excel.Workbooks.Open(excel_path_abs, ReadOnly=True, UpdateLinks=0)
        # 0 = xlTypePDF；不指定 From/To Sheet → 导出工作簿全部可见工作表
        wb.ExportAsFixedFormat(0, out_pdf_abs)
        # 落盘防御性等待：正常情况下 ExportAsFixedFormat 同步写完（实测受控
        # 实验 1.6s 内写全）。保留"pdfplumber 能打开且页数≥1"才放行的兜底——
        # 防杀毒实时扫描/慢磁盘/Office 后台补写的文件锁（_write_bytes_retry
        # 同源的 Windows 元凶）。⚠️ 注意：不能用 fitz 探测（MuPDF 对不完整
        # PDF 宽容，缺 /Root 也肯开）；pdfplumber 严格校验 xref 才匹配后续管线。
        import time as _time
        deadline = _time.time() + wait_sec
        exported_ok = False
        while _time.time() < deadline:
            if os.path.exists(out_pdf_path) and os.path.getsize(out_pdf_path) > 0:
                try:
                    with pdfplumber.open(out_pdf_path) as _probe:
                        if len(_probe.pages) >= 1:
                            exported_ok = True
                            break
                except Exception:
                    pass
            _time.sleep(0.5)
        if not exported_ok:
            raise RuntimeError(f"Excel 导出 PDF 超时未完成（{int(wait_sec)}s），"
                               f"文件可能仍在写入: {out_pdf_path}")
        wb.Close(False)
        wb = None
    except Exception as e:
        raise RuntimeError(f"Excel COM 转换失败：{e}") from e
    finally:
        # 释放 COM 引用（赋值 None 令 PythonCOM 引用计数归零）+ Quit，
        # 缺一步都可能导致 excel.exe 进程残留占用临时文件
        if wb is not None:
            try:
                wb.Close(False)
            except Exception:
                pass
            wb = None
        if excel is not None:
            try:
                excel.Quit()
            except Exception:
                pass
            excel = None
    if not os.path.exists(out_pdf_path) or os.path.getsize(out_pdf_path) == 0:
        raise RuntimeError(f"Excel COM 转换未生成有效 PDF：{out_pdf_path}")


def ocr_page_lines(pil_img, ocr):
    """整页 OCR，返回 [(x0,y0,x1,y1,text), ...]（像素坐标，顶部原点）。
    rapidocr 的 det 按文字行切块（每个 box 一行）——写入 PDF 文字层时必须整行
    一次 insert_text，pdfplumber 的 extract_text 才能按行还原（签署方正则
    "需方：A 供方：B"同行多对匹配依赖行结构）。
    单页 OCR 抛异常返回 []（该页无文字层，后续定位对该页降级，绝不崩全程）。"""
    try:
        arr = np.array(pil_img.convert("RGB"))
        result, _ = ocr(arr)
    except Exception as e:
        print(f"  ⚠️  本页 OCR 失败（跳过该页文字层，不影响盖章）: {e}")
        return []
    lines = []
    for item in (result or []):
        box, text = item[0], item[1]
        text = (text or "").strip()
        if not text:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        lines.append((min(xs), min(ys), max(xs), max(ys), text))
    return lines


def _insert_invisible_lines(page, lines, sx, sy):
    """把 OCR 行以 render_mode=3（隐形）写入页面。sx/sy = 像素→PDF pts 换算比例。
    与 flatten_stamped_page 重建文字层同一套路：视觉 100% 来自位图，文字层只为
    可搜索/可提取（pdfplumber 的智能定位全靠它）。逐行插入保证行结构。"""
    for x0, y0, x1, y1, text in lines:
        fontsize = max((y1 - y0) * sy * 0.8, 4.0)
        # 宽度校准（v1.1.1）：按行高推的字号只保证纵向贴合，横向铺开宽度
        # = fontsize × 字符数，与 OCR 行框宽脱节（实测签名栏行框 213pts 被
        # 铺成 496pts，超 max_word_width 被误过滤，关键词定位落空）。
        # 把文字层词宽缩放到与 OCR 行框一致，定位/搜索才反映真实版式。
        target_w = (x1 - x0) * sx
        try:
            tl = fitz.get_text_length(text, fontname="china-s", fontsize=fontsize)
        except Exception:
            tl = 0  # 特殊字符（如 emoji）量宽失败时退回未校准字号，该行仍可搜索
        if tl > 0:
            fontsize = max(fontsize * target_w / tl, 2.0)
        try:
            page.insert_text(
                fitz.Point(x0 * sx, y1 * sy - fontsize * 0.18), text,
                fontsize=fontsize, fontname="china-s", render_mode=3)
        except Exception:
            # 个别行字符不支持时跳过，不影响整页
            continue


def build_pdf_from_scanned_pages(pages, out_path):
    """pages: [(pil_img, page_w_pts, page_h_pts, ocr_lines, px_w, px_h)]
    生成"整页位图 + OCR 隐形文字层"的规范化 PDF。"""
    doc = fitz.open()
    try:
        for img, w, h, lines, pw, ph in pages:
            page = doc.new_page(width=w, height=h)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=92)
            page.insert_image(page.rect, stream=buf.getvalue())
            _insert_invisible_lines(page, lines, w / pw, h / ph)
        doc.save(out_path, garbage=3, deflate=True)
    finally:
        doc.close()


def normalize_input(pdf_path, input_kind, ocr, dpi=SCAN_OCR_DPI):
    """图片/扫描件 → 规范化临时 PDF。返回 (tmp_pdf_path, img_orig_w_px, 识别行数)。
    OCR 不可用时 lines 为空 → 无文字层 → 后续定位自动落到默认位置并警告
    （诚实降级，不阻塞盖章）。img_orig_w_px 仅图片输入有效（渲染回图片用）。"""
    pages = []
    img_w_px = None
    if input_kind == 'image':
        img = Image.open(pdf_path).convert("RGB")
        img_w_px = img.width
        scale = NORMALIZED_PAGE_W / img.width
        w, h = NORMALIZED_PAGE_W, img.height * scale
        lines = ocr_page_lines(img, ocr) if ocr else []
        pages.append((img, w, h, lines, img.width, img.height))
    else:  # pdf-scan：渲染每页再 OCR（页尺寸保持原 pts，不动比例）
        doc = fitz.open(pdf_path)
        try:
            for page in doc:
                pix = page.get_pixmap(dpi=dpi, alpha=False)
                stride = getattr(pix, "stride", pix.width * 3)
                # frombuffer 引用的是 pix 内部缓冲，pix 销毁前必须 copy 出来
                img = Image.frombuffer("RGB", (pix.width, pix.height), pix.samples,
                                       "raw", "RGB", stride, 1).copy()
                lines = ocr_page_lines(img, ocr) if ocr else []
                pages.append((img, page.rect.width, page.rect.height, lines,
                              pix.width, pix.height))
        finally:
            doc.close()
    tmp = tempfile.mktemp(suffix='.normalized.pdf')
    build_pdf_from_scanned_pages(pages, tmp)
    n_lines = sum(len(p[3]) for p in pages)
    return tmp, img_w_px, n_lines


def render_pdf_page_to_image(pdf_path, page_number, out_img_path, target_w_px):
    """盖章完成的 PDF 页按原图宽度渲染回图片（图片输入的输出路径）。
    zoom = 原图宽 / 页宽：输出图片与原图同分辨率，章的占比与 PDF 中一致。"""
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_number - 1]
        zoom = target_w_px / page.rect.width
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        stride = getattr(pix, "stride", pix.width * 3)
        img = Image.frombuffer("RGB", (pix.width, pix.height), pix.samples,
                               "raw", "RGB", stride, 1).copy()
    finally:
        doc.close()
    ext = os.path.splitext(out_img_path)[1].lower()
    if ext in ('.jpg', '.jpeg'):
        img.save(out_img_path, quality=95)
    elif ext == '.webp':
        img.save(out_img_path, quality=95)
    elif ext == '.bmp':
        img.save(out_img_path, format='BMP')
    else:
        img.save(out_img_path, format='PNG')


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
    print(f"合同文件:  {pdf_path}")
    print(f"公章图片:  {seal_image_path}")

    # ---- 步骤 0: 输入类型识别与规范化 ----
    # Excel→PDF（v1.2.0）；图片/扫描件 → "位图+OCR文字层 PDF"。
    # 后续所有分析/定位/合并都作用在 src_pdf 上（规范化后的临时 PDF 或原 PDF），
    # 与原管线零差异；tmp_normalized / tmp_excel_pdf 在函数结束（含 dry-run
    # 提前返回）时清理。orig_input 始终是原始文件——Excel 等非 PDF 输入在第 0
    # 步替换 pdf_path 为临时 PDF 后，默认输出名仍以原始文件名为基准。
    print("\n" + "─" * 55)
    print("【步骤 0】识别输入类型")
    print("─" * 55)

    orig_input = pdf_path
    try:
        input_kind = detect_input_kind(pdf_path)
    except RuntimeError as e:
        print(f"  ❌ {e}")
        print("     请确认文件未损坏、未加密，或先用阅读器另存一份再试。")
        return None
    src_pdf = pdf_path
    img_orig_w = None        # 图片输入的原始宽度（px），渲染回图片用
    tmp_excel_pdf = None     # Excel→PDF 临时文件，结束时清理
    tmp_normalized = None    # 规范化临时 PDF，结束时清理
    kind_label = {'pdf-text': '文本版 PDF', 'pdf-scan': '扫描件 PDF（无文本层）',
                  'image': '图片文件', 'excel': 'Excel 工作簿'}[input_kind]
    print(f"  输入类型: {kind_label}")

    # Excel 输入（v1.2.0）：先经本机 Excel COM「另存为 PDF」（与人工在 Office
    # 中操作等价，保留原打印设置/分页），转出的 PDF 是文本版 → 直接复用文本
    # 版管线盖章/压平，智能定位/角色匹配自动生效，无任何新定位逻辑。
    # 转换失败给出"手动另存为 PDF 后重跑"的兜底指引（铁律9）。
    if input_kind == 'excel':
        print(f"  → Excel 转为 PDF（等同 Office「另存为 PDF」），之后走 PDF 管线 ...")
        tmp_excel_pdf = tempfile.mktemp(suffix='_excel2pdf.pdf')
        try:
            convert_excel_to_pdf(pdf_path, tmp_excel_pdf)
            print(f"  → 转换完成（{os.path.getsize(tmp_excel_pdf)} bytes）")
        except Exception as e:
            print(f"  ❌ Excel 转 PDF 失败: {e}")
            print("     兜底方案：请手动用 Office 打开该 Excel，执行「另存为 PDF」，")
            print("     再把生成的 PDF 文件交给我盖章（盖章流程不变）。")
            _cleanup_tmp(tmp_excel_pdf)
            return None
        pdf_path = tmp_excel_pdf
        input_kind = detect_input_kind(pdf_path)
        # ⚠️ 核心：src_pdf 必须重新指向转换后的 PDF！曾漏改导致 analyze_pdf_seals
        # 对原 .xlsx（zip）调 pdfplumber 报 "No /Root object"（解析器把 xlsx 当 PDF
        # 解析的合理报错），且被误当作"导出异步未写完"排查很久（铁律1教训）。
        # 转换后为文本版 PDF 时走 pdf-text 通用分支（src_pdf 此处即可）；若为
        # 扫描件会在下方规范化分支覆盖为 tmp_normalized。
        src_pdf = pdf_path
        kind_label = {'pdf-text': '文本版 PDF', 'pdf-scan': '扫描件 PDF（无文本层）',
                      'image': '图片文件'}.get(input_kind, input_kind)
        print(f"  → 转换后 PDF 输入类型: {kind_label}")

    if input_kind != 'pdf-text':
        if input_kind == 'image':
            print(f"  → 图片规范化为 PDF 页面（宽 {NORMALIZED_PAGE_W:.0f}pts）+ OCR 建文字层")
        else:
            print(f"  → 扫描件按 {SCAN_OCR_DPI}dpi 渲染每页 + OCR 建文字层")
        full_ocr = _lazy_full_ocr_engine()
        if full_ocr is None:
            print("  ⚠️  OCR 依赖不可用，无法建立文字层：智能定位/关键词定位全部失效，")
            print("      将落到默认位置（右下角），交付前必须人工核对！")
            print("      （安装 rapidocr_onnxruntime 后重跑即可智能定位：")
            print("       pip install rapidocr_onnxruntime -i https://mirrors.aliyun.com/pypi/simple/）")
        tmp_normalized, img_orig_w, n_ocr_lines = normalize_input(
            pdf_path, input_kind, full_ocr)
        src_pdf = tmp_normalized
        if full_ocr is not None:
            print(f"  → OCR 建立文字层完成（{n_ocr_lines} 行），后续定位流程与文本版合同一致")

    # ---- 步骤 1: 分析 PDF 中已有公章 ----
    print("\n" + "─" * 55)
    print("【步骤 1】分析文档中已有公章")
    print("─" * 55)

    all_images = analyze_pdf_seals(src_pdf)
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
            parties = extract_contract_parties(src_pdf)
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
                src_pdf, party["role"], party.get("company"))
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
                kw_blocks = find_keyword_blocks(src_pdf, keywords)

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
                            # 命中词明细：骑压分支关键词精对齐用（v1.1.1）
                            'kw_words': block.get('kw_words', []),
                        }
                        positioning_mode = 'keyword'
                        side_label = '左侧' if block['side'] == 'left' else '右侧'
                        print(f"  → 关键词定位成功！匹配到{side_label}文字块: {block['keywords_found']}")
                        print(f"  → 文字区域: ({block['x0']:.0f}, {block['y0']:.0f}) → "
                              f"({block['x1']:.0f}, {block['y1']:.0f})")
                        print(f"  → 公章中心: ({block['center_x']:.1f}, {block['center_y']:.1f})")

            if positioning_mode == 'default':
                print("\n  ⚠️  关键词定位失败，使用默认位置（末页右下角签名区）。")
                print("      位置不可靠：知道角色请加 --role 角色名 重试，"
                      "OCR 没出公司名请加 --company \"公司名\" 重试；交付前必须人工核对！")
                # 默认点按文档实际末页尺寸比例计算（A4 下≈历史默认点 318,547；
                # 写死 A4 第一页曾在非 A4/多页文档上盖错地方）。签署区在末页。
                _dw, _dh, _dp = _last_page_size(src_pdf)
                _dcx, _dcy = _dw * 0.535, _dh * 0.65
                _dd = SEAL_DEFAULT_SIZE
                reference = {
                    'x0': _dcx - _dd / 2, 'y0': _dcy - _dd / 2,
                    'x1': _dcx + _dd / 2, 'y1': _dcy + _dd / 2,
                    'width': _dd, 'height': _dd,
                    'center_x': _dcx, 'center_y': _dcy,
                    'page_width': _dw, 'page_height': _dh,
                    'page': _dp, 'pixel_width': 0, 'pixel_height': 0,
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
            src_pdf, reference)
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
            target_cx = (kw_x0 + kw_x1) / 2
            # 关键词精对齐（v1.1.1）：长签署行（如"单位（盖章）/承诺人（签名）："）
            # 骑整块中心会盖偏——章应骑在"盖章"二字处，不是几何中心。
            # 文字层词宽已校准=OCR行框宽，按字符均布估算关键词在块内的位置；
            # 找不到关键词明细（如智能定位合成块）时退回块中心。
            kw_centers = []
            kw_hits = []
            for w_text, wx0, wx1 in reference.get('kw_words', []):
                for kw in (keywords or []):
                    idx = w_text.find(kw)
                    if idx >= 0 and len(w_text) > 0:
                        char_w = (wx1 - wx0) / len(w_text)
                        kw_centers.append(wx0 + (idx + len(kw) / 2) * char_w)
                        kw_hits.append(kw)
                        break
            if kw_centers:
                target_cx = sum(kw_centers) / len(kw_centers)
                print(f"  文字块较宽（{block_w:.0f}pts），骑压\"{'/'.join(kw_hits)}\"关键词处（精对齐）")
            else:
                print(f"  文字块较宽（{block_w:.0f}pts），骑压式盖章（模拟真实压字）")
            target_cx += offset_x
            target_cy = reference['center_y'] + offset_y
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
        forbidden = build_forbidden_zones(src_pdf, party["role"], party.get("company"))
        ncx, ncy, moved = adjust_avoid_forbidden(
            target_cx, target_cy, ref_content_w / 2, ref_content_h / 2,
            forbidden, page_w, page_h)
        if moved:
            print(f"  ⚠️  落点压到他角色盖章栏/公司名，已自动避让: "
                  f"({target_cx:.0f},{target_cy:.0f}) → ({ncx:.0f},{ncy:.0f})")
            target_cx, target_cy = ncx, ncy
        else:
            # 网格搜不到合法位（禁忌区过大）且章中心仍在区内：保持原位但必须
            # 明示，不能静默盖到对方签章区上（命中语义同 adjust：只看章中心）
            _hit = any((z[0] - 4 <= target_cx <= z[2] + 4 and
                        z[1] - 4 <= target_cy <= z[3] + 4) for z in forbidden)
            if _hit:
                print("  ⚠️  落点仍压到他角色盖章栏/公司名且附近无合法位，"
                      "请人工核对输出位置（必要时加 --offset-x/--offset-y 微调）")

    # ---- 步骤 4: 处理新公章图片 ----
    print("\n" + "─" * 55)
    print("【步骤 4】处理新公章图片")
    print("─" * 55)

    new_seal = None
    try:
        with Image.open(seal_image_path) as _im:
            new_seal = _im.copy()  # copy 后立即释放文件句柄（Windows 下不关闭会锁文件）
    except Exception as e:
        print(f"  ❌ 公章图片无法打开（文件损坏或格式不支持）: {e}")
        print("     请换一张 PNG/JPG 公章图片重试。")
        _cleanup_tmp(tmp_normalized)
        _cleanup_tmp(tmp_excel_pdf)
        return None
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
        _cleanup_tmp(tmp_normalized)
        _cleanup_tmp(tmp_excel_pdf)
        return "dry-run"  # dry-run 成功返回真值；所有失败路径返回 None，
        # main 据此给退出码（dry-run 入参非法仍是失败，必须 exit 1）

    # ---- 步骤 5: 生成最终 PDF ----
    print("\n" + "─" * 55)
    print("【步骤 5】生成最终 PDF")
    print("─" * 55)

    # 页号合法性钳制：页号越界会导致"章没盖上却显示成功"——最危险的静默失败，
    # 必须拦截（正常路径页号合法，此分支只防损坏 PDF 等异常）
    try:
        _cnt_doc = fitz.open(src_pdf)
        _n_pages = len(_cnt_doc)
        _cnt_doc.close()
    except Exception:
        _n_pages = 0
    if _n_pages and not (1 <= reference['page'] <= _n_pages):
        print(f"  ⚠️  定位页号 {reference['page']} 超出文档范围(1~{_n_pages})，已钳到末页")
        reference['page'] = max(min(reference['page'], _n_pages), 1)

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

    # 合并到原始 PDF（图片/扫描件输入时 = 规范化后的临时 PDF，视觉内容不变）
    reader_original = PdfReader(src_pdf)
    reader_overlay = PdfReader(overlay_path)
    writer = PdfWriter()

    for i, page in enumerate(reader_original.pages):
        if i == reference['page'] - 1:
            overlay_page = reader_overlay.pages[0]
            page.merge_page(overlay_page)
        writer.add_page(page)

    # 输出路径决策：
    # - 图片输入且未指定输出 → 默认输出同格式图片（原名_已盖章.原扩展名）
    # - 图片输入且指定 .pdf 输出 → 输出 PDF（规范化后的版本，位图+文字层）
    # - PDF / Excel 输入 → 原名_已盖章.pdf（Excel 第0步转 PDF 后按 PDF 处理；
    #   基准名必须用原 Excel 文件 orig_input，不能用已被替换的临时 PDF 路径）
    if output_path is None:
        base = os.path.splitext(orig_input)[0]
        if input_kind == 'image':
            output_path = f"{base}_已盖章{os.path.splitext(orig_input)[1]}"
        else:
            output_path = f"{base}_已盖章.pdf"
    # 图片输出：先落中间 PDF（走合并+压平同一管线），最后渲染回图片
    img_output = (input_kind == 'image' and
                  os.path.splitext(output_path)[1].lower() != '.pdf')
    pdf_out_path = tempfile.mktemp(suffix='.stamped.pdf') if img_output else output_path

    if not img_output:
        # 输出父目录不存在时 open 直接抛 FileNotFoundError：提前拦截给指引
        _parent = os.path.dirname(os.path.abspath(output_path))
        if _parent and not os.path.isdir(_parent):
            print(f"  ❌ 输出目录不存在: {_parent}")
            print("     请先创建该目录，或换一个已存在的输出路径。")
            _cleanup_tmp(tmp_normalized)
            _cleanup_tmp(tmp_excel_pdf)
            return None

    buf = io.BytesIO()
    writer.write(buf)
    try:
        _write_bytes_retry(pdf_out_path, buf.getvalue())
    except PermissionError:
        # 目标被持续占用（资源管理器预览/杀软长扫描），换名落盘保证盖章不白跑
        import time as _time
        alt = f"{os.path.splitext(pdf_out_path)[0]}_{_time.strftime('%H%M%S')}.pdf"
        _write_bytes_retry(alt, buf.getvalue())
        pdf_out_path = alt
        if not img_output:
            output_path = alt
        print(f"  ⚠️  目标文件被其他程序占用，已改写到: {alt}")
        print("      （关闭占用它的程序如预览窗格后，可重命名为原输出名，或删除旧文件重跑）")
    except OSError as e:
        print(f"  ❌ 输出文件写入失败: {e}")
        print("     请确认磁盘空间充足、输出路径合法后重试。")
        _cleanup_tmp(tmp_normalized)
        _cleanup_tmp(tmp_excel_pdf)
        return None

    # 尽早关闭读取器释放文件句柄（Windows 下不关闭会导致临时文件删不掉）
    for _r in (reader_original, reader_overlay):
        try:
            _r.close()
        except Exception:
            pass

    # 清理临时文件（被杀软瞬时锁定时只警告，绝不因此崩掉已成功的盖章）
    _cleanup_tmp(cropped_path)
    _cleanup_tmp(overlay_path)

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
        try:
            flatten_stamped_page(pdf_out_path, reference['page'], dpi=dpi)
        except Exception as e:
            print(f"  ⚠️  压平失败（{e}）：保留未压平版本，公章仍是独立图片对象，"
                  "可被编辑软件选中/移动——请关闭占用该文件的程序后重跑以获得防编辑版本")
        else:
            print(f"  盖章页（第 {reference['page']} 页）已压平: "
                  f"整页位图({dpi}dpi) + 隐形文字层（文字仍可搜索/复制）")
            print("  → 公章与页面融为一体，编辑软件无法单独选中/移动/删除公章")
    else:
        print("  ⚠️  未压平（--no-flatten）：公章仍是页面内独立图片对象，"
              "可被编辑软件选中/移动/删除，存在法律风险，仅限应急/内部核对使用")

    # ---- 步骤 7: 图片输入时渲染回图片（与原图同分辨率）----
    if img_output:
        print("\n" + "─" * 55)
        print("【步骤 7】渲染回图片")
        print("─" * 55)
        try:
            render_pdf_page_to_image(pdf_out_path, reference['page'],
                                     output_path, img_orig_w)
        except Exception as e:
            print(f"  ❌ 渲染回图片失败: {e}")
            _cleanup_tmp(pdf_out_path)
            _cleanup_tmp(tmp_normalized)
            _cleanup_tmp(tmp_excel_pdf)
            return None
        _cleanup_tmp(pdf_out_path)
        print(f"  已输出图片: {output_path}（宽 {img_orig_w}px，与原图同分辨率）")
        print("  → 章已融入图片像素，任何图片/PDF 编辑软件都无法单独选中或移除公章")

    _cleanup_tmp(tmp_normalized)
    _cleanup_tmp(tmp_excel_pdf)
    return output_path


# ============================================================
# 命令行入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='公章添加工具 v1.2.1 — 支持文本版PDF/扫描件PDF/图片/Excel，智能定位 + 防编辑压平',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 pdf_seal_stamper.py contract.pdf              # 文本版 PDF
  python3 pdf_seal_stamper.py scan.pdf                  # 扫描件 PDF（无文本层，自动 OCR）
  python3 pdf_seal_stamper.py photo.jpg                 # 图片（拍的合同照片，默认输出 原名_已盖章.jpg）
  python3 pdf_seal_stamper.py quote.xlsx                # Excel（自动转 PDF 后盖章，输出 原名_已盖章.pdf）
  python3 pdf_seal_stamper.py photo.jpg seal.png out.pdf  # 图片输入、PDF 输出
  python3 pdf_seal_stamper.py contract.pdf seal.png output.pdf
  python3 pdf_seal_stamper.py contract.pdf --rotate -15
  python3 pdf_seal_stamper.py contract.pdf --dry-run
        """
    )
    parser.add_argument('pdf', help='合同文件路径：PDF（文本版或扫描件）/ 图片'
                                    '（png/jpg/jpeg/bmp/webp）/ Excel（xlsx/xls/xlsm/xlsb，自动转 PDF）')
    parser.add_argument('seal', nargs='?', default=None,
                        help='公章图片路径（可选，默认使用脚本同目录下的"默认公章图片.png"）')
    parser.add_argument('output', nargs='?', default=None,
                        help='输出路径（可选）：PDF/Excel 输入默认 原名_已盖章.pdf；'
                             '图片输入默认 原名_已盖章.原扩展名，指定 .pdf 结尾则输出 PDF')
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

    # 解析关键词（过滤空串：空关键词 "" 会匹配所有文字导致定位错乱，曾犯）
    keywords = [kw.strip() for kw in args.keywords.split(',') if kw.strip()]
    if not keywords:
        print("❌ --keywords 为空（请给出至少一个关键词，或去掉该参数用默认值）")
        sys.exit(1)

    if args.dpi <= 0:
        print(f"❌ --dpi 必须为正整数，收到: {args.dpi}")
        sys.exit(1)
    if args.dpi > 600:
        print(f"  ⚠️  --dpi={args.dpi} 过高：文件会很大且压平很慢，"
              "一般 300 足够，确认需要才继续")

    # 如果未指定公章，使用默认公章
    if args.seal is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        args.seal = os.path.join(script_dir, '默认公章图片.png')
        print(f"ℹ️  未指定公章图片，使用默认公章: {args.seal}")

    for path, name in [(args.pdf, '合同文件'), (args.seal, '公章图片')]:
        if not os.path.exists(path):
            print(f"❌ {name} 不存在: {path}")
            sys.exit(1)

    # 覆盖防护：输出路径不得与输入/公章路径相同（测试事故曾把默认公章图片
    # 当输出覆盖销毁——图片输入时输出默认同格式图片，更容易踩中）
    if args.output:
        for other, name in [(args.pdf, '合同文件'), (args.seal, '公章图片')]:
            if os.path.abspath(args.output) == os.path.abspath(other):
                print(f"❌ 输出路径与{name}路径相同，执行会覆盖源文件，已拒绝: {args.output}")
                sys.exit(1)

    # 输入类型校验：只接受 PDF、支持的图片格式或 Excel 工作簿
    in_ext = os.path.splitext(args.pdf)[1].lower()
    if in_ext != '.pdf' and in_ext not in IMAGE_INPUT_EXTS and in_ext not in EXCEL_INPUT_EXTS:
        print(f"❌ 不支持的合同文件类型: {in_ext or '(无扩展名)'}"
              f"（支持 .pdf / {' / '.join(IMAGE_INPUT_EXTS)} / "
              f"{' / '.join(EXCEL_INPUT_EXTS)}）")
        sys.exit(1)
    # 图片输入 + 显式输出：输出只接受 PDF 或图片格式
    if in_ext in IMAGE_INPUT_EXTS and args.output:
        out_ext = os.path.splitext(args.output)[1].lower()
        if out_ext != '.pdf' and out_ext not in IMAGE_INPUT_EXTS:
            print(f"❌ 图片输入的输出只支持 PDF 或图片格式，收到: {out_ext or '(无扩展名)'}")
            sys.exit(1)
    # Excel 输入 + 显式输出：Excel 转 PDF 后按 PDF 输出，扩展名必须是 .pdf
    if in_ext in EXCEL_INPUT_EXTS and args.output:
        out_ext = os.path.splitext(args.output)[1].lower()
        if out_ext != '.pdf':
            print(f"❌ Excel 输入的输出固定为 PDF（Excel 先转 PDF 再盖章），收到: "
                  f"{out_ext or '(无扩展名)'}，请用 .pdf 结尾的输出路径")
            sys.exit(1)

    try:
        result = process_seal(
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
    except Exception as e:
        print(f"❌ 盖章过程出现未预期错误: {e}")
        print("   请确认合同文件未损坏、磁盘空间充足后重试；仍失败请附上报错信息反馈。")
        sys.exit(1)
    if result is None:
        # process_seal 已打印具体原因（Excel 转换失败/图片损坏/输出目录缺失/
        # 输入损坏等，含 dry-run 入参非法的情形）；返回 None 即失败，必须非 0
        # 退出，否则调用方会误判成功（曾犯）
        sys.exit(1)


if __name__ == '__main__':
    main()