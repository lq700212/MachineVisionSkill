# -*- coding: utf-8 -*-
"""2D 视觉定位/贴片方案 PPT 生成器（skill 正式入口，客户版）。

换项目只改配置，不写 Python：
    python two_d_ppt.py --config project_config.json

输入
----
  --config          project_config.json（可选；只给 --selection 也能跑）
  --selection       selection_result.json（默认在 config 同目录依次查找）
  --template        母版 pptx（默认在工作区自动发现「视觉检测方案.pptx」）
  --hardware-page   母版里硬件页的 0 基索引（默认 3，即第 4 页）
  --company         公司名（默认 苏州华际光电科技有限公司）
  --out             输出 pptx（默认 <config目录>/<project_name>/<project_name>.pptx）
  --no-check        跳过机检（仅排障，交付禁用）
  --no-preview      跳过导出逐页预览

复用关系（维护只改被复用的模块）
--------------------------------
  章节骨架 / 版式 / 封面 / 目录 / 流程卡 / 三栏卡 / 架构图 / 结论条
      → ppt_layout.py（STANDARD_PAGES / STANDARD_SECTIONS / Deck）
  工作距离标注 + 构建期自检
      → ppt_diagram.py（add_wd_dim / self_check）
  机检 / 逐页预览
      → ppt_layout.run_quality_check / export_preview（subprocess 调用）
  型号 / 精度 / 视野 / 像素当量
      → selection_result.json（vision_proposal_generator.py 产出，与选型同源）

与 3D 生成器的关系
------------------
两本 PPT 共用同一份 12 页骨架（STANDARD_PAGES），只有专项页内容不同：
  2D 专项页：选型计算链 / 视觉算法 / 精度分析
  3D 专项页：点云成像 / 6D 位姿 / 视野校核
本文件只保留 2D 特有页面与「母版硬件页替换」机制。
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import date

from PIL import Image
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Emu

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ppt_layout import (Deck, STANDARD_PAGES, toc_items, page_title,  # noqa: E402
                        discover_template, run_quality_check, export_preview,
                        BLUE_D, BLUE, BLUE_L, BLUE_LL, RED, GRAY, GRAY_L,
                        BLACK, WHITE)
from ppt_diagram import add_wd_dim, self_check  # noqa: E402

SKILL_DIR = os.path.dirname(HERE)
DEFAULT_COMPANY = "苏州华际光电科技有限公司"

# 目录文案（编号与页序由 STANDARD_SECTIONS 决定）
SECTION_TEXT = {
    "requirements": ("项目需求", "工件特征、贴合精度与节拍"),
    "system": ("系统方案", "布局、系统组成与节拍"),
    "hardware": ("硬件选型", "相机、镜头、光源与选型计算"),
    "special_b": ("视觉算法", "圆心定位与坐标转换"),
    "special_c": ("精度分析", "误差链与余量校核"),
    "delivery": ("实施与验收", "实施步骤、标定与验收标准"),
}

# 页面标题（完整映射；目录名称之外可写更具体的标题）
PAGE_TITLES = {
    "requirements": "项目需求",
    "system": "系统方案",
    "workflow": "工作流程",
    "hardware": "硬件选型",
    "special_a": "选型计算",
    "special_b": "视觉算法",
    "special_c": "精度分析",
    "architecture": "系统架构",
    "delivery": "实施与验收",
}

# 2D 场景文案默认值（贴片/定位类项目）；config.scene 可逐项覆盖
DEFAULT_SCENE = {
    "subtitle": "圆孔圆心视觉定位  ·  PLC / 机器人自动贴片",
    "part_feature": "圆孔 Φ8~9 mm，贴片覆盖在孔口上，将孔封住",
    "core_goal": "稳定提取圆孔圆心，并把像素坐标准确转换为机器人贴片坐标。",
    "target_label": "贴片",        # 工件示意图上的覆盖物标签
    "accuracy_label": "贴合精度",   # 需求行标签
    "accuracy_item": "贴片中心与孔中心偏差",  # 需求行说明
    "acceptance_item": "孔心偏差",  # 验收标准条目名
}

# 精度误差链默认值（贴片类项目典型值）；config.precision_chain 可覆盖
DEFAULT_CHAIN = [
    ["视觉圆心重复性", 0.02, "亚像素边缘 + 圆拟合"],
    ["镜头畸变 / 标定残差", 0.03, "TV 畸变 0.02%，棋盘格校正"],
    ["手眼标定误差", 0.05, "九点标定，覆盖整个工作视野"],
    ["机器人重复定位", 0.05, "按常规 SCARA / 六轴设备指标"],
    ["吸嘴中心偏差", 0.05, "吸嘴中心标定后补偿"],
]

# 母版硬件页契约（视觉检测方案.pptx 第 4 页）；换母版才需要改这里
HW_PIC_SLOTS = {
    "图片 7": ("camera", None),                      # 相机：取 selection.image_path
    "图片 6": ("lens", (6.55, 2.78, 1.15, 1.48)),    # 镜头：放大，避免被框架压小
    "图片 19": ("light", None),                      # 环光：保持原位
}
HW_FIXED_PICS = {
    "lens": os.path.join(SKILL_DIR, "assets", "part_images", "定焦镜头.png"),
    "light": os.path.join(SKILL_DIR, "assets", "part_images", "环光.png"),
}


# ==================== 输入 ====================
def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_selection(cfg_dir, project_name):
    """按约定顺序查找 selection_result.json。"""
    cands = [
        os.path.join(cfg_dir, "selection_result.json"),
        os.path.join(cfg_dir, "output_贴片", "selection_result.json"),
        os.path.join(cfg_dir, "output", "selection_result.json"),
        os.path.join(cfg_dir, project_name, "selection_result.json"),
    ]
    return next((p for p in cands if os.path.exists(p)), cands[0])


def validate_chain(chain):
    """校验 precision_chain 格式。弱模型常写成 dict 或漏列，报错必须给正确示例。"""
    if not isinstance(chain, list) or not chain:
        raise SystemExit(
            "[config] precision_chain 必须是非空数组，每行三项：\n"
            '  "precision_chain": [["视觉测量重复性", 0.02, "亚像素边缘+圆拟合"], ...]')
    for i, row in enumerate(chain, 1):
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            raise SystemExit(
                f"[config] precision_chain 第 {i} 行必须是 "
                f"[误差源, 典型值mm, 说明] 三项，当前是 {row!r}")
        try:
            float(row[1])
        except (TypeError, ValueError):
            raise SystemExit(
                f"[config] precision_chain 第 {i} 行典型值不是数字: {row[1]!r}")


def build_ctx(cfg, sel):
    info = sel.get("project_info") or {}
    hw = sel.get("hardware_selection") or {}
    cam = hw.get("camera") or {}
    lens = hw.get("lens") or {}
    light = hw.get("light_source") or {}

    scene = dict(DEFAULT_SCENE)
    scene.update(cfg.get("scene") or {})
    unknown = set(cfg.get("scene") or {}) - set(DEFAULT_SCENE)
    if unknown:
        print(f"[提示] config.scene 里有未知键 {sorted(unknown)}，将被忽略；"
              f"可用键：{sorted(DEFAULT_SCENE)}")

    cam_w = (cam.get("resolution") or {}).get("width", 0)
    cam_h = (cam.get("resolution") or {}).get("height", 0)
    cam_px = cam.get("pixel_size", 0)
    lens_f = lens.get("focal_length", "")
    lens_mag = lens.get("magnification_at_wd") or lens.get("magnification", 0) or 0
    lens_wd = lens.get("wd_requirement") or lens.get("working_distance", 0) or 0
    light_wd = light.get("working_distance", 0) or 0
    pixel_mm = cam_px / 1000.0 / lens_mag if lens_mag else 0

    budget = info.get("precision_budget") or {}
    tol = info.get("tolerance")
    prec = info.get("precision_requirement")
    px_max = info.get("pixel_precision_max_mm") or 0
    req_px = (info.get("required_pixels") or {}).get("x") or 0

    # 精度口径短式（版面用）+ 完整推导（备注用）
    if budget.get("mode") == "system_budget":
        band = budget["tolerance_band_mm"]
        tol_txt = (f"±{band / 2:g}mm→带宽{band:g}mm"
                   if budget.get("tolerance_type") == "bilateral"
                   else f"公差{band:g}mm")
        prec_basis = (f"{tol_txt}×{budget['allocation_ratio']:.0%}"
                      f"={budget['allowed_error_mm'] * 1000:.0f}μm"
                      f"÷{budget['pixel_factor']:g}={px_max * 1000:.1f}μm/px")
    elif budget.get("mode") == "direct_measurement":
        prec_basis = (f"公差带{budget['tolerance_band_mm']:g}mm"
                      f"÷{budget['direct_factor']:g}={px_max * 1000:.1f}μm/px")
    elif budget.get("basis_text"):
        prec_basis = budget["basis_text"]
    else:
        prec_basis = (f"测量精度 {prec:g}mm ÷ 3 = {px_max * 1000:.1f}μm/px"
                      if prec is not None else "精度口径待确认")
    prec_basis_full = budget.get("basis_text") or prec_basis

    if tol is not None:
        tol_txt = (f"±{tol} mm" if budget.get("tolerance_type") == "bilateral"
                   else f"≤ {tol} mm")
    elif prec is not None:
        tol_txt = f"测量精度 {prec:g} mm"
    else:
        tol_txt = "精度口径待确认"
    # 规格口径（偏差/验收行）：只写限值，不写"测量精度"前缀
    if tol is not None:
        spec_txt = (f"±{tol} mm" if budget.get("tolerance_type") == "bilateral"
                    else f"≤ {tol} mm")
    elif prec is not None:
        spec_txt = f"≤ {prec:g} mm"
    else:
        spec_txt = "精度口径待确认"
    req_value_txt = spec_txt.replace("≤ ", "").replace("±", "")

    fov_margin = info.get("fov_margin") or cfg.get("fov_margin") or 1.2
    fov = info.get("field_of_view") or {}
    cycle = info.get("cycle_time") or cfg.get("cycle_time") or 1
    fov_w = fov.get("width", 0) or 0
    fov_h = fov.get("height", 0) or 0
    real_fov_w = cam_w * cam_px / 1000 / lens_mag if lens_mag else 0
    real_fov_h = cam_h * cam_px / 1000 / lens_mag if lens_mag else 0

    return {
        "info": info, "cam": cam, "lens": lens, "light": light,
        "scene": scene,
        "cam_brand": cam.get("brand", ""), "cam_model": cam.get("model", ""),
        "cam_w": cam_w, "cam_h": cam_h, "cam_px": cam_px,
        "cam_wan": round(cam_w * cam_h / 1e4, -1) if cam_w and cam_h else 0,
        "lens_brand": lens.get("brand", ""), "lens_model": lens.get("model", ""),
        "lens_f": lens_f, "lens_mag": lens_mag, "lens_wd": lens_wd,
        "light_brand": light.get("brand", ""), "light_model": light.get("model", ""),
        "light_angle": light.get("light_angle", ""), "light_wd": light_wd,
        "pixel_mm": pixel_mm, "px_max": px_max, "req_px": req_px,
        "tol_txt": tol_txt, "spec_txt": spec_txt, "req_value_txt": req_value_txt,
        "prec_basis": prec_basis,
        "prec_basis_full": prec_basis_full, "budget": budget,
        "fov_margin": fov_margin, "fov_w": fov_w, "fov_h": fov_h,
        "real_fov_w": real_fov_w, "real_fov_h": real_fov_h,
        "cycle": cycle,
    }


# ==================== 页面 ====================
def build_deck(cfg, sel, ctx, opts):
    deck = Deck(opts["template"])
    prs = deck.prs
    company = opts["company"]

    def new_slide(key=None):
        if not key:
            return deck.new_slide(None)
        title = PAGE_TITLES.get(key) or page_title(SECTION_TEXT, key)
        return deck.new_slide(title)

    def pic_fit(s, path, x, y, w, h, border=False):
        """等比缩放居中放置图片（Deck.picture 不做比例计算）。"""
        iw, ih = Image.open(path).size
        ratio = iw / ih
        if w / h > ratio:
            nh, nw = h, h * ratio
        else:
            nw, nh = w, w / ratio
        pic = deck.picture(s, path, x + (w - nw) / 2, y + (h - nh) / 2, nw, nh)
        if border:
            pic.line.color.rgb = GRAY_L
            pic.line.width = 0.75
        return pic

    # 先把母版硬件页摘出来（保留原页做替换，避免重建丢模板元素）
    hw_index = opts["hardware_page"]
    if hw_index >= len(prs.slides):
        raise SystemExit(f"[输入] 母版只有 {len(prs.slides)} 页，"
                         f"--hardware-page {hw_index} 越界")
    hw_slide = prs.slides[hw_index]
    tpl_count = len(prs.slides)          # 新建页之前的母版页数

    # ---------- 1 封面 ----------
    s = new_slide()
    deck.cover(
        s,
        cfg.get("project_name") or sel.get("project_info", {}).get("name")
        or "视觉引导贴片系统方案",
        ctx["scene"]["subtitle"],
        f"{ctx['tol_txt']}　|　节拍 {ctx['cycle']:g} s/件"
        f"　|　工作距离 {ctx['lens_wd']:.0f} mm",
        company,
        date.today().isoformat()[:7].replace("-", "."),
    )

    # ---------- 2 目录 ----------
    s = new_slide()
    deck.toc(s, toc_items(SECTION_TEXT))

    # ---------- 3 项目需求 ----------
    s = new_slide("requirements")
    # 左：工件俯视示意
    deck.box(s, 0.75, 1.35, 5.55, 3.35, fill=BLUE_LL, line=GRAY_L, line_w=0.75,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.04)
    deck.box(s, 1.15, 1.85, 4.75, 2.35, fill=RGBColor(0xBF, 0xBF, 0xBF),
             line=GRAY, line_w=1.0)
    for cx, cy, cover in [(2.05, 2.55, False), (3.55, 3.45, True), (4.95, 2.55, False)]:
        d = 0.62
        deck.box(s, cx - d / 2, cy - d / 2, d, d, fill=RGBColor(0x40, 0x40, 0x40),
                 line=GRAY, shape=MSO_SHAPE.OVAL)
        deck.box(s, cx - d / 2 + 0.06, cy - d / 2 + 0.06, d - 0.12, d - 0.12,
                 fill=RGBColor(0x20, 0x20, 0x20), line=None, shape=MSO_SHAPE.OVAL)
        if cover:
            cd = 0.84
            deck.box(s, cx - cd / 2, cy - cd / 2, cd, cd,
                     fill=RGBColor(0xF4, 0xB1, 0x83), line=RED, line_w=1.25,
                     shape=MSO_SHAPE.OVAL)
            deck.text(s, cx - 0.75, cy - 0.62, 1.5, 0.3,
                      [{"text": ctx["scene"]["target_label"], "size": 12,
                        "bold": True, "color": RED}],
                      align=PP_ALIGN.CENTER)
    deck.text(s, 1.15, 4.30, 4.75, 0.3,
              [{"text": f"工件俯视示意：{ctx['scene']['target_label']}覆盖孔口，将孔封住",
                "size": 12, "color": GRAY}],
              align=PP_ALIGN.CENTER)

    # 右：客户需求
    deck.section_label(s, 6.75, 1.25, "客户需求", w=6.0, size=18)
    reqs = [
        ("工件特征", ctx["scene"]["part_feature"]),
        (ctx["scene"]["accuracy_label"],
         f"{ctx['scene']['accuracy_item']} {ctx['spec_txt']}"),        ("工作距离", f"相机到工件约 {ctx['lens_wd']:.0f} mm（可按机构需要调整）"),
        ("定位方式", "PLC 控制伺服运动到固定点位，每个点位拍照一次"),
        ("单点视野", f"约 {ctx['real_fov_w']:.0f} × {ctx['real_fov_h']:.0f} mm"
                     "（覆盖圆孔并留定位余量）"),
        ("节拍", f"{ctx['cycle']:g} s/件：PLC 运动到位 → 拍照 → 贴片全流程"),
    ]
    for i, (k, v) in enumerate(reqs):
        yy = 1.78 + i * 0.62
        deck.box(s, 6.75, yy + 0.09, 0.12, 0.12, fill=BLUE)
        deck.text(s, 7.0, yy, 1.15, 0.4,
                  [{"text": k, "size": 14, "bold": True, "color": BLUE_D}])
        deck.text(s, 8.15, yy, 4.55, 0.52,
                  [{"text": v, "size": 14, "color": BLACK}], line_spacing=1.0)
    deck.text(s, 6.75, 5.38, 5.95, 0.26,
              [{"text": f"注：视觉测量精度按客户给定口径计；"
                        f"{ctx['scene']['accuracy_label']}由定位、机构与标定共同保证。",
                "size": 9.5, "color": GRAY}], line_spacing=1.0)
    deck.callout(s, 6.75, 5.72, 5.95, 0.75, "核心目标：" + ctx["scene"]["core_goal"],
                 kind="warn", size=13)

    # ---------- 4 系统方案 ----------
    s = new_slide("system")
    # 实体坐标变量化：尺寸标注只准引用 shape，禁止手写坐标
    CAM_BOX_X, CAM_BOX_Y, CAM_BOX_W, CAM_BOX_H = 2.25, 1.40, 1.05, 0.62
    LENS_BOX_X, LENS_BOX_Y, LENS_BOX_W, LENS_BOX_H = 2.55, 2.02, 0.45, 0.55
    LIGHT_BOX_X, LIGHT_BOX_Y, LIGHT_BOX_W, LIGHT_BOX_H = 1.85, 2.74, 1.85, 0.28
    WORK_BOX_X, WORK_BOX_Y, WORK_BOX_W, WORK_BOX_H = 1.55, 4.55, 2.45, 0.28
    PLAT_BOX_Y = 4.83

    deck.box(s, 0.65, 1.15, 5.95, 5.25, fill=WHITE, line=GRAY_L, line_w=0.75)
    deck.box(s, CAM_BOX_X, CAM_BOX_Y, CAM_BOX_W, CAM_BOX_H,
             fill=RGBColor(0xFF, 0xC0, 0x00), line=GRAY, line_w=0.75)
    lens_box = deck.box(s, LENS_BOX_X, LENS_BOX_Y, LENS_BOX_W, LENS_BOX_H,
                        fill=RGBColor(0x1A, 0x1A, 0x1A), line=None)
    light_box = deck.box(s, LIGHT_BOX_X, LIGHT_BOX_Y, LIGHT_BOX_W, LIGHT_BOX_H,
                         fill=RGBColor(0xB0, 0xB0, 0xB0), line=GRAY, line_w=0.75)
    deck.box(s, LIGHT_BOX_X + (LIGHT_BOX_W - 0.45) / 2, LIGHT_BOX_Y + 0.04,
             0.45, 0.20, fill=WHITE, line=None)
    work_box = deck.box(s, WORK_BOX_X, WORK_BOX_Y, WORK_BOX_W, WORK_BOX_H,
                        fill=RGBColor(0x2E, 0x75, 0xB6), line=None)
    deck.box(s, 2.55, WORK_BOX_Y, 0.45, WORK_BOX_H, fill=WHITE, line=GRAY,
             line_w=0.5, shape=MSO_SHAPE.OVAL)
    deck.box(s, 1.30, PLAT_BOX_Y, 2.95, 0.22, fill=RGBColor(0x8C, 0x8C, 0x8C),
             line=None)
    deck.text(s, 1.25, 5.12, 3.1, 0.3,
              [{"text": "XY 伺服平台 / 工件", "size": 11, "color": GRAY}],
              align=PP_ALIGN.CENTER)
    deck.box(s, 4.95, 3.55, 0.42, 1.35, fill=RGBColor(0x40, 0x40, 0x40), line=None)
    deck.box(s, 4.55, 2.95, 1.55, 0.26, fill=RGBColor(0x40, 0x40, 0x40), line=None)
    deck.box(s, 4.60, 3.18, 0.28, 0.42, fill=RGBColor(0x40, 0x40, 0x40), line=None)
    deck.text(s, 4.45, 2.55, 1.75, 0.3,
              [{"text": "机器人 / 贴片头", "size": 11, "color": GRAY}],
              align=PP_ALIGN.CENTER)
    deck.text(s, 3.45, 1.48, 0.9, 0.3,
              [{"text": "相机", "size": 12, "bold": True, "color": BLACK}])
    deck.line(s, 3.35, 1.62, 3.05, 1.62, color=GRAY, width=0.75, arrow=True)
    deck.text(s, 3.15, 2.02, 1.35, 0.3,
              [{"text": f"{ctx['lens_f']}mm 镜头", "size": 12, "bold": True, "color": BLACK}])
    deck.line(s, 3.05, 2.17, 3.00, 2.17, color=GRAY, width=0.75, arrow=True)
    deck.text(s, 3.85, 2.70, 0.9, 0.3,
              [{"text": "环形光", "size": 12, "bold": True, "color": BLACK}])
    deck.line(s, 3.75, 2.88, 3.68, 2.88, color=GRAY, width=0.75, arrow=True)
    deck.text(s, 1.05, 4.12, 0.55, 0.3,
              [{"text": "工件", "size": 12, "bold": True, "color": BLACK}])
    deck.line(s, 1.32, 4.28, 1.60, 4.52, color=GRAY, width=0.75, arrow=True)
    # 工作距离 = 光学件前端面 → 检测面（相机机身高度不计入）
    add_wd_dim(s, 0.80, f"{ctx['lens_wd']:.0f}mm", lens_box, work_box, color=GRAY)
    add_wd_dim(s, 1.30, f"{ctx['light_wd']:.0f}mm", light_box, work_box,
               text_side="right", color=GRAY)
    issues = self_check(s)
    if issues:
        raise SystemExit("尺寸标注自检失败: " + "; ".join(issues))

    # 右：系统组成
    deck.section_label(s, 6.95, 1.20, "系统组成", w=5.8, size=18)
    comp = [
        ("视觉单元", f"{ctx['cam_wan']:.0f} 万黑白相机 + {ctx['lens_f']}mm 微距镜头"
                     " + 环形光 + 光源控制器 + 工控机"),
        ("运动单元", "PLC + XY 伺服平台（点位运动）+ 机器人 / 贴片头"),
        ("通讯单元", "PLC→视觉 IO 硬触发；视觉→机器人 TCP/IP；"
                     "视觉→PLC 结果 IO / Modbus TCP"),
        ("机构前提", "相机固定于工位上方；光源独立支架；"
                     "贴片头与相机光路错位或让位，避免遮挡"),
    ]
    for i, (k, v) in enumerate(comp):
        yy = 1.78 + i * 1.02
        deck.box(s, 6.95, yy + 0.06, 0.10, 0.72, fill=BLUE)
        deck.text(s, 7.20, yy, 1.05, 0.35,
                  [{"text": k, "size": 14, "bold": True, "color": BLUE_D}])
        deck.text(s, 8.25, yy, 4.45, 0.9,
                  [{"text": v, "size": 13, "color": BLACK}], line_spacing=1.05)
    deck.callout(s, 6.95, 5.95, 5.75, 0.55,
                 f"{ctx['cycle']:g} s 节拍：伺服到位 → 硬触发拍照 → 圆心定位 → "
                 "坐标转换 → 机器人贴片（拍照时工件不动）",
                 kind="info", size=10.5)

    # ---------- 5 工作流程 ----------
    s = new_slide("workflow")
    steps = [
        ("01", "伺服定位", "PLC 控制 XY 伺服\n把工件移动到\n设定的拍照点位", "≤300 ms"),
        ("02", "触发拍照", "PLC 输出 IO 硬触发\n相机曝光 ≤5 ms\n工件静止成像", "≤80 ms"),
        ("03", "圆心定位", "ROI 提取 + 亚像素\n边缘检测 + 圆拟合\n输出圆心 (u, v)", "≤100 ms"),
        ("04", "坐标转换", "像素坐标 →\n机器人坐标\n（手眼标定矩阵）", "≤20 ms"),
        ("05", "机器人贴片", "贴片中心对准孔心\n下压覆盖孔口\n完成封孔", "≤400 ms"),
    ]
    deck.step_cards(s, 1.45, steps, card_h=2.85, desc_size=11.5)
    deck.text(s, 0.55, 4.55, 12.25, 0.3,
              [{"text": "注：机器人与伺服动作时间为典型估算，最终以现场设备实测节拍为准；"
                        "视觉处理按 ROI 局部图像计算。",
                "size": 9.5, "color": GRAY}])

    # ---------- 7 选型计算 ----------
    s = new_slide("special_a")
    deck.section_label(s, 0.70, 1.05, "计算过程", w=5.85, size=18)
    req_px = ctx["req_px"]
    ratio_px = ctx["cam_w"] / req_px if req_px else 0
    calc = [
        ("① 精度换算", ctx["prec_basis"]),
        ("② 视野确定",
         f"单点位检测区域 {ctx['fov_w'] / ctx['fov_margin']:.0f}×"
         f"{ctx['fov_h'] / ctx['fov_margin']:.0f} mm × 余量 {ctx['fov_margin']:g} = "
         f"视野 {ctx['fov_w']:g}×{ctx['fov_h']:g} mm"),
        ("③ 所需像素",
         f"{ctx['fov_w']:g} ÷ {ctx['px_max']:.5f} = {req_px} px，"
         f"{ctx['cam_w']} px 满足（像素数 {ratio_px:.1f} 倍）"),
        ("④ 镜头匹配",
         f"{ctx['lens_wd']:.0f} mm 配 {ctx['lens_f']} mm 镜头，"
         f"β≈{ctx['lens_mag']:.3f}x，视野 "
         f"{ctx['real_fov_w']:.1f}×{ctx['real_fov_h']:.1f} mm"),
        ("⑤ 实际精度",
         f"{ctx['cam_px']} ÷ {ctx['lens_mag']:.3f} = {ctx['pixel_mm'] * 1000:.1f} μm/px，"
         f"上限 {ctx['px_max'] * 1000:.1f} μm，"
         f"余量 {ctx['px_max'] / ctx['pixel_mm']:.1f} 倍"),
    ]
    for i, (k, v) in enumerate(calc):
        yy = 1.55 + i * 0.92
        deck.box(s, 0.70, yy, 1.28, 0.62, fill=BLUE_L, line=None)
        deck.text(s, 0.74, yy + 0.14, 1.2, 0.35,
                  [{"text": k, "size": 11, "bold": True, "color": BLUE_D}],
                  align=PP_ALIGN.CENTER)
        deck.text(s, 2.12, yy + 0.02, 4.45, 0.78,
                  [{"text": v, "size": 11.5, "color": BLACK}], line_spacing=1.05)

    rows = [
        ("相机", f"{ctx['cam_brand']} {ctx['cam_model']}"),
        ("分辨率", f"{ctx['cam_w']} × {ctx['cam_h']}（{ctx['cam_wan']:.0f} 万）"),
        ("像元 / 靶面", f"{ctx['cam_px']} μm / {ctx['cam'].get('sensor_size', '2/3\"')}"),
        ("镜头", f"{ctx['lens_model']}（{ctx['lens_f']} mm，{ctx['lens_mag']:.3f}x）"),
        ("工作距离", f"{ctx['lens_wd']:.0f} mm"),
        ("实际视野", f"{ctx['real_fov_w']:.1f} × {ctx['real_fov_h']:.1f} mm"),
        ("像素当量", f"{ctx['pixel_mm']:.4f} mm/pixel"),
        ("光源", f"{ctx['light_brand']} {ctx['light_model']}"
                 f"（{ctx['light_angle']}° 环形光）"),
        ("节拍匹配", f"视觉 ≤200 ms，全流程 {ctx['cycle']:g} s"),
    ]
    tx, ty, tw, row_h = 6.75, 1.10, 5.95, 0.50
    tbl_shape = s.shapes.add_table(len(rows), 2, Inches(tx), Inches(ty),
                                   Inches(tw), Inches(row_h * len(rows)))
    tbl = tbl_shape.table
    tbl.columns[0].width = Inches(1.55)
    tbl.columns[1].width = Inches(tw - 1.55)
    for ri, (k, v) in enumerate(rows):
        tbl.rows[ri].height = Inches(row_h)
        for ci, text in enumerate((k, v)):
            cell = tbl.cell(ri, ci)
            cell.text = ""
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = Inches(0.10)
            cell.margin_right = Inches(0.06)
            cell.fill.solid()
            cell.fill.fore_color.rgb = BLUE_D if ci == 0 else (
                BLUE_LL if ri % 2 == 0 else BLUE_L)
            p = cell.text_frame.paragraphs[0]
            r = p.add_run()
            r.text = text
            deck.set_run(r, 12.5, ci == 0, WHITE if ci == 0 else BLACK)
            p.alignment = PP_ALIGN.LEFT
    deck.text(s, 6.75, 5.85, 5.95, 0.7,
              [{"text": f"注：镜头 WD 250~550 mm 可调，{ctx['lens_wd']:.0f} mm 为设计工作点；"
                        f"光源安装高度约 {ctx['light_wd']:.0f} mm；像素需求仅 {req_px} px，"
                        f"选 {ctx['cam_wan']:.0f} 万像素是为孔边缘多像素覆盖与 "
                        f"{ctx['cycle']:g} s 节拍下的短曝光余量。",
                "size": 10, "color": GRAY}], line_spacing=1.05)
    # 精度口径完整推导放备注（版面放不下长句）
    s.notes_slide.notes_text_frame.text = (
        f"精度口径（{ctx['budget'].get('mode_label', '未声明')}）：{ctx['prec_basis_full']}\n"
        + "".join(f"· {a}\n" for a in (ctx["budget"].get("assumptions") or []))
        + f"结论：像素当量上限 {ctx['px_max'] * 1000:.1f} μm/px，"
          f"实际 {ctx['pixel_mm'] * 1000:.2f} μm/px，"
          f"余量 {ctx['px_max'] / ctx['pixel_mm'] if ctx['pixel_mm'] else 0:.2f}x。")

    # ---------- 8 视觉算法 ----------
    s = new_slide("special_b")
    algo = ["图像采集", "ROI / 预处理", "亚像素边缘", "圆拟合", "坐标转换", "输出贴片位"]
    x0, gap, cw = 0.55, 0.24, 1.92
    for i, name in enumerate(algo):
        x = x0 + i * (cw + gap)
        deck.box(s, x, 1.12, cw, 0.62, fill=BLUE, line=None,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.18)
        deck.text(s, x, 1.25, cw, 0.35,
                  [{"text": name, "size": 12.5, "bold": True, "color": WHITE}],
                  align=PP_ALIGN.CENTER)
        if i < len(algo) - 1:
            ax = x + cw + 0.02
            deck.line(s, ax, 1.43, ax + 0.20, 1.43, color=BLUE, width=1.75,
                      arrow=True)
    # 圆孔图像示意
    deck.box(s, 0.65, 2.20, 4.15, 3.55, fill=RGBColor(0xF2, 0xF2, 0xF2),
             line=GRAY_L, line_w=0.75)
    deck.box(s, 1.38, 2.75, 2.70, 2.55, fill=None,
             line=RGBColor(0x00, 0xB0, 0x50), line_w=1.0)
    deck.text(s, 1.45, 2.55, 2.5, 0.25,
              [{"text": "ROI", "size": 10, "bold": True,
                "color": RGBColor(0x00, 0x80, 0x40)}])
    cx, cy, r = 2.73, 4.02, 0.78
    deck.box(s, cx - r, cy - r, 2 * r, 2 * r, fill=RGBColor(0x9A, 0x9A, 0x9A),
             line=None, shape=MSO_SHAPE.OVAL)
    deck.box(s, cx - r + 0.20, cy - r + 0.20, 2 * (r - 0.20), 2 * (r - 0.20),
             fill=RGBColor(0x26, 0x26, 0x26), line=None, shape=MSO_SHAPE.OVAL)
    deck.box(s, cx - 0.10, cy - 0.10, 0.20, 0.20, fill=RED, line=None,
             shape=MSO_SHAPE.OVAL)
    deck.line(s, cx - 1.15, cy, cx + 1.15, cy, color=RGBColor(0xFF, 0x33, 0x33),
              width=1.0)
    deck.line(s, cx, cy - 1.15, cx, cy + 1.15, color=RGBColor(0xFF, 0x33, 0x33),
              width=1.0)
    deck.text(s, 2.55, 5.35, 2.4, 0.28,
              [{"text": "圆心 (u, v)", "size": 11, "bold": True, "color": RED}],
              align=PP_ALIGN.CENTER)
    # 右侧关键点
    deck.section_label(s, 5.15, 2.05, "圆心定位关键点", w=7.6, size=17)
    pts = [
        ("亚像素边缘", "沿径向卡尺找边，单圆有效边缘点 ≥360 个，"
                       "边缘定位精度优于 0.1 pixel。"),
        ("圆拟合", "最小二乘拟合 + RANSAC 剔除异常点，抑制毛刺、油污和局部反光的影响。"),
        ("重复性", f"静态连续 30 次测量，圆心标准差 ≤0.02 mm"
                   f"（按 {ctx['pixel_mm']:.4f} mm/pixel 估算）。"),
        ("标定", "棋盘格完成镜头畸变校正；九点法完成像素坐标→机器人坐标的手眼标定。"),
        ("异常处理", "孔缺失、遮挡、偏心超限 → 输出 NG 并报警，机器人不执行贴片。"),
    ]
    for i, (k, v) in enumerate(pts):
        yy = 2.55 + i * 0.72
        deck.box(s, 5.20, yy + 0.06, 0.10, 0.10, fill=BLUE)
        deck.text(s, 5.42, yy, 1.05, 0.35,
                  [{"text": k, "size": 12.5, "bold": True, "color": BLUE_D}])
        deck.text(s, 6.55, yy, 6.2, 0.65,
                  [{"text": v, "size": 11.5, "color": BLACK}], line_spacing=1.05)

    # ---------- 9 精度分析 ----------
    s = new_slide("special_c")
    deck.section_label(s, 0.75, 1.02,
                       "贴片偏差误差链（视觉闭环后，伺服定位误差被视觉测量吸收）",
                       w=8.0, size=14)
    chain = cfg.get("precision_chain") or DEFAULT_CHAIN
    validate_chain(chain)
    vis_vals = [float(row[1]) for row in chain[:3]]
    vis_rss = (sum(v * v for v in vis_vals) ** 0.5) if vis_vals else 0.0
    all_rss = (sum(float(row[1]) ** 2 for row in chain) ** 0.5) if chain else 0.0
    field_control = cfg.get("field_control_mm") or 0.2
    data = [["误差源", "典型值", "说明"]]
    data += [[row[0], f"±{row[1]:g} mm", row[2]] for row in chain]
    data.append(["合成误差（RSS）", f"≈ ±{all_rss:.2f} mm", "均方根合成，含执行链"])
    tx, ty, tw = 0.75, 1.52, 11.85
    row_h = [0.50] + [0.52] * len(chain) + [0.55]
    tbl_shape = s.shapes.add_table(len(data), 3, Inches(tx), Inches(ty),
                                   Inches(tw), Inches(sum(row_h)))
    tbl = tbl_shape.table
    tbl.columns[0].width = Inches(3.35)
    tbl.columns[1].width = Inches(2.25)
    tbl.columns[2].width = Inches(tw - 5.60)
    for ri, row in enumerate(data):
        tbl.rows[ri].height = Inches(row_h[ri])
        for ci, text in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.text = ""
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = Inches(0.12)
            cell.fill.solid()
            if ri == 0:
                cell.fill.fore_color.rgb = BLUE_D
            elif ri == len(data) - 1:
                cell.fill.fore_color.rgb = RGBColor(0xFD, 0xEC, 0xEC)
            else:
                cell.fill.fore_color.rgb = WHITE if ri % 2 == 1 else BLUE_LL
            p = cell.text_frame.paragraphs[0]
            r = p.add_run()
            r.text = text
            if ri == 0:
                deck.set_run(r, 13, True, WHITE)
            elif ri == len(data) - 1:
                deck.set_run(r, 13, True, RED)
            else:
                deck.set_run(r, 12.5, ci == 0, BLACK)
            p.alignment = PP_ALIGN.CENTER if ci == 1 else PP_ALIGN.LEFT
    allow_um = (ctx["budget"].get("allowed_error_mm") or 0) * 1000
    if allow_um > 0 and vis_rss > 0:
        p9_note = (f"视觉测量链（圆心+畸变+手眼）RSS ≈ ±{vis_rss:.3f} mm，"
                   f"在允许误差 {allow_um:.0f} μm 内"
                   f"（余量 {allow_um / (vis_rss * 1000):.1f}x）；"
                   "机器人重复定位与吸嘴偏差属执行链，由整机公差剩余份额覆盖。")
    else:
        p9_note = "注：机器人重复定位、吸嘴偏差为常规设备典型值，最终以现场标定与实测为准。"
    margin = (ctx["budget"].get("allowed_error_mm") or 0) / field_control \
        if field_control else 0
    deck.callout(s, 0.75, 5.55, 11.85, 0.82,
                 f"结论：理论合成误差约 ±{all_rss:.2f} mm，"
                 f"按现场工况控制在 ≤{field_control:g} mm，"
                 f"相对 {ctx['req_value_txt']} 要求"
                 f"仍有 ≥{margin:.1f} 倍余量。",
                 kind="warn", size=13.5)
    deck.text(s, 0.75, 6.48, 11.85, 0.25,
              [{"text": p9_note if p9_note.startswith("注：") else f"注：{p9_note}",
                "size": 9.5, "color": GRAY}])

    # ---------- 10 系统架构 ----------
    s = new_slide("architecture")
    deck.text(s, 0.90, 1.55, 11.53, 0.45,
              [{"text": "系统采用分层架构，从成像到贴片执行形成闭环，"
                        "视觉只负责测量，动作由 PLC 与机器人完成。",
                "size": 14, "color": GRAY}], align=PP_ALIGN.CENTER)
    deck.arch_row(s, 2.75, [
        ("感知层", "成像采集",
         f"{ctx['cam_wan']:.0f} 万相机 + {ctx['lens_f']}mm 镜头 + 环形光，"
         "PLC 硬触发单帧采集。"),
        ("处理层", "圆心定位",
         "ROI 提取、亚像素边缘、圆拟合，输出孔心像素坐标。"),
        ("决策层", "坐标转换",
         "畸变校正 + 手眼矩阵，换算为机器人坐标并判定 OK/NG。"),
        ("执行层", "贴片执行",
         "PLC 控制伺服点位，机器人 / 贴片头完成对准与下压。"),
    ], h=2.10)
    deck.callout(s, 0.62, 5.65, 12.10, 0.75,
                 "全链路可追溯：图像、圆心坐标、判定结果与节拍写入日志，"
                 "支持按时间段与孔位查询。", kind="info", bold=False)

    # ---------- 11 实施与验收 ----------
    s = new_slide("delivery")
    cols = [
        ("实施步骤", ["需求与孔位表确认", "相机 / 镜头 / 光源采购", "支架与光源机构安装",
                      "镜头畸变 + 手眼标定", "PLC / 机器人通讯联调", "试产与节拍验证"]),
        ("标定内容", ["镜头畸变标定（棋盘格）", "手眼九点标定", "吸嘴中心标定",
                      "光源亮度与曝光整定", "孔位坐标表复核", "NG 判定阈值确认"]),
        ("验收标准", [f"连续 30 件{ctx['scene']['target_label']}验证",
                      f"{ctx['scene']['acceptance_item']} {ctx['spec_txt']}",
                      f"节拍 ≤ {ctx['cycle']:g} s/件（全流程）", "NG 点位 100% 报警",
                      "标定报告 / 操作说明", "通讯协议与点位表交付"]),
    ]
    deck.col_cards(s, 1.25, cols, h=4.50, item_size=12, space_after=27)
    deck.box(s, 0.55, 5.95, 12.25, 0.55, fill=WHITE, line=BLUE_L, line_w=0.75)
    deck.text(s, 0.75, 6.04, 11.9, 0.4,
              [{"text": "周期预估：硬件采购约 2 周 + 机构安装 2~3 天 + "
                        "标定联调 3~5 天 + 试产验证 3 天（以现场条件为准）。",
                "size": 10.5, "color": GRAY}], line_spacing=1.0)

    # ---------- 12 谢谢 ----------
    s = new_slide()
    deck.thanks(s, company)

    # ============ 硬件页替换（母版原页） ============
    _fill_hardware_page(deck, hw_slide, ctx, pic_fit)

    # ============ 删除母版其余页并重排 ============
    # 新建页顺序：cover, toc, req, system, workflow, special_a, special_b,
    #             special_c, architecture, delivery, thanks
    # 只删母版原有页（新建页索引在 tpl_count 之后，必须保留）
    for i in sorted([i for i in range(tpl_count) if i != hw_index], reverse=True):
        deck.kill_slide(prs, i)
    xml_lst = list(prs.slides._sldIdLst)
    hw_id = xml_lst[0]                      # 只剩硬件页 + 11 个新建页
    new_ids = xml_lst[1:]
    order = new_ids[:5] + [hw_id] + new_ids[5:]
    for el in list(prs.slides._sldIdLst):
        prs.slides._sldIdLst.remove(el)
    for el in order:
        prs.slides._sldIdLst.append(el)

    if len(prs.slides) != len(STANDARD_PAGES):
        raise SystemExit(f"[自检] 页数 {len(prs.slides)} 与标准骨架 "
                         f"{len(STANDARD_PAGES)} 不一致")

    deck.finalize(company, first_page_no=1, footer_from=2)
    return deck


# ==================== 母版硬件页替换（2D 特有机制） ====================
def _fill_hardware_page(deck, s, ctx, pic_fit):
    """把母版第 4 页的型号/参数/图片替换成本项目选型结果。

    模板契约：视觉检测方案.pptx 第 4 页的 shape 名与文案（同轴光/远心镜头/
    228±4mm/80mm 等）是母版固定内容，只做值替换，不重建页面。
    """
    for sh in s.shapes:
        if sh.has_text_frame:
            txt = sh.text_frame.text.strip()
            if txt == "同轴光":
                sh.text_frame.text = "环形光"
                for p in sh.text_frame.paragraphs:
                    deck.set_run(p.runs[0], 14, False, BLACK)
            elif txt == "远心镜头":
                sh.text_frame.text = "微距镜头"
                for p in sh.text_frame.paragraphs:
                    deck.set_run(p.runs[0], 14, False, BLACK)
            elif txt == "228±4mm":
                sh.text_frame.text = f"{ctx['lens_wd']:.0f}mm"
                for p in sh.text_frame.paragraphs:
                    deck.set_run(p.runs[0], 14, False, BLACK)
            elif txt == "80mm":
                sh.text_frame.text = f"{ctx['light_wd']:.0f}mm"
                for p in sh.text_frame.paragraphs:
                    deck.set_run(p.runs[0], 13, False, BLACK)
                sh.text_frame.word_wrap = False
                sh.width = Inches(1.05)
            elif sh.name == "文本框 23":
                sh.text_frame.text = ""
                p = sh.text_frame.paragraphs[0]
                r = p.add_run()
                r.text = (f"使用 {ctx['cam_wan']:.0f} 万像素黑白相机"
                          f"（{ctx['cam_brand']} {ctx['cam_model']}），"
                          f"分辨率为 {ctx['cam_w']} × {ctx['cam_h']}，"
                          f"像元尺寸 {ctx['cam_px']} μm，"
                          f"像素当量为 {ctx['pixel_mm']:.4f} mm/pixel")
                deck.set_run(r, 14, False, BLACK)
            elif sh.name == "文本框 29":
                sh.text_frame.text = ""
                p = sh.text_frame.paragraphs[0]
                r = p.add_run()
                r.text = (f"镜头：{ctx['lens_model']} / {ctx['lens_f']}mm / "
                          f"{ctx['lens_mag']:.3f}x / WD {ctx['lens_wd']:.0f}mm")
                deck.set_run(r, 13, False, BLACK)
                sh.width = Inches(5.0)
                sh.text_frame.word_wrap = False
            elif sh.name == "文本框 30":
                sh.text_frame.text = ""
                p = sh.text_frame.paragraphs[0]
                r = p.add_run()
                r.text = (f"环形光：{ctx['light_brand']} {ctx['light_model']}"
                          f"（{ctx['light_angle']}°）")
                deck.set_run(r, 13, False, BLACK)
                sh.width = Inches(3.5)

        if sh.has_table:
            tbl = sh.table
            vals = [
                ["相机工作距离", f"{ctx['lens_wd']:.0f}mm"],
                ["相机视野", f"{ctx['real_fov_w']:.1f}mm×{ctx['real_fov_h']:.1f}mm"],
                ["像素当量", f"{ctx['pixel_mm'] * 1000:.2f}μm/pixel"],
                ["光源工作距离", f"{ctx['light_wd']:.0f}mm"],
            ]
            tbl.columns[0].width = Inches(1.85)
            tbl.columns[1].width = Inches(2.45)
            for ri, row in enumerate(vals):
                tbl.rows[ri].height = Inches(0.38)
                for ci, val in enumerate(row):
                    cell = tbl.cell(ri, ci)
                    cell.text = ""
                    p = cell.text_frame.paragraphs[0]
                    r = p.add_run()
                    r.text = val
                    deck.set_run(r, 13, ci == 0, BLUE_D if ci == 0 else BLACK)
            sh.top = Inches(5.28)
            sh.width = Inches(4.30)

    # 产品图片替换（找不到对应图则保留模板原图，不报错）
    for sh in list(s.shapes):
        if sh.shape_type != 13 or sh.name not in HW_PIC_SLOTS:
            continue
        kind, override = HW_PIC_SLOTS[sh.name]
        if kind == "camera":
            img_rel = ctx["cam"].get("image_path")
            path = os.path.join(SKILL_DIR, img_rel) if img_rel else None
        else:
            path = HW_FIXED_PICS.get(kind)
        if not path or not os.path.exists(path):
            continue
        if override:
            x, y, w, h = override
        else:
            x, y, w, h = (Emu(sh.left).inches, Emu(sh.top).inches,
                          Emu(sh.width).inches, Emu(sh.height).inches)
        sh._element.getparent().remove(sh._element)
        pic_fit(s, path, x, y, w, h)


# ==================== CLI ====================
def auto_select(cfg_path, cfg_dir):
    """selection 缺失时自动补：调 vision_proposal_generator --auto --dry-run。

    只选型不生成 PPT，因此不会覆盖已交付的客户版。失败时把选型报告原样透出，
    由调用方决定停止——禁止在这里兜底填数字。
    """
    vpg = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "vision_proposal_generator.py")
    if not os.path.exists(vpg):
        return False
    print("[选型] 未找到 selection_result.json，自动调用选型（--auto --dry-run）……")
    r = subprocess.run([sys.executable, vpg, "--config", cfg_path,
                        "--auto", "--dry-run"], cwd=cfg_dir)
    return r.returncode == 0


def parse_args():
    ap = argparse.ArgumentParser(description="2D 视觉定位/贴片方案 PPT 生成器（客户版）")
    ap.add_argument("--config", help="project_config.json（可选）")
    ap.add_argument("--selection",
                    help="selection_result.json（默认在 config 同目录依次查找）")
    ap.add_argument("--template", help="母版 pptx（默认在工作区自动发现「视觉检测方案.pptx」）")
    ap.add_argument("--hardware-page", type=int, default=3,
                    help="母版硬件页的 0 基索引（默认 3，即第 4 页）")
    ap.add_argument("--company", default=DEFAULT_COMPANY, help="公司名")
    ap.add_argument("--out", help="输出 pptx（默认 <config目录>/<project_name>/<project_name>.pptx）")
    ap.add_argument("--no-auto-select", action="store_true",
                    help="selection 缺失时不自动补选型（仅排障）")
    ap.add_argument("--no-check", action="store_true", help="跳过机检（仅排障）")
    ap.add_argument("--no-preview", action="store_true", help="跳过逐页预览导出")
    return ap.parse_args()


def main():
    args = parse_args()
    if not args.config and not args.selection:
        raise SystemExit(
            "[输入] 需要 --config 指定项目配置（新项目先按 SKILL.md「新项目从0」建 config）：\n"
            '  python tools/two_d_ppt.py --config "<工作区>\\project_config.json"\n'
            "已有 selection 也可直接给 --selection。")

    cfg = {}
    cfg_dir = os.getcwd()
    if args.config:
        cfg_path = os.path.abspath(args.config)
        if not os.path.exists(cfg_path):
            raise SystemExit(f"[输入] config 不存在: {cfg_path}")
        cfg_dir = os.path.dirname(cfg_path)
        cfg = load_json(cfg_path)
        if cfg.get("installation") or cfg.get("calibration_error_mm"):
            raise SystemExit(
                "[输入] 这是 3D 配置（含 installation / 误差预算字段），"
                "不是 2D 配置。\n"
                '3D 请用：python "<skill>\\tools\\three_d_ppt.py" '
                '--config "<工作区>\\project_config_3d.json"')

    project_name = (cfg.get("project_name")
                    or "视觉引导贴片系统方案")
    sel_path = args.selection or find_selection(cfg_dir, project_name)
    if not os.path.exists(sel_path) and args.config and not args.no_auto_select:
        auto_select(cfg_path, cfg_dir)
        sel_path = find_selection(cfg_dir, project_name)
    if not os.path.exists(sel_path):
        raise SystemExit(
            f"[输入] selection 不存在: {sel_path}\n"
            "两条路任选：\n"
            "  1) 直接重跑本命令（会自动补选型；需 config 存在）\n"
            "  2) 先手动跑 vision_proposal_generator.py --config <config> --auto --dry-run\n"
            "选型报口径问题（exit 2）时，把脚本原话转问用户，不要自己填数字。")
    sel = load_json(sel_path)
    project_name = cfg.get("project_name") or (sel.get("project_info") or {}).get("name") \
        or project_name

    template = args.template or cfg.get("template") or discover_template(cfg_dir)
    if not template or not os.path.exists(template):
        raise SystemExit(f"[输入] 未找到母版 pptx：请把「视觉检测方案.pptx」放到 {cfg_dir}，"
                         "或用 --template 指定")

    out_dir = cfg.get("output_dir")
    if out_dir and not os.path.isabs(out_dir):
        out_dir = os.path.join(cfg_dir, out_dir)
    out = args.out or os.path.join(out_dir or os.path.join(cfg_dir, project_name),
                                   project_name + ".pptx")

    # 场景文案防呆：默认值是"贴片"场景，非贴片项目不改 scene 会写出错文案
    if not (cfg.get("scene") or {}):
        if not any(k in project_name for k in ("贴片", "定位", "引导", "对位")):
            print(f"[提示] config 未写 scene，P3/P8/P11 将使用默认贴片文案；"
                  f"项目名「{project_name}」不像贴片/定位项目，"
                  f"请用 config.scene 覆盖 part_feature / core_goal / "
                  f"target_label / accuracy_label / accuracy_item / acceptance_item")

    ctx = build_ctx(cfg, sel)
    deck = build_deck(cfg, sel, ctx, {
        "template": template,
        "hardware_page": args.hardware_page,
        "company": args.company,
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
