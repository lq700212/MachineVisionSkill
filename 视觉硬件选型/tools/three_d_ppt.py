# -*- coding: utf-8 -*-
"""3D 视觉引导抓取方案 PPT 生成器（skill 正式入口，客户版）。

换项目只改配置，不写 Python：
    python three_d_ppt.py --config project_config_3d.json

输入
----
  --config         project_config_3d.json（必填）
  --selection      three_d_selection.json（默认 config 同目录）
  --template       母版 pptx（默认在工作区自动发现「视觉检测方案.pptx」）
  --pointcloud-dir 点云图目录（默认 <config目录>/点云图/crop）
  --company        公司名（默认 苏州华际光电科技有限公司）
  --out            输出 pptx（默认 <config目录>/<project_name>/<project_name>.pptx）
  --no-check       跳过机检（仅排障，交付禁用）
  --no-preview     跳过导出逐页预览

复用关系（维护只改被复用的模块）
--------------------------------
  章节骨架 / 版式 / 封面 / 目录 / 流程卡 / 三栏卡 / 架构图
      → ppt_layout.py（STANDARD_PAGES / STANDARD_SECTIONS / Deck）
  工作距离标注 + 构建期自检
      → ppt_diagram.py（add_wd_dim / self_check）
  机检 / 逐页预览
      → check_ppt_quality.py / export_ppt_images.py（subprocess 调用，不复制逻辑）
  型号 / 视野 / 点距 / 误差
      → three_d_selection.json + hardware_database.json（与 three_d_selector.py 同源）

本文件只保留 3D 特有页面：产品俯视示意、ETH/EIH 布局、点云成像、6D 位姿、视野校核。
"""
import argparse
import json
import math
import os
import subprocess
import sys
from datetime import date

from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.dml import MSO_LINE_DASH_STYLE

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ppt_layout import (Deck, STANDARD_PAGES, toc_items, page_title,  # noqa: E402
                        discover_template, run_quality_check, export_preview,
                        BLUE_D, BLUE, BLUE_L, BLUE_LL,
                        RED, RED_L, GREEN, GRAY, GRAY_L, BLACK, WHITE)
from ppt_diagram import add_wd_dim, self_check  # noqa: E402
from three_d_selector import ThreeDCameraSelector  # noqa: E402

SKILL_DIR = os.path.dirname(HERE)
HW_DB_PATH = os.path.join(SKILL_DIR, "config", "hardware_database.json")
DEFAULT_COMPANY = "苏州华际光电科技有限公司"

# skill 内置缺省点云图（同型号相机典型成像）。用户未提供实拍图时逐张回退，
# 避免 P7 出现"素材待补"占位框；用户实拍图优先，缺省图只补缺失的图位。
DEFAULT_PC_DIR = os.path.join(SKILL_DIR, "assets", "pointcloud_default")

# 目录文案（各方案自己填；编号与页序由 STANDARD_SECTIONS 决定）
SECTION_TEXT = {
    "requirements": ("项目需求", "产品、安装、拍照与换型约束"),
    "system": ("系统方案", "布局、工作流程与系统组成"),
    "hardware": ("硬件选型", "点云成像效果与相机参数"),
    "special_b": ("6D 位姿", "底部不平与 RZ 可观测性"),
    "special_c": ("视野校核", "工作距离、余量与旋转包络"),
    "delivery": ("实施与验收", "标定、换型、节拍与交付"),
}

# 页面标题（目录名之外的完整标题）
PAGE_TITLES = {
    "requirements": "项目需求",
    "system": "系统方案",
    "workflow": "工作流程",
    "hardware": "硬件选型",
    "special_a": "点云成像效果",
    "special_b": "6D 位姿与 RZ 可观测性",
    "special_c": "视野与工作距离校核",
    "architecture": "系统架构",
    "delivery": "实施与验收",
}


# ==================== 数据 ====================
def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fov_at(hw, wd):
    """指定工作距离的视野（复用选型脚本：单点缩放 / 两点插值）。"""
    return ThreeDCameraSelector.fov_at_wd(hw, wd)


def pitch_at(hw, wd):
    """物方点距（复用选型脚本：该 WD 下 FOV 宽 / 深度图宽）。"""
    return ThreeDCameraSelector.xy_resolution(hw, wd)


def parse_part_size(cfg, req):
    """产品尺寸：优先 selection，其次 config 的 'WxH' 字符串。"""
    ps = (req or {}).get("part_size_mm") or {}
    if ps.get("width") and ps.get("height"):
        return float(ps["width"]), float(ps["height"])
    raw = str(cfg.get("part_size") or "").lower().replace("*", "x")
    for sep in ("x", "×"):
        if sep in raw:
            w, h = raw.split(sep)[:2]
            return float(w), float(h)
    raise SystemExit("[输入] 缺少产品尺寸：selection.part_size_mm 或 config.part_size")


def pick_locked_model(sel):
    """锁定型号优先级：internal_decision → recommendation → 第一台 PASS。"""
    dec = sel.get("internal_decision") or {}
    if dec.get("locked_model"):
        return dec["locked_model"], "internal_decision"
    rec = sel.get("recommendation") or {}
    if rec.get("model"):
        return rec["model"], "recommendation"
    for c in sel.get("candidates") or []:
        if c.get("verdict") == "PASS":
            return c["model"], "candidates"
    raise SystemExit("[输入] selection 里没有可用型号（internal_decision/recommendation/PASS）")


def build_rec(hw, part_w, part_h, fov_margin, abs_errors):
    """把硬件库条目 + 项目口径合成页面用的 REC（不硬编码任何数值）。"""
    wd = hw.get("optimal_working_distance_mm")
    wd_range = (hw.get("working_distance_range_mm")
                or hw.get("working_distance_mm") or [None, None])
    if wd is None:
        if all(wd_range):
            wd = (wd_range[0] + wd_range[1]) / 2
        else:
            raise SystemExit(f"[输入] {hw['model']} 缺少工作距离")
    fov = fov_at(hw, wd)
    pitch = pitch_at(hw, wd)
    if not fov.get("width") or not fov.get("height") or not pitch:
        raise SystemExit(f"[输入] {hw['model']} 缺少 FOV 或分辨率，无法计算视野/点距")

    cam_err = hw.get("guidance_accuracy_mm")
    est = False
    if cam_err is None:
        # 厂商未公布引导精度时按 skill 规则估算，并显式标注"估算"
        z = hw.get("z_repeatability_mm") or 0
        vdi = hw.get("vdi_accuracy_mm") or 0
        cam_err = max(z, vdi) + 0.5 * pitch
        est = True

    other_rss = math.sqrt(sum(v * v for v in (abs_errors or {}).values()))
    total = math.sqrt(cam_err ** 2 + other_rss ** 2)

    cap = hw.get("capture_time_s")
    if isinstance(cap, (list, tuple)) and len(cap) >= 2:
        cap_lo, cap_hi = float(cap[0]), float(cap[1])
    elif isinstance(cap, str):
        cap_lo, cap_hi = 0.3, 0.6
    else:
        cap_lo, cap_hi = 0.3, 0.6

    return {
        "brand": hw["brand"],
        "series": hw.get("series", ""),
        "model": hw["model"],
        "technology": hw.get("technology", ""),
        "working_distance_range_mm": wd_range,
        "recommended_wd_mm": wd,
        "fov_at_wd_mm": fov,
        "xy_resolution_mm": pitch,
        "guidance_accuracy_mm": cam_err,
        "guidance_is_estimate": est,
        "total_error_mm": total,
        "capture_time_s": [cap_lo, cap_hi],
        "software": hw.get("software") or [],
        "interface": hw.get("interface", "GigE"),
        "ip_rating": hw.get("ip_rating", "—"),
        "needs_vendor_confirmation": hw.get("needs_vendor_confirmation") or [],
    }


def rotated_size(w, h, deg):
    """矩形件旋转 deg 后的外接宽高（非正方形产品必须宽高分别算）。"""
    r = math.radians(deg)
    return (w * math.cos(r) + h * math.sin(r),
            w * math.sin(r) + h * math.cos(r))


def rotated_width(w, h, deg):
    """方形/矩形件旋转 deg 后的外接宽度。"""
    return rotated_size(w, h, deg)[0]


# ==================== 页面 ====================
def build_deck(cfg, sel, hw, opts):
    """按标准页序生成 12 页；返回 Deck（未保存）。"""
    req = sel.get("requirements") or {}
    part_w, part_h = parse_part_size(cfg, req)
    fov_margin = req.get("fov_margin") or cfg.get("fov_margin") or 1.2
    cycle = req.get("cycle_time_s") or cfg.get("cycle_time") or 3.0
    cycle_assumed = req.get("cycle_time_assumed", cfg.get("cycle_time_assumed"))
    install = (sel.get("project") or {}).get("installation") or cfg.get("installation") or "ETH"
    company = opts["company"]
    pc_dir = opts["pointcloud_dir"]
    rec = build_rec(hw, part_w, part_h, fov_margin,
                    (sel.get("error_budget") or {}).get("absolute_errors_mm") or {})
    tech_short = (cfg.get("technology_short")
                  or rec["technology"].split("（")[0].split("(")[0])

    wd = rec["recommended_wd_mm"]
    fov = rec["fov_at_wd_mm"]
    pitch = rec["xy_resolution_mm"]
    cam_err = rec["guidance_accuracy_mm"]
    cap_lo, cap_hi = rec["capture_time_s"]
    need_w = part_w * fov_margin
    need_h = part_h * fov_margin
    margin_w = fov["width"] / need_w * 100 - 100
    margin_h = fov["height"] / need_h * 100 - 100
    margin_col = GREEN if min(margin_w, margin_h) >= 0 else RED

    deck = Deck(opts["template"])
    prs, layout = deck.prs, deck.layout

    def new_slide(key=None):
        if not key:
            return deck.new_slide(None)
        title = PAGE_TITLES.get(key) or page_title(SECTION_TEXT, key)
        return deck.new_slide(title)

    # ---------- 1 封面 ----------
    s = new_slide()
    install_desc = ("ETH 眼在手外" if install == "ETH"
                    else "EIH 眼在手上" if install == "EIH" else install)
    deck.cover(
        s,
        cfg.get("project_name") or "3D 视觉引导抓取系统方案",
        f"{part_w:.0f} × {part_h:.0f} mm 产品　·　{install_desc}　·　6D 位姿引导抓取",
        f"工作距离 {wd:.0f} mm　|　单次视野 "
        f"{fov['width']:.0f} × {fov['height']:.0f} mm　|　{rec['ip_rating']}",
        company,
        date.today().isoformat()[:7].replace("-", "."),
    )

    # ---------- 2 目录 ----------
    s = new_slide()
    deck.toc(s, toc_items(SECTION_TEXT))

    # ---------- 3 项目需求 ----------
    s = new_slide("requirements")
    # 左：产品俯视示意。视野框按真实 FOV 比例，产品按真实尺寸比例，
    # 让客户一眼看出"单帧覆盖整个产品"。
    C3_X, C3_Y, C3_W, C3_H = 0.55, 0.98, 6.30, 5.55
    deck.box(s, C3_X, C3_Y, C3_W, C3_H, fill=WHITE, line=GRAY_L, line_w=0.75)
    fov_in_w = 5.30
    fov_in_h = fov_in_w * fov["height"] / fov["width"]
    fov_in_x = C3_X + (C3_W - fov_in_w) / 2
    fov_in_y = 1.72
    fov_rect = deck.box(s, fov_in_x, fov_in_y, fov_in_w, fov_in_h,
                        fill=None, line=BLUE, line_w=1.2)
    fov_rect.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    part_in_w = fov_in_w * part_w / fov["width"]
    part_in_h = fov_in_h * part_h / fov["height"]
    part_in_x = fov_in_x + (fov_in_w - part_in_w) / 2
    part_in_y = fov_in_y + (fov_in_h - part_in_h) / 2
    deck.box(s, part_in_x, part_in_y, part_in_w, part_in_h,
             fill=RGBColor(0xB8, 0xB8, 0xB8), line=GRAY, line_w=1.0)
    # 上表面结构特征（示意 6D 匹配所依赖的轮廓）
    for k in range(1, 4):
        yy = part_in_y + part_in_h * k / 4
        deck.line(s, part_in_x + 0.08, yy, part_in_x + part_in_w - 0.08, yy,
                  color=RGBColor(0x8C, 0x8C, 0x8C), width=0.75)
    deck.line(s, part_in_x + part_in_w * 0.62, part_in_y + 0.08,
              part_in_x + part_in_w * 0.62, part_in_y + part_in_h - 0.08,
              color=RGBColor(0x8C, 0x8C, 0x8C), width=0.75)
    deck.text(s, part_in_x - 0.40, part_in_y + part_in_h + 0.04,
              part_in_w + 0.80, 0.26,
              [{"text": f"{part_w:.0f} × {part_h:.0f}", "size": 9.5,
                "bold": True, "color": BLACK}], align=PP_ALIGN.CENTER)
    deck.text(s, fov_in_x, fov_in_y + fov_in_h + 0.06, fov_in_w, 0.26,
              [{"text": f"单帧视野 {fov['width']:.0f} × {fov['height']:.0f} mm",
                "size": 9.5, "color": BLUE}], align=PP_ALIGN.CENTER)
    deck.text(s, C3_X + 0.20, 5.50, C3_W - 0.40, 0.30,
              [{"text": "产品俯视示意：单帧视野完整覆盖工件，无需拼接",
                "size": 9.5, "color": GRAY}], align=PP_ALIGN.CENTER)

    # 右：客户需求
    deck.text(s, 7.15, 1.00, 5.60, 0.35,
              [{"text": "客户需求", "size": 15, "bold": True, "color": BLUE_D}])
    variants = cfg.get("product_variants")
    bottom = cfg.get("bottom_flatness") or ""
    reqs = [
        ("产品外形", f"{part_w:.0f} × {part_h:.0f} mm 工件，上表面为抓取参考面"),
        ("安装方式", f"{install_desc}，相机"
                     + ("固定于支架" if install == "ETH" else "随机器人运动")),
        ("拍照方式", cfg.get("trigger_mode") or "传送带挡停，静止拍照"),
        ("位姿维度", "6D（XYZ + RX/RY/RZ）"
                     + ("，底部不平需引导夹爪角度" if bottom else "")),
        ("换型", f"{variants}，数量待确认" if variants else "多型号，数量待确认"),
        ("节拍", f"{cycle:g} s/件" + ("（假设值，待确认）" if cycle_assumed else "")),
    ]
    for i, (k, v) in enumerate(reqs):
        y = 1.48 + i * 0.72
        deck.box(s, 7.15, y + 0.05, 0.09, 0.30, fill=BLUE)
        deck.text(s, 7.39, y, 1.25, 0.30,
                  [{"text": k, "size": 10.5, "bold": True, "color": BLUE_D}])
        deck.text(s, 8.62, y - 0.02, 4.15, 0.60,
                  [{"text": v, "size": 10.5, "color": BLACK}], line_spacing=1.08)
    deck.callout(s, 7.15, 5.92, 5.60, 0.72,
                 "核心目标：稳定输出 6D 位姿，把点云坐标准确转换为机器人抓取坐标。",
                 kind="warn")

    # ---------- 4 系统方案 ----------
    s = new_slide("system")
    deck.box(s, 0.55, 0.98, 6.55, 5.60, fill=WHITE, line=GRAY_L, line_w=0.75)
    if install == "ETH":
        # 固定支架：立柱 + 横梁 + 相机 + 光窗 + 传送带 + 机器人
        post_x, post_y, post_w, post_h = 4.42, 1.22, 0.14, 3.55
        beam_x, beam_y, beam_w, beam_h = 2.62, 1.22, 1.94, 0.13
        cam_x, cam_y, cam_w, cam_h = 2.78, 1.35, 1.20, 0.60
        win_x, win_y, win_w, win_h = 3.05, 1.95, 0.66, 0.20
        deck.box(s, post_x, post_y, post_w, post_h,
                 fill=RGBColor(0x8C, 0x8C, 0x8C), line=None)
        deck.box(s, beam_x, beam_y, beam_w, beam_h,
                 fill=RGBColor(0x8C, 0x8C, 0x8C), line=None)
        deck.text(s, 4.62, 1.28, 1.10, 0.3,
                  [{"text": "支架", "size": 11, "bold": True, "color": BLACK}])
        mount_label = "ETH 固定支架"
    else:
        # EIH：机器人立柱 + 横臂，相机挂在末端
        post_x, post_y, post_w, post_h = 4.55, 2.10, 0.16, 2.60
        beam_x, beam_y, beam_w, beam_h = 3.05, 2.10, 1.55, 0.16
        cam_x, cam_y, cam_w, cam_h = 2.75, 2.26, 0.66, 0.52
        win_x, win_y, win_w, win_h = 2.85, 2.78, 0.46, 0.14
        deck.box(s, post_x, post_y, post_w, post_h,
                 fill=RGBColor(0x40, 0x40, 0x40), line=None)
        deck.box(s, beam_x, beam_y, beam_w, beam_h,
                 fill=RGBColor(0x40, 0x40, 0x40), line=None)
        deck.text(s, 4.80, 2.02, 1.40, 0.3,
                  [{"text": "机器人（EIH）", "size": 10, "bold": True, "color": BLACK}])
        mount_label = "EIH 机器人末端"

    cam_box = deck.box(s, cam_x, cam_y, cam_w, cam_h,
                       fill=RGBColor(0x33, 0x33, 0x33), line=GRAY, line_w=0.75)
    win_box = deck.box(s, win_x, win_y, win_w, win_h,
                       fill=RGBColor(0x0D, 0x0D, 0x0D), line=None)
    box_part_x, box_part_y, box_part_w = 2.15, 4.62, 1.80
    conv_x, conv_y, conv_w, conv_h = 1.30, 4.86, 3.55, 0.20
    deck.line(s, win_x, win_y + win_h, box_part_x, box_part_y,
              color=BLUE, width=1.0, dash=MSO_LINE_DASH_STYLE.DASH)
    deck.line(s, win_x + win_w, win_y + win_h, box_part_x + box_part_w, box_part_y,
              color=BLUE, width=1.0, dash=MSO_LINE_DASH_STYLE.DASH)
    part_box = deck.box(s, box_part_x, box_part_y, box_part_w, 0.30,
                        fill=BLUE, line=None)
    deck.text(s, box_part_x, box_part_y + 0.04, box_part_w, 0.24,
              [{"text": f"产品 {part_w:.0f}×{part_h:.0f}", "size": 9.5,
                "bold": True, "color": WHITE}], align=PP_ALIGN.CENTER)
    deck.box(s, conv_x, conv_y, conv_w, conv_h,
             fill=RGBColor(0x8C, 0x8C, 0x8C), line=None)

    deck.text(s, 1.35, 1.30, 1.15, 0.3,
              [{"text": "3D 相机", "size": 11, "bold": True, "color": BLACK}])
    deck.line(s, 2.48, 1.45, cam_x - 0.02, cam_y + 0.20,
              color=GRAY, width=0.75, arrow=True)
    deck.text(s, win_x + win_w + 0.28, win_y + 0.02, 1.55, 0.28,
              [{"text": "光窗（投影+成像）", "size": 8.5, "color": GRAY}])
    deck.line(s, win_x + win_w + 0.26, win_y + 0.10, win_x + win_w + 0.02, win_y + 0.10,
              color=GRAY, width=0.6, arrow=True)
    deck.text(s, 1.30, 5.12, 1.90, 0.28,
              [{"text": "传送带（挡停静止）", "size": 9, "color": GRAY}])
    deck.text(s, 2.72, 3.18, 1.60, 0.28,
              [{"text": f"FOV {fov['width']:.0f}×{fov['height']:.0f}",
                "size": 10, "bold": True, "color": BLUE}])
    deck.text(s, 2.72, 3.44, 1.60, 0.28,
              [{"text": f"点距 {pitch:.3f} mm", "size": 9, "color": BLUE}])
    add_wd_dim(s, 1.48, f"{wd:.0f}mm", win_box, part_box,
               color=GRAY, box_w=0.74, text_gap=0.06)
    issues = self_check(s)
    if issues:
        raise SystemExit("尺寸标注自检失败: " + "; ".join(issues))

    # 右：系统组成
    deck.text(s, 7.40, 0.98, 5.35, 0.35,
              [{"text": "系统组成", "size": 15, "bold": True, "color": BLUE_D}])
    sw_list = rec["software"] if isinstance(rec["software"], list) else []
    comp = [
        ("视觉单元", f"{rec['brand']} {rec['model']} + 工控机 + 视觉软件"),
        ("安装单元", f"{mount_label}，工作距离 {wd:.0f} mm"
                     + ("，标定一次长期有效" if install == "ETH" else "，随机器人运动")),
        ("执行单元", "机器人 + 夹爪，接收 6D 位姿"),
        ("通讯单元", f"{rec['interface']} 采图；PLC 硬触发；位姿以太网上传；NG/OK 回 PLC"),
    ]
    for i, (k, v) in enumerate(comp):
        y = 1.45 + i * 1.02
        deck.box(s, 7.40, y + 0.05, 0.10, 0.72, fill=BLUE)
        deck.text(s, 7.62, y, 1.10, 0.32,
                  [{"text": k, "size": 11.5, "bold": True, "color": BLUE_D}])
        deck.text(s, 8.68, y - 0.02, 4.05, 0.90,
                  [{"text": v, "size": 10.5, "color": BLACK}], line_spacing=1.06)
    deck.box(s, 7.40, 5.55, 5.30, 0.95, fill=BLUE_L, line=None)
    deck.text(s, 7.56, 5.55, 5.02, 0.95,
              [{"text": "工作流", "size": 10, "bold": True, "color": BLUE_D},
               {"text": "挡停到位 → PLC 触发 → 3D 采集 → 点云匹配 → 6D 位姿 → 机器人抓取 → 放行",
                "size": 10, "color": BLACK}], line_spacing=1.05,
              anchor=MSO_ANCHOR.MIDDLE)

    # ---------- 5 工作流程 ----------
    s = new_slide("workflow")
    vis_lo = cap_lo + 0.35
    vis_hi = cap_hi + 0.85
    steps = [
        ("01", "挡停到位", "传送带挡停\n工件静止\n等待触发", "—"),
        ("02", "PLC 触发", "到位信号\n硬触发相机\nIO 触发", "<20 ms"),
        ("03", "3D 采集", f"{tech_short}\n静态多曝光\n有序点云", "按型号"),
        ("04", "点云匹配", "模板配准\n输出 6D 位姿\n匹配评分", "0.3~0.8 s"),
        ("05", "位姿下发", "以太网\n机器人接收\nTCP/IP", "<50 ms"),
        ("06", "机器人抓取", "夹爪下爪\n放行\nNG/OK", "按节拍"),
    ]
    deck.step_cards(s, 1.10, steps, card_h=2.85, desc_size=10)

    cycle_note = (f"最坏 {vis_hi:.1f} s，节拍 {cycle:g} s 尚余 {cycle - vis_hi:.1f} s。"
                  if vis_hi < cycle else
                  f"最坏 {vis_hi:.1f} s 已超节拍 {cycle:g} s，需按实际采集参数复核。")
    deck.box(s, 0.62, 4.20, 6.05, 0.95, fill=BLUE_L, line=None)
    deck.text(s, 0.78, 4.20, 5.75, 0.95,
              [{"text": f"视觉侧合计约 {vis_lo:.1f}~{vis_hi:.1f} s"
                        + (f"（节拍 {cycle:g} s 为假设值）" if cycle_assumed
                           else f"（节拍 {cycle:g} s）"),
                "size": 11.5, "bold": True, "color": BLUE_D},
               {"text": cycle_note + "静态拍照可多曝光合成，最高精度模式耗时更长。",
                "size": 9.5, "color": GRAY}], line_spacing=1.05,
              anchor=MSO_ANCHOR.MIDDLE)

    deck.text(s, 6.95, 4.20, 5.75, 0.32,
              [{"text": "通讯接口", "size": 11, "bold": True, "color": BLUE_D}])
    deck.text(s, 6.95, 4.54, 5.75, 1.70,
              [{"text": f"相机接口：{rec['interface']}", "size": 10, "color": BLACK},
               {"text": f"防护等级：{rec['ip_rating']}", "size": 10, "color": BLACK},
               {"text": "触发：PLC 到位信号硬触发（IO）", "size": 10, "color": BLACK},
               {"text": "位姿：以太网 TCP/IP 上传机器人", "size": 10, "color": BLACK},
               {"text": "结果：NG/OK 信号回 PLC", "size": 10, "color": BLACK}],
              line_spacing=1.30)

    deck.box(s, 0.62, 5.35, 6.05, 0.85, fill=RED_L, line=None)
    deck.text(s, 0.78, 5.35, 5.75, 0.85,
              [{"text": "异常处理", "size": 10, "bold": True, "color": RED},
               {"text": "采集超时或点云质量不合格 → 输出 NG 信号 → 产品流入 NG 通道，禁止机器人盲抓。",
                "size": 9.5, "color": BLACK}], line_spacing=1.08,
              anchor=MSO_ANCHOR.MIDDLE)

    # ---------- 6 硬件选型 ----------
    s = new_slide("hardware")
    deck.box(s, 0.55, 0.98, 5.35, 5.55, fill=WHITE, line=GRAY_L, line_w=0.75)
    cam6 = deck.box(s, 2.05, 1.45, 1.55, 0.80,
                    fill=RGBColor(0x33, 0x33, 0x33), line=GRAY, line_w=0.75)
    win6 = deck.box(s, 2.38, 2.25, 0.90, 0.20,
                    fill=RGBColor(0x0D, 0x0D, 0x0D), line=None)
    part6 = deck.box(s, 1.60, 5.30, 2.45, 0.28, fill=BLUE, line=None)
    deck.box(s, 1.15, 5.58, 3.35, 0.18,
             fill=RGBColor(0x8C, 0x8C, 0x8C), line=None)
    deck.line(s, 2.38, 2.45, 1.60, 5.30,
              color=BLUE, width=1.0, dash=MSO_LINE_DASH_STYLE.DASH)
    deck.line(s, 3.28, 2.45, 4.05, 5.30,
              color=BLUE, width=1.0, dash=MSO_LINE_DASH_STYLE.DASH)
    deck.text(s, 3.80, 1.58, 1.60, 0.30,
              [{"text": "3D 相机", "size": 11, "bold": True, "color": BLACK}])
    deck.line(s, 3.76, 1.72, 3.62, 1.72, color=GRAY, width=0.75, arrow=True)
    deck.text(s, 3.80, 2.30, 1.95, 0.30,
              [{"text": "光窗（WD 起算面）", "size": 8.5, "color": GRAY}])
    deck.line(s, 3.76, 2.40, 3.32, 2.38, color=GRAY, width=0.6, arrow=True)
    deck.text(s, 1.30, 5.82, 3.10, 0.28,
              [{"text": "传送带（挡停静止）", "size": 9, "color": GRAY}])
    add_wd_dim(s, 1.30, f"{wd:.0f}mm", win6, part6,
               color=GRAY, box_w=0.74, text_gap=0.06)
    issues = self_check(s)
    if issues:
        raise SystemExit("尺寸标注自检失败: " + "; ".join(issues))
    deck.text(s, 0.55, 6.16, 5.35, 0.30,
              [{"text": f"{install_desc}，工作距离从光窗到产品上表面",
                "size": 9, "color": GRAY}], align=PP_ALIGN.CENTER)

    deck.text(s, 6.20, 1.00, 6.40, 0.30,
              [{"text": "推荐型号", "size": 11, "bold": True, "color": BLUE}])
    deck.text(s, 6.20, 1.30, 6.40, 0.45,
              [{"text": f"{rec['brand']} {rec['model']}", "size": 20,
                "bold": True, "color": BLUE_D}])
    deck.text(s, 6.20, 1.80, 6.40, 0.30,
              [{"text": f"{rec['technology']}　·　{rec['ip_rating']}",
                "size": 10.5, "color": GRAY}])
    wd_range = rec["working_distance_range_mm"]
    wd_range_txt = (f"{wd_range[0]}–{wd_range[1]} mm"
                    if all(wd_range) else "见规格")
    acc_num = f"{cam_err:.2f}" if cam_err < 1 else f"{cam_err:.1f}"
    acc_txt = f"±{acc_num} mm"
    acc_label = "引导精度（估算）" if rec["guidance_is_estimate"] else "引导精度（标称）"
    rows = [
        ["项目", "参数"],
        ["工作距离", f"{wd:.0f} mm（{wd_range_txt}）"],
        ["该距离视野", f"{fov['width']:.0f} × {fov['height']:.0f} mm"],
        ["点间距", f"{pitch:.3f} mm"],
        [acc_label, acc_txt],
        ["采集时间", f"{cap_lo:g}–{cap_hi:g} s"],
        ["防护 / 接口", f"{rec['ip_rating']} / {rec['interface']}"],
    ]
    deck.table(s, 6.20, 2.20, 6.35, [2.05, 4.30], rows,
               row_h=0.50, font=10.5, first_col_bold=True)
    note = (f"视野按 {part_w:.0f}×{part_h:.0f} × {fov_margin:g} 余量校核；"
            + ("引导精度按标称 Z/VDI 与点距估算，以真实工件打样实测确认。"
               if rec["guidance_is_estimate"] else
               "引导精度为厂商标称值，以真实工件打样实测确认。"))
    if sw_list:
        note += "\n配套软件：" + " / ".join(sw_list)
    deck.text(s, 6.20, 5.92, 6.35, 0.62,
              [{"text": note, "size": 9, "color": GRAY}], line_spacing=1.06)

    # ---------- 7 点云成像效果 ----------
    s = new_slide("special_a")
    # 图片来源判定：三张全部实拍才标"实采"；用了缺省图就标"同型号典型成像"，
    # 不得把缺省图说成本工件实采（客户会当成实测结论）。
    pc_files = ("pc_top.png", "pc_slant_a.png", "pc_slant_b.png")
    all_real = all(os.path.exists(os.path.join(pc_dir, f)) for f in pc_files)
    allow_default = not opts.get("no_default_pointcloud")
    has_default = allow_default and all(
        os.path.exists(os.path.join(DEFAULT_PC_DIR, f)) for f in pc_files)
    src_tag = "实采" if all_real else ("同型号典型成像" if has_default else "")
    deck.text(s, 0.62, 0.90, 12.10, 0.32,
              [{"text": f"{rec['brand']} {rec['model']}"
                        + (f" {src_tag}" if src_tag else "")
                        + f"　·　{tech_short}　·　点间距 {pitch:.2f} mm",
                "size": 12, "color": GRAY}])

    def img_or_ph(x, y, w, h, fname, label):
        """图位填充：用户实拍图 > skill 内置缺省图 > 占位框。"""
        for src in [pc_dir] + ([DEFAULT_PC_DIR] if allow_default else []):
            path = os.path.join(src, fname)
            if os.path.exists(path):
                deck.picture(s, path, x, y, w, h)
                return "user" if src == pc_dir else "default"
        deck.box(s, x, y, w, h, fill=BLUE_LL, line=GRAY_L, line_w=0.75)
        deck.text(s, x, y + h / 2 - 0.18, w, 0.36,
                  [{"text": label, "size": 10, "color": GRAY}], align=PP_ALIGN.CENTER)
        return None

    img_or_ph(0.55, 1.30, 5.60, 4.36, "pc_top.png", "点云素材待补：pc_top.png")
    pc_note = "俯视点云"
    if cfg.get("point_count"):
        pc_note += f" · 单帧 {int(cfg['point_count']):,} 点"
    deck.text(s, 0.55, 5.72, 5.60, 0.26,
              [{"text": pc_note, "size": 9, "color": GRAY}])
    img_or_ph(6.45, 1.30, 2.89, 2.40, "pc_slant_a.png", "待补：pc_slant_a.png")
    deck.text(s, 6.45, 3.76, 2.89, 0.26,
              [{"text": "斜视 · 高度与凹槽结构", "size": 9, "color": GRAY}])
    img_or_ph(9.54, 1.30, 3.20, 2.40, "pc_slant_b.png", "待补：pc_slant_b.png")
    deck.text(s, 9.54, 3.76, 3.20, 0.26,
              [{"text": "斜视 · 边缘轮廓与台阶", "size": 9, "color": GRAY}])

    deck.box(s, 0.55, 6.02, 5.60, 0.66, fill=BLUE_LL, line=None)
    deck.text(s, 0.70, 6.02, 5.30, 0.66,
              [{"text": "采集设置", "size": 9.5, "bold": True, "color": BLUE_D},
               {"text": f"{tech_short} · 多曝光合成 · "
                        f"单次采集 {cap_lo:g}–{cap_hi:g}s · 输出有序点云 + 法向量",
                "size": 8.5, "color": GRAY}], line_spacing=1.10,
              anchor=MSO_ANCHOR.MIDDLE)

    surf = cfg.get("surface_condition") or ""
    if "待确认" in surf:
        surf_bullet = ("表面适应", "深色 / 反光表面需打样确认曝光参数与点云完整性")
    else:
        surf_bullet = ("表面适应", "深色金属件点云连续、无明显空洞")
    has_pc = os.path.exists(os.path.join(pc_dir, "pc_top.png"))
    if all_real:
        bullets = [
            ("完整覆盖", f"{part_w:.0f}×{part_h:.0f} 工件单帧完整覆盖，点间距 {pitch:.2f} mm"),
            ("结构清晰", "加强筋、凹槽、孔位清晰，可直接用于 6D 位姿匹配"),
            surf_bullet,
        ]
    elif has_default or has_pc:
        # 缺省图 / 部分实拍：只描述相机成像能力，不绑定本工件尺寸与具体特征
        bullets = [
            ("完整覆盖", f"单帧完整覆盖工件，点间距 {pitch:.2f} mm"),
            ("结构清晰", "轮廓、凹槽、孔位清晰，可直接用于 6D 位姿匹配"),
            surf_bullet,
        ]
    else:
        bullets = [
            ("待打样", "点云覆盖、结构清晰度与表面适应性以真实工件打样结果为准"),
        ]
    for i, (t, d) in enumerate(bullets):
        y = 4.35 + i * 0.72
        deck.box(s, 6.45, y + 0.06, 0.09, 0.42, fill=BLUE)
        deck.text(s, 6.66, y, 6.10, 0.27,
                  [{"text": t, "size": 10.5, "bold": True, "color": BLUE_D}])
        deck.text(s, 6.66, y + 0.26, 6.10, 0.30,
                  [{"text": d, "size": 9.5, "color": BLACK}])

    # ---------- 8 6D 位姿与 RZ ----------
    s = new_slide("special_b")
    flow = ["点云采集", "平面拟合", "模板配准", "位姿解算", "坐标转换", "输出 6D 位姿"]
    fw, fg = 1.80, 0.26
    for i, t in enumerate(flow):
        x = 0.62 + i * (fw + fg)
        deck.box(s, x, 1.05, fw, 0.52, fill=BLUE, line=None,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.14)
        deck.text(s, x, 1.15, fw, 0.32,
                  [{"text": t, "size": 10.5, "bold": True, "color": WHITE}],
                  align=PP_ALIGN.CENTER)
        if i < len(flow) - 1:
            deck.line(s, x + fw + 0.02, 1.31, x + fw + fg - 0.02, 1.31,
                      color=BLUE, width=1.5, arrow=True)

    deck.text(s, 0.62, 1.88, 6.05, 0.32,
              [{"text": "位姿可观测性", "size": 13, "bold": True, "color": BLUE_D}])
    obs = [["自由度", "可观测性", "依赖信息"],
           ["X / Y 平移", "可观测", "点云整体位置"],
           ["Z 高度", "可观测", "上表面高度"],
           ["RX / RY 倾斜", "可观测", "上表面平面拟合"],
           ["RZ 绕法向旋转", "弱 / 不可观测", "外轮廓、2D 纹理、CAD 模板"]]
    deck.table(s, 0.62, 2.28, 6.05, [1.75, 1.75, 2.55], obs,
               row_h=0.55, font=10.5)

    deck.text(s, 6.95, 1.88, 5.75, 0.32,
              [{"text": "关键点", "size": 13, "bold": True, "color": BLUE_D}])
    kps = [
        ("RZ 是难点", "上表面无特征平面时，RZ 无法从点云解出，需外轮廓 / 2D 纹理 / 机械定位"),
        ("底部不平", "导致 RX/RY 偏差；夹爪下压可能使产品变形或翻转"),
        ("对策", "3D CAD 模板匹配、2D + 点云融合、柔性夹爪 / 两步调姿"),
        ("需提供", "各型号 3D CAD 模型，或确认上表面存在可辨识特征"),
    ]
    for i, (k, v) in enumerate(kps):
        y = 2.28 + i * 0.80
        deck.box(s, 6.95, y + 0.05, 0.09, 0.30, fill=BLUE)
        deck.text(s, 7.19, y, 5.35, 0.28,
                  [{"text": k, "size": 10.5, "bold": True, "color": BLUE_D}])
        deck.text(s, 7.19, y + 0.28, 5.35, 0.48,
                  [{"text": v, "size": 9.5, "color": BLACK}], line_spacing=1.06)

    deck.callout(s, 0.62, 5.60, 12.10, 0.80,
                 "结论：XYZ + RX/RY 由点云直接解算，RZ 依赖外轮廓或 2D 纹理——"
                 "这是打样阶段首要验证项。", kind="warn")

    # ---------- 9 视野与工作距离校核 ----------
    s = new_slide("special_c")
    cards = [
        ("产品外形", f"{part_w:.0f} × {part_h:.0f} mm", GRAY),
        ("需求视野（×%g）" % fov_margin, f"{need_w:.0f} × {need_h:.0f} mm", GRAY),
        ("实际视野", f"{fov['width']:.0f} × {fov['height']:.0f} mm", BLUE_D),
        ("视野余量", f"{margin_w:+.0f}% / {margin_h:+.0f}%", margin_col),
    ]
    for i, (k, v, col) in enumerate(cards):
        x = 0.62 + i * 3.08
        deck.box(s, x, 1.02, 2.88, 1.05, fill=BLUE_LL, line=BLUE_L, line_w=0.9,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
        deck.text(s, x + 0.16, 1.10, 2.55, 0.3,
                  [{"text": k, "size": 10, "color": GRAY}])
        deck.text(s, x + 0.16, 1.40, 2.60, 0.45,
                  [{"text": v, "size": 15, "bold": True, "color": col}])

    deck.text(s, 0.62, 2.30, 6.2, 0.3,
              [{"text": "来料旋转敏感性", "size": 13, "bold": True, "color": BLUE_D}])
    rot_rows = [["旋转角", "产品外接尺寸", "所需视野", "判定"]]
    rot_all_ok = True
    for deg in (0, 5, 10, 45):
        rw, rh = rotated_size(part_w, part_h, deg)
        need_w, need_h = rw * fov_margin, rh * fov_margin
        ok = need_w <= fov["width"] and need_h <= fov["height"]
        rot_all_ok = rot_all_ok and ok
        rot_rows.append([f"±{deg}°", f"{rw:.0f} × {rh:.0f} mm",
                         f"{need_w:.0f} × {need_h:.0f} mm",
                         "满足" if ok else "视野不足"])
    deck.table(s, 0.62, 2.68, 6.30, [1.40, 1.60, 1.95, 1.35], rot_rows,
               row_h=0.52, font=10)
    w45 = rotated_width(part_w, part_h, 45)
    concl = (f"结论：来料 ±45° 任意角度（外接圆 {w45:.0f}mm）仍在视野内，"
             "安装位置有充足调整空间。" if rot_all_ok else
             f"结论：±45° 时外接圆 {w45:.0f}mm 超出视野，"
             "需加大工作距离或选更大视野型号。")
    deck.text(s, 0.62, 5.50, 6.30, 0.80,
              [{"text": concl, "size": 10.5,
                "color": BLACK if rot_all_ok else RED}], line_spacing=1.12)

    deck.text(s, 7.20, 2.30, 5.55, 0.3,
              [{"text": "工作距离取值", "size": 13, "bold": True, "color": BLUE_D}])
    wd_rows = [
        ["项目", "值"],
        ["推荐工作距离", f"{wd:.0f} mm（光窗 → 产品上表面）"],
        ["允许范围", wd_range_txt],
        ["点间距", f"{pitch:.3f} mm"],
        [acc_label, acc_txt],
    ]
    deck.table(s, 7.20, 2.68, 5.55, [1.75, 3.80], wd_rows, row_h=0.55, font=10,
               first_col_bold=True)
    deck.text(s, 7.20, 5.62, 5.55, 0.55,
              [{"text": "工作点取最佳成像距离，视野与精度兼顾。",
                "size": 10, "color": GRAY}], line_spacing=1.05)

    # ---------- 10 系统架构 ----------
    s = new_slide("architecture")
    deck.text(s, 0.90, 1.55, 11.53, 0.45,
              [{"text": "系统采用分层架构，从点云采集到抓取执行形成闭环，确保引导稳定可靠。",
                "size": 14, "color": GRAY}], align=PP_ALIGN.CENTER)
    deck.arch_row(s, 2.75, [
        ("感知层", "3D 采集", "相机与工控机协同，单帧获取完整点云。"),
        ("处理层", "点云处理", "滤波、法向估计、平面拟合与模板配准，输出候选位姿。"),
        ("决策层", "位姿判定", "校验匹配得分与可达性，判定 OK/NG，生成抓取位姿。"),
        ("执行层", "引导抓取", "位姿经以太网下发机器人，夹爪完成抓取与放行。"),
    ], h=2.10)
    deck.callout(s, 0.62, 5.65, 12.10, 0.75,
                 "全链路可追溯：点云、位姿、判定结果与节拍写入日志，"
                 "支持按时间段与型号查询。", kind="info", bold=False)

    # ---------- 11 实施与验收 ----------
    s = new_slide("delivery")
    calib = "ETH 手眼标定" if install == "ETH" else "EIH 手眼标定"
    deck.col_cards(s, 1.05, [
        ("实施步骤", ["需求与接口确认", "相机 / 支架采购", "支架安装与接线",
                      calib, "PLC / 机器人联调", "试产与节拍验证"]),
        ("标定与换型", ["标定板 20+ 位姿标定", "标定球 5 点验证", "各型号 3D 模板制作",
                        "采集参数分型号配置", "换型流程演练", "漂移复检机制"]),
        ("验收标准", ["连续 30 件抓取验证", "引导精度按打样实测确认",
                      f"节拍 ≤ {cycle:g} s/件", "NG 判定 100% 报警",
                      "标定报告 / 操作说明", "通讯协议与点位表交付"]),
    ], h=4.50, item_size=12, space_after=27)
    deck.box(s, 0.62, 5.78, 12.10, 0.72, fill=BLUE_LL, line=None)
    deck.text(s, 0.78, 5.86, 11.80, 0.58,
              [{"text": "周期预估：设计确认 1 周 + 样件打样 1–2 周 + 设备制造 3–4 周 + "
                        "现场安装 3–5 天 + 试产爬坡 1–2 周。",
                "size": 10, "color": GRAY}], line_spacing=1.05)

    # ---------- 12 谢谢 ----------
    s = new_slide()
    deck.thanks(s, company)

    # ---------- 删除模板原有页面 ----------
    for i in sorted(range(len(prs.slides._sldIdLst) - len(STANDARD_PAGES)), reverse=True):
        deck.kill_slide(prs, i)

    deck.finalize(company, first_page_no=1, footer_from=2)
    return deck


# ==================== CLI ====================
def auto_select(cfg_path, cfg_dir):
    """selection 缺失时自动补：调 three_d_selector.py 选型。

    选型失败时把报告原样透出后停止——禁止兜底填数字。
    """
    ts = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "three_d_selector.py")
    if not os.path.exists(ts):
        return False
    print("[选型] 未找到 three_d_selection.json，自动调用选型……")
    r = subprocess.run([sys.executable, ts, "--config", cfg_path], cwd=cfg_dir)
    return r.returncode == 0


def parse_args():
    ap = argparse.ArgumentParser(description="3D 视觉引导抓取方案 PPT 生成器（客户版）")
    ap.add_argument("--config", required=True, help="project_config_3d.json")
    ap.add_argument("--selection",
                    help="three_d_selection.json（默认 config 同目录或 <project_name>/）")
    ap.add_argument("--template", help="母版 pptx（默认在工作区自动发现「视觉检测方案.pptx」）")
    ap.add_argument("--pointcloud-dir",
                    help="点云图目录（默认 <project_name>/点云图/crop；缺图回退 skill 内置缺省图）")
    ap.add_argument("--no-default-pointcloud", action="store_true",
                    help="禁用 skill 内置缺省点云图（缺图位置画占位框，仅排障/内部评审）")
    ap.add_argument("--company", default=DEFAULT_COMPANY, help="公司名")
    ap.add_argument("--out", help="输出 pptx（默认 <config目录>/<project_name>/<project_name>.pptx）")
    ap.add_argument("--no-auto-select", action="store_true",
                    help="selection 缺失时不自动补选型（仅排障）")
    ap.add_argument("--no-check", action="store_true", help="跳过机检（仅排障）")
    ap.add_argument("--no-preview", action="store_true", help="跳过逐页预览导出")
    return ap.parse_args()


def main():
    args = parse_args()
    cfg_path = os.path.abspath(args.config)
    if not os.path.exists(cfg_path):
        raise SystemExit(f"[输入] config 不存在: {cfg_path}")
    cfg_dir = os.path.dirname(cfg_path)
    cfg = load_json(cfg_path)

    # 2D 配置误传给 3D 入口：先指路，避免弱模型去"补 part_size"把 2D 配置改坏
    if not cfg.get("installation") and cfg.get("detection_type"):
        raise SystemExit(
            "[输入] 这是 2D 配置（含 detection_area / detection_type），"
            "不是 3D 配置。\n"
            '2D 请用：python "<skill>\\tools\\two_d_ppt.py" '
            '--config "<工作区>\\project_config.json"')

    project_name = cfg.get("project_name") or "3D视觉引导抓取系统方案"
    # 依次尝试：config 同目录 → 输出目录（selector 默认落在 <project_name>/）
    cands = [os.path.join(cfg_dir, "three_d_selection.json"),
             os.path.join(cfg_dir, project_name, "three_d_selection.json")]
    if args.selection:
        sel_path = args.selection
    else:
        sel_path = next((p for p in cands if os.path.exists(p)), cands[0])
        if not os.path.exists(sel_path) and not args.no_auto_select:
            auto_select(cfg_path, cfg_dir)
            sel_path = next((p for p in cands if os.path.exists(p)), cands[0])
    if not os.path.exists(sel_path):
        raise SystemExit(
            f"[输入] selection 不存在: {sel_path}\n"
            "两条路任选：\n"
            "  1) 直接重跑本命令（会自动补选型）\n"
            "  2) 先手动跑 three_d_selector.py --config <config>\n"
            "选型报无解时把缺口报告原文转给用户，禁止改参数试探。")
    sel = load_json(sel_path)

    if not os.path.exists(HW_DB_PATH):
        raise SystemExit(f"[输入] 硬件库不存在: {HW_DB_PATH}")
    hw_db = load_json(HW_DB_PATH)

    model, source = pick_locked_model(sel)
    hw = next((c for c in hw_db.get("three_d_cameras", []) if c["model"] == model), None)
    if hw is None:
        raise SystemExit(f"[输入] 硬件库里没有型号 {model}（来源 {source}）")

    template = args.template or discover_template(cfg_dir)
    if not template or not os.path.exists(template):
        raise SystemExit(f"[输入] 未找到母版 pptx：请把「视觉检测方案.pptx」放到 {cfg_dir}，"
                         "或用 --template 指定")

    project_name = cfg.get("project_name") or "3D视觉引导抓取系统方案"
    out = args.out or os.path.join(cfg_dir, project_name, project_name + ".pptx")
    pc_dir = args.pointcloud_dir or next(
        (p for p in (os.path.join(cfg_dir, project_name, "点云图", "crop"),
                     os.path.join(cfg_dir, "点云图", "crop"))
         if os.path.isdir(p)),
        os.path.join(cfg_dir, project_name, "点云图", "crop"))

    print(f"[数据] 型号: {hw['brand']} {hw['model']}（来源: {source}）")
    print(f"[模板] {os.path.basename(template)}")
    print(f"[点云] {pc_dir}" + ("" if os.path.isdir(pc_dir) else "（目录不存在）"))
    if args.no_default_pointcloud:
        print("[点云] 已禁用缺省图（--no-default-pointcloud）：缺图位置画占位框")
    else:
        print(f"[点云] 缺省图: {DEFAULT_PC_DIR}（用户图缺失位置逐张回退）")

    deck = build_deck(cfg, sel, hw, {
        "template": template,
        "company": args.company,
        "pointcloud_dir": pc_dir,
        "no_default_pointcloud": args.no_default_pointcloud,
    })
    deck.save(out)

    ok = True
    if not args.no_check:
        print("\n[机检] check_ppt_quality.py")
        ok = run_quality_check(out, selection=sel_path)
        if not ok:
            print("[机检] 未通过：按报告修正后重跑；禁止带 FAIL 交付")
    if not args.no_preview:
        print("\n[预览] export_ppt_images.py")
        export_preview(out, os.path.join(os.path.dirname(out), "ppt_review"))

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
