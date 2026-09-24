#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键盖章编排（盖章专员 skill 标准入口，v1.3.0 新增）。

把"强模型人工盖章流程"固化为代码——弱模型照抄运行即可得到相同结果
（铁律9：判断机检化，模型只需转述脚本打印的【决策】/【结论】）：

    Word→PDF → 首轮全自动 → 信号解析 → 预览渲染 + 签署区锚点校验
    → 偏离自动算偏移重试 → 打印结论与交付话术

用法：
    python seal_workflow.py <合同文件> [公章图片] [输出] [选项]

    合同文件：.pdf / 图片(png/jpg/jpeg/bmp/webp) / Excel(xlsx/xls/xlsm/xlsb)
              / Word(doc/docx，自动经 doc2pdf.py 转 PDF 后盖章)
    公章图片：可选，默认用 skill 目录下"默认公章图片.png"
    输出：可选；不指定时按主脚本默认规则（原名_已盖章.pdf / 原图格式）

    --role 角色          首轮即指定角色（甲方/乙方/卖方/买方…），跳过自动匹配
    --no-default-role    关闭"双方无章默认盖乙方"自动重试（纯自动+报告）
    --no-auto-retry      关闭"偏离签署区自动算偏移重试"（只给出建议命令）
    --preview-dpi N      预览图渲染分辨率，默认 110（只影响预览图清晰度）
    其余 --company/--rotate/--offset-x/--offset-y/--side/--keywords/
    --no-auto/--no-flatten/--dpi/--dry-run 原样透传给 pdf_seal_stamper.py

固化的三条方法（根因注释，写给下次排查的人）：
  1. 双方无章默认乙方：首轮**不指定 --role** 全自动跑（有对方章→对称、
     真章→智能匹配都能命中）；只有"落到默认兜底位置"（最不可靠的分支，
     常盖到正文中央）**且**文档中无已有公章时，才自动用 --role 乙方重试。
     ——用户明令的默认规则，不问用户直接执行。
  2. 锚点校验代替肉眼估算：全部坐标统一用**顶部原点 y 向下**
    （pdfplumber/fitz 系；主脚本的 目标中心/公章位置 同系，跨 reportlab
     底原点的换算只在主脚本步骤5内部出现一次，见 AGENTS.md 铁律2）。
     在盖章页找"角色名+签署行"锚点行，目标=(行中心x, 行中心y+20)，
     与章中心比较：|dx|<=40 且 |dy|<=70 判"在签署区"，否则按下式
     给出/自动执行偏移重试：next_offset = 用户offset + (目标-本轮目标中心)。
     注意重试必须带**累计总量**（主脚本是 target += offset 绝对量，
     不是增量，传增量会只挪一小步，曾犯）。
  3. 预览图强制目检：只要生成了输出（PDF→渲染盖章页，图片→输出即预览），
     就落盘 `<输出基名>_预览.png` 并打印路径；【结论】✅也不代表可跳过目检。
"""

import argparse
import os
import re
import subprocess
import sys

# GBK 控制台打印中文/emoji 保命（v1.2.1 同类事故）
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
STAMPER = os.path.join(SKILL_DIR, "pdf_seal_stamper.py")
DOC2PDF = os.path.join(SKILL_DIR, "doc2pdf.py")
DEFAULT_SEAL = os.path.join(SKILL_DIR, "默认公章图片.png")
PIP_MIRROR = "https://mirrors.aliyun.com/pypi/simple/"

WORD_EXTS = (".doc", ".docx")
PDF_EXTS = (".pdf",)
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
EXCEL_EXTS = (".xlsx", ".xls", ".xlsm", ".xlsb")

DEFAULT_ROLE = "乙方"   # 双方无章时的默认盖章角色（用户明令）
NEAR_DX, NEAR_DY = 40, 70  # 锚点判定阈值 pts（约 1/3 章宽，实测校准）
MAX_RUNS = 3               # 首轮 + 角色重试 + 偏移重试，永不更多（防循环）

# 角色别名：签署栏常写"卖方"而抬头写"乙方"（买方（甲方）/卖方（乙方）式），
# 找锚点行时本名找不到就找别名（只做"同侧"映射，不做甲乙互串）。
ROLE_ALIASES = {
    "甲方": ["甲方", "买方"],
    "买方": ["买方", "甲方"],
    "乙方": ["乙方", "卖方"],
    "卖方": ["卖方", "乙方"],
    "供方": ["供方", "乙方", "卖方"],
    "需方": ["需方", "甲方", "买方"],
}
SIG_WORDS = ("签字", "盖章", "签章", "公章", "代表", "签约", "日期")
CO_WORDS = ("公司", "有限", "工作室", "集团", "合作社", "工厂", "商行",
            "中心", "服务部", "经营部", "个体")


def run_cmd(argv, timeout):
    """跑子进程，返回 (returncode, stdout_text)。stdout 按 utf-8 解码
    （主脚本 v1.2.1 起已重配 utf-8 输出；errors=replace 防残字节崩）。"""
    try:
        r = subprocess.run(argv, capture_output=True, timeout=timeout)
        out = (r.stdout or b"").decode("utf-8", "replace")
        err = (r.stderr or b"").decode("utf-8", "replace")
        return r.returncode, out + ("\n" + err if err.strip() else "")
    except subprocess.TimeoutExpired:
        return 124, f"❌ 子进程超时（{timeout}s）：{' '.join(argv)}"


def step_convert_word(contract):
    """步骤0：Word→PDF（内置 doc2pdf.py）。返回 (pdf_path, note)。"""
    print("── 步骤0：Word→PDF 转换 ──")
    code, out = run_cmd([sys.executable, DOC2PDF, contract], timeout=300)
    print(out)
    if code != 0:
        return None, "Word 转 PDF 失败（见上方指引）"
    m = re.search(r"转换成功:\s*(.+?)\s*$", out, re.M)
    if not m or not os.path.exists(m.group(1).strip()):
        return None, "转换输出解析失败，请手动用 Word 另存为 PDF 后重跑"
    return m.group(1).strip(), ""


def parse_stamper_output(out):
    """解析主脚本输出信号。返回 dict（缺啥补 None，调用方按有无判断）。"""
    s = {}
    m = re.search(r"检测到 (\d+) 个图片，其中 (\d+) 个被识别为公章", out)
    s["existing"] = int(m.group(2)) if m else 0
    m = re.search(r"智能定位成功（策略：(.+?)）", out)
    s["smart_strategy"] = m.group(1) if m else None
    s["smart_ok"] = s["smart_strategy"] is not None
    s["side"] = ("左侧" if "）：左侧" in out else
                 "右侧" if "）：右侧" in out else "")
    s["fallback"] = "智能定位未成功，回退常规定位" in out
    s["keyword_ok"] = "关键词定位成功" in out
    s["default_pos"] = "关键词定位失败，使用默认位置" in out
    s["seal_ocr_fail"] = "公章公司名 OCR 失败" in out
    s["no_parties"] = "合同未提取到'角色: 公司名'信息" in out
    m = re.search(r"合同中未找到「(.+?)」的盖章位置", out)
    s["role_not_found"] = m.group(1) if m else None
    m = re.search(r"公章匹配到角色:\s*(.+?)（(.+?)）", out)
    s["matched"] = (m.group(1), m.group(2)) if m else None
    m = re.search(r"使用手动指定角色:\s*(.+)", out)
    s["manual_role"] = m.group(1).strip() if m else None
    s["need_human"] = ("建议人工确认" in out)
    s["avoided"] = "已自动避让" in out
    s["symmetric"] = "对侧对称" in out
    m = re.search(r"目标中心:\s*\(([\d.]+),\s*([\d.]+)\)", out)
    s["target"] = (float(m.group(1)), float(m.group(2))) if m else None
    m = re.search(r"公章位置:\s*\(([\d.]+),\s*([\d.]+)\) → "
                  r"\(([\d.]+),\s*([\d.]+)\)", out)
    if m:
        x0, y0, x1, y1 = (float(m.group(i)) for i in range(1, 5))
        s["seal_center"] = ((x0 + x1) / 2, (y0 + y1) / 2)
    else:
        s["seal_center"] = None
    m = re.search(r"^\s*位置:\s*\(([\d.]+),\s*([\d.]+)\)", out, re.M)
    m2 = re.search(r"尺寸:\s*([\d.]+) x ([\d.]+) pts", out)
    if m and m2 and s["seal_center"] is None:
        # dry-run 分支：位置=左上角，补尺寸得中心（顶部原点系内加减一致）
        x, y = float(m.group(1)), float(m.group(2))
        s["seal_center"] = (x + float(m2.group(1)) / 2,
                            y + float(m2.group(2)) / 2)
    m = re.search(r"^\s*输出:\s*(.+?)\s*$", out, re.M)
    s["output"] = m.group(1).strip() if m else None
    m = re.search(r"盖章页（第 (\d+) 页）", out)
    s["stamp_page"] = int(m.group(1)) if m else None
    m = re.search(r"输入类型:\s*(.+)", out)
    s["input_kind"] = m.group(1).strip() if m else ""
    s["collision"] = ("输出路径与" in out and "路径相同" in out)
    s["excel_fail"] = "Excel 转 PDF 失败" in out
    s["ocr_missing"] = "OCR 依赖不可用" in out
    s["ocr_built"] = "OCR 建立文字层完成" in out
    return s


def print_decision(sig):
    """按决策表打印【决策】（弱模型照抄转述即可，无需自己判断）。"""
    print("──【决策】信号解读（对照 SKILL.md 决策表）──")
    if sig["smart_ok"]:
        print(f"  ✅ 智能定位成功（策略：{sig['smart_strategy']}）："
              "可交付，仍需目检预览图")
    elif sig["fallback"]:
        print("  → 智能定位未成功，已回退常规定位")
    if sig["keyword_ok"]:
        print("  ⚠️  退化为关键词定位：未能智能识别角色，请核对位置后交付")
    if sig["default_pos"]:
        print("  ❌ 落到默认兜底位置（末页右下角）：位置不可靠，"
              "必须用 --role/偏移修正，不可直接交付")
    if sig["seal_ocr_fail"]:
        print("  ⚠️  公章公司名 OCR 失败：可用 read 查看公章图后加 "
              '--company "公司名" 重试（样章环形"北京"字样属正常失败）')
    if sig["no_parties"]:
        print("  ⚠️  合同未提取到签署方：人工判断我方角色后加 --role 重试")
    if sig["role_not_found"]:
        print(f"  → 合同中没有「{sig['role_not_found']}」的盖章栏 "
              "（只有签字栏时属正常，改用签署区锚点校验）")
    if sig["matched"]:
        print(f"  → 公章匹配到角色: {sig['matched'][0]}（{sig['matched'][1]}）")
    if sig["symmetric"]:
        print("  → 策略：对侧对称（与他角色盖章栏同高），正常交付并说明行位置")
    if sig["avoided"]:
        print("  → 已自动避让对方签章区，正常交付")
    if sig["need_human"]:
        print("  ⚠️  含「建议人工确认」：必须把确认提醒写进交付话术")


def find_anchor(pdf_path, role, page_idx):
    """在盖章页找签署区锚点行。返回 (tx, ty, 描述) 或 None。

    找法：pdfplumber 取词→按行聚拢→**所有别名**的行全部收集后全局择优
    （签署词+2，公司词+1；盖章页+2、末页+1；再按偏下、偏右排序），
    取分高者；目标=(行中心x, 行中心y+20)（章压签署行是真实习惯，实测校准）。

    根因（曾犯）：按"本名→别名"逐个返回首个命中——抬头"卖方（乙方）：…"
    行含"乙方"而签署栏只写"卖方"，结果锚点落在页眉抬头，偏移重试把章
    盖到页眉且自检"通过"（循环论证）。必须全别名收集+位置加权，
    签署区（末页偏下）天然赢过抬头。
    """
    try:
        import pdfplumber
    except Exception:
        print("  ⚠️  缺少 pdfplumber，锚点校验跳过："
              f"pip install pdfplumber -i {PIP_MIRROR}")
        return None
    try:
        doc = pdfplumber.open(pdf_path)
    except Exception as e:
        print(f"  ⚠️  锚点分析打不开源 PDF: {e}")
        return None
    try:
        n = len(doc.pages)
        names = ROLE_ALIASES.get(role, [role])
        cands = []  # (score, page_bonus, yc, x0, tx, ty, 描述)
        for p in range(n):
            page = doc.pages[p]
            bonus = (2 if p == page_idx else 0) + (1 if p == n - 1 else 0)
            for name in names:  # 全别名收集，不早退（防抬头行抢赢签署行）
                for item in _anchor_lines_on_page(page, name):
                    score, tx, ty, desc = item
                    cands.append((score, bonus, ty, tx, tx, ty,
                                  f"{desc}（第{p + 1}页，按{name}匹配）"))
            g = _generic_sign_row(page)
            if g:
                tx, ty, desc = g
                cands.append((0, bonus, ty, tx, tx, ty,
                              f"{desc}（第{p + 1}页，无角色名兜底）"))
        if not cands:
            return None
        best = max(cands, key=lambda c: (c[0], c[1], c[2], c[3]))
        return best[4], best[5], best[6]
    finally:
        try:
            doc.close()
        except Exception:
            pass


def _lines_of(page):
    """词按 top 聚拢成行：[((x0, x1, yc, norm_text), words)]（顶部原点系）。

    约束：行内分侧必须用同一聚拢结果的词（按 round(top) 键），不许用
    yc 反查（yc 是均值，round(yc)≠行键，会捞到别行的词，曾犯）。
    """
    rows = {}
    for w in page.extract_words() or []:
        rows.setdefault(round(w["top"]), []).append(w)
    lines = []
    for top, ws in rows.items():
        ws = sorted(ws, key=lambda w: w["x0"])
        x0 = min(w["x0"] for w in ws)
        x1 = max(w["x1"] for w in ws)
        yc = (min(w["top"] for w in ws) + max(w["bottom"] for w in ws)) / 2
        norm = "".join(w["text"] for w in ws).replace(" ", "")
        lines.append(((x0, x1, yc, norm), ws))
    return lines, page.height


# 同侧/对侧：签署栏"买方…卖方…"常同处一行，锚点必须只框本侧
SIDES = ({"甲方", "买方", "需方"}, {"乙方", "卖方", "供方"})


def _opposite_aliases(name):
    for side in SIDES:
        if name in side:
            other = SIDES[1] if side is SIDES[0] else SIDES[0]
            return [a for a in other]
    return []


def _anchor_lines_on_page(page, name):
    """返回该页所有含角色名的行：[(score, tx, ty, 描述)]，由调用方全局择优。
    顶部 10% 页眉直接排除（抬头 logo/标题不是签署区）。

    根因（曾犯）：签署栏"买方：___ 卖方：X公司"本就是同一行，
    整行取中心会把目标定在两栏正中间（章骑中缝压正文）。
    行内若同时含对侧别名，只框本侧词：对侧在左→取本侧词及之后，
    对侧在右→取对侧词之前（签字栏本侧公司名紧跟本侧标签，真实版式）。
    """
    lines, h = _lines_of(page)
    opp = _opposite_aliases(name)
    out = []
    for (x0, x1, yc, t), words in lines:
        if name not in t or yc < h * 0.10:
            continue
        score = (2 if any(k in t for k in SIG_WORDS) else 0) + \
                (1 if any(k in t for k in CO_WORDS) else 0)
        # 行内分侧：按词分别找本侧/对侧标签的位置
        self_i = next((i for i, w in enumerate(words) if name in w["text"]),
                      None)
        opp_i = next((i for i, w in enumerate(words)
                      if any(a in w["text"] for a in opp)), None)
        if self_i is not None and opp_i is not None and opp_i != self_i:
            region = words[self_i:] if opp_i < self_i else words[:opp_i]
        else:
            region = words
        if not region:
            region = words
        rx0 = min(w["x0"] for w in region)
        rx1 = max(w["x1"] for w in region)
        out.append((score, (rx0 + rx1) / 2, yc + 20, t[:24]))
    return out


def _generic_sign_row(page):
    lines, h = _lines_of(page)
    best = None
    for (x0, x1, yc, t), _ws in lines:
        if not any(k in t for k in ("签字", "签约日期", "盖章", "签章")):
            continue
        if yc < h * 0.10:
            continue
        key = (yc, x0)
        if best is None or key > best[0]:
            best = (key, (x0 + x1) / 2, yc + 20, t[:24])
    return best[1:] if best else None


def render_preview(output_path, stamp_page, dpi):
    """渲染预览图。PDF 输出→渲染盖章页；图片输出→输出即预览。"""
    ext = os.path.splitext(output_path)[1].lower()
    if ext != ".pdf":
        print(f"  预览图即输出图片: {output_path}")
        return output_path
    try:
        import pymupdf
    except Exception:
        print("  ⚠️  缺少 pymupdf，预览图跳过："
              f"pip install pymupdf -i {PIP_MIRROR}")
        return None
    try:
        doc = pymupdf.open(output_path)
        idx = max(0, min((stamp_page or len(doc)) - 1, len(doc) - 1))
        pix = doc[idx].get_pixmap(dpi=dpi)
        prev = os.path.splitext(output_path)[0] + "_预览.png"
        pix.save(prev)
        doc.close()
        print(f"  预览图: {prev}（请用 read 查看目检）")
        return prev
    except Exception as e:
        print(f"  ⚠️  预览图渲染失败: {e}")
        return None


def source_text_len(pdf_path):
    """源 PDF 文字量（<20 字符视为无文本层，锚点分析跳过）。"""
    try:
        import pdfplumber
        total = 0
        with pdfplumber.open(pdf_path) as doc:
            for p in doc.pages:
                total += len(p.extract_text() or "")
                if total >= 20:
                    return total
        return total
    except Exception:
        return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="一键盖章编排 v1.3.0：Word→PDF→全自动→预览+锚点校验→偏离自动重试",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("contract", help="合同文件：pdf/图片/Excel/Word(doc/docx)")
    ap.add_argument("seal", nargs="?", default=None, help="公章图片（可选）")
    ap.add_argument("output", nargs="?", default=None, help="输出路径（可选）")
    ap.add_argument("--role", default=None, help="首轮即指定角色（跳过自动匹配）")
    ap.add_argument("--no-default-role", action="store_true",
                    help="关闭双方无章默认盖乙方的自动重试")
    ap.add_argument("--no-auto-retry", action="store_true",
                    help="关闭偏离签署区自动算偏移重试（只给建议命令）")
    ap.add_argument("--preview-dpi", type=int, default=110,
                    help="预览图分辨率（默认110，只影响预览清晰度）")
    for a, kw in (("--company", {}), ("--rotate", {"type": float}),
                  ("--offset-x", {"type": float, "default": 0.0}),
                  ("--offset-y", {"type": float, "default": 0.0}),
                  ("--side", {}), ("--keywords", {}), ("--dpi", {"type": int})):
        ap.add_argument(a, **kw)
    ap.add_argument("--no-auto", action="store_true")
    ap.add_argument("--no-flatten", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    contract = args.contract
    if not os.path.exists(contract):
        print(f"❌ 合同文件不存在: {contract}")
        return 1
    ext = os.path.splitext(contract)[1].lower()
    if ext not in WORD_EXTS + PDF_EXTS + IMAGE_EXTS + EXCEL_EXTS:
        print(f"❌ 不支持的合同文件类型: {ext or '(无扩展名)'}"
              f"（支持 .pdf / 图片{''.join(IMAGE_EXTS)} / "
              f"Excel{''.join(EXCEL_EXTS)} / Word{''.join(WORD_EXTS)}）")
        return 1
    # 位置参数防呆（test4 事故档案：位置错位曾覆盖销毁默认公章）：
    # 只给两参且第二参是"不存在的 .pdf"→ 按输出理解、公章用默认
    # （公章不可能是 PDF；存在的文件仍按公章理解，不静默猜）。
    if args.seal and not args.output and not os.path.exists(args.seal) \
            and args.seal.lower().endswith(".pdf"):
        print(f"  → 第二参 {args.seal} 不存在且为 .pdf，按\"输出\"理解，"
              "公章用默认")
        args.output, args.seal = args.seal, None

    # ── 步骤0：Word→PDF ──
    src_pdf = contract
    if ext in WORD_EXTS:
        src_pdf, note = step_convert_word(os.path.abspath(contract))
        if src_pdf is None:
            print(f"❌ {note}")
            return 1

    seal = args.seal or DEFAULT_SEAL
    if not os.path.exists(seal):
        print(f"❌ 公章图片不存在: {seal}")
        if args.seal:
            print("  提示：位置参数顺序是 合同 公章 输出——若你是想指定输出，"
                  "请用三个参数（中间补公章），或第二参直接给 .pdf 输出路径"
                  "（不存在的 .pdf 会自动按输出理解、公章用默认）")
        return 1
    if os.path.abspath(seal) == os.path.abspath(DEFAULT_SEAL):
        print("  ℹ️  使用默认公章：请用 read 查看确认是否为贵公司章；"
              "环形\"北京\"重复字样=样章，仅供预览")

    base_opt = [sys.executable, STAMPER, src_pdf]
    if args.seal:
        base_opt.append(args.seal)
    elif args.output:
        # 显式输出 + 默认章：必须补传默认章路径（主脚本位置顺序无"跳过公章"位，
        # 不补则输出会掉进公章位报"公章不存在"——实测曾犯）
        base_opt.append(DEFAULT_SEAL)
    if args.output:
        base_opt.append(args.output)
    flag_opt = []
    if args.company:
        flag_opt += ["--company", args.company]
    if args.rotate is not None:
        flag_opt += ["--rotate", str(args.rotate)]
    if args.side:
        flag_opt += ["--side", args.side]
    if args.keywords:
        flag_opt += ["--keywords", args.keywords]
    if args.dpi:
        flag_opt += ["--dpi", str(args.dpi)]
    for f in ("no_auto", "no_flatten", "dry_run"):
        if getattr(args, f):
            flag_opt.append("--" + f.replace("_", "-"))

    role_forced = args.role is not None
    role = args.role or DEFAULT_ROLE
    user_ox, user_oy = float(args.offset_x or 0), float(args.offset_y or 0)

    runs = [0]  # 轮次计数：上限 MAX_RUNS（首轮+角色重试+偏移重试）

    def run_round(extra, tag):
        runs[0] += 1
        cmd = base_opt + flag_opt + extra
        print(f"\n── 盖章第{tag}轮 ──\n  $ {' '.join(cmd)}")
        code, out = run_cmd(cmd, timeout=900)
        print(out)
        return code, parse_stamper_output(out)

    # ── 第1轮：全自动（用户给了 --role 则首轮即用）──
    r1_extra = (["--role", args.role] if role_forced else []) + \
               (["--offset-x", str(user_ox), "--offset-y", str(user_oy)]
                if (user_ox or user_oy) else [])
    code, sig = run_round(r1_extra, "1（全自动）")
    print_decision(sig)
    if code != 0 or (not args.dry_run and not sig["output"]):
        if sig["collision"]:
            print("❌ 输出路径撞了输入/公章路径：换一个输出路径重跑")
        elif sig["excel_fail"]:
            print("❌ 按输出里的指引手动转 PDF 后重跑")
        elif sig["ocr_missing"]:
            print("❌ 按输出里的 pip 命令装好 OCR 依赖后重跑")
        else:
            print("❌ 主脚本失败（原因见上方输出），修好后重跑")
        return 1

    landed_default = sig["default_pos"] or (
        sig["fallback"] and not sig["keyword_ok"] and not sig["smart_ok"])

    # ── 第2轮：双方无章默认乙方（用户明令，不问直接执行）──
    if (landed_default and not role_forced and not args.no_default_role
            and not args.dry_run and sig["existing"] == 0):
        print(f"\n→ 默认规则（双方无章盖{DEFAULT_ROLE}）："
              f"首轮落到默认兜底位置，自动用 --role {role} 重试")
        code, sig = run_round(["--role", role], f"2（默认{role}）")
        print_decision(sig)
        if code != 0 or not sig["output"]:
            print("❌ 第2轮失败（见上方输出），修好后重跑")
            return 1
        role_forced = True

    # ── dry-run：只分析，给建议命令 ──
    if args.dry_run:
        print("\n── dry-run 分析（未生成文件）──")
        if sig["seal_center"] and src_pdf.lower().endswith(".pdf") \
                and source_text_len(src_pdf) >= 20:
            anchor = find_anchor(src_pdf, role if role_forced else DEFAULT_ROLE,
                                 (sig["stamp_page"] or 1) - 1)
            if anchor:
                gap = _report_gap(sig["seal_center"], anchor, dry=True)
                if abs(gap[0]) <= NEAR_DX and abs(gap[1]) <= NEAR_DY:
                    print("【结论】🔍 落点在签署区：去掉 --dry-run 执行同命令即可")
                else:
                    print("【结论】🔍 落点偏离签署区：按上方\"建议\"偏移执行正式命令")
            else:
                print("【结论】🔍 无签署区锚点：正式执行后必须目检预览图再交付")
        else:
            print("【结论】🔍 无法机检（无源文字层或无定位结果）："
                  "正式执行后必须目检预览图再交付")
        print("  注：dry-run 不生成文件，正式命令=去掉 --dry-run 的同命令")
        return 0

    # ── 预览渲染 ──
    print("\n── 预览渲染 ──")
    out_ext = os.path.splitext(sig["output"])[1].lower()
    preview = render_preview(sig["output"], sig["stamp_page"],
                             args.preview_dpi)

    # ── 锚点校验 + 第3轮：偏离自动算偏移重试 ──
    verdict, gap = "visual", None  # visual=锚点机检跳过，只靠目检
    analyzable = (out_ext == ".pdf" and src_pdf.lower().endswith(".pdf")
                  and source_text_len(src_pdf) >= 20)
    if analyzable and sig["seal_center"]:
        anchor = find_anchor(src_pdf, role if role_forced else DEFAULT_ROLE,
                             (sig["stamp_page"]
                              or _page_count(src_pdf)) - 1)
        if anchor:
            gap = _report_gap(sig["seal_center"], anchor, dry=False)
            if abs(gap[0]) <= NEAR_DX and abs(gap[1]) <= NEAR_DY:
                verdict = "ok"
            elif runs[0] < MAX_RUNS and not args.no_auto_retry:
                verdict = "retry"
            else:
                verdict = "bad"
        else:
            print("  ⚠️  未找到签署区锚点行：无法机检，只能目检预览图")
    else:
        reason = ("图片/扫描件/Excel 输入无源文字层" if out_ext == ".pdf"
                  else "图片输出无文字层")
        print(f"  ⚠️  锚点机检跳过（{reason}）：必须目检预览图")

    if verdict == "retry":
        dx, dy = gap
        # total = 用户offset + 本轮增量（主脚本取绝对量，传增量会少挪，曾犯）
        nx, ny = round(user_ox + dx), round(user_oy + dy)
        print(f"\n→ 落点偏离签署区 {dx:+.0f}/{dy:+.0f}pts，"
              f"自动重试（累计偏移 --offset-x {nx} --offset-y {ny}）")
        last_extra = (["--role", role] if role_forced else []) + \
                     ["--offset-x", str(nx), "--offset-y", str(ny)]
        code, sig = run_round(last_extra, "3（偏移修正）")
        print_decision(sig)
        if code == 0 and sig["output"]:
            preview = render_preview(sig["output"], sig["stamp_page"],
                                     args.preview_dpi)
            if sig["seal_center"] and analyzable:
                anchor = find_anchor(
                    src_pdf, role, (sig["stamp_page"]
                                    or _page_count(src_pdf)) - 1)
                if anchor:
                    gap = _report_gap(sig["seal_center"], anchor, dry=False)
                    verdict = ("ok" if abs(gap[0]) <= NEAR_DX
                               and abs(gap[1]) <= NEAR_DY else "bad")

    # ── 结论与交付话术（固定，弱模型照抄转述）──
    print("\n" + "═" * 55)
    if verdict == "ok":
        print(f"【结论】✅ 位置可信：章中心距签署区锚点"
              f" ({gap[0]:+.0f},{gap[1]:+.0f})pts，在阈值内")
        print("  仍请目检预览图，无误后交付输出文件")
    elif verdict == "bad":
        print(f"【结论】⚠️ 位置待确认：章中心距签署区锚点"
              f" ({gap[0]:+.0f},{gap[1]:+.0f})pts，超出阈值")
        print("  必须目检预览图：位置不对就按上方建议偏移重跑，确认后再交付")
    else:
        print("【结论】⚠️ 位置靠目检确认（锚点机检跳过）："
              "必须打开预览图核对章落在签署区后再交付")
    print("── 交付话术 ──")
    if not args.no_flatten:
        print("  输出为防编辑压平版：公章与页面融为一体，PDF 编辑软件无法单独"
              "选中/移动/删除公章（法律安全），文字仍可搜索复制")
    else:
        print("  ⚠️  本次 --no-flatten（可编辑版，仅内部核对）：公章是独立图片"
              "对象，有被移走法律风险，正式交付必须用默认压平重出")
    if out_ext != ".pdf":
        print("  图片输出：章已融入图片像素，任何编辑软件都无法单独移除")
    if sig.get("need_human"):
        print("  ⚠️  本单含「建议人工确认」（无该角色盖章栏，章盖公司名旁）"
              "：交付必须附带确认提醒")
    if os.path.abspath(seal) == os.path.abspath(DEFAULT_SEAL):
        print("  ⚠️  本次用默认样章：正式版请提供贵公司真实公章图片重出")
    print(f"  输出文件: {sig['output']}")
    if preview and preview != sig["output"]:
        print(f"  预览图: {preview}")
    print("═" * 55)
    return 0


def _report_gap(center, anchor, dry):
    tx, ty, desc = anchor
    dx, dy = tx - center[0], ty - center[1]
    tag = "（预估，未盖章）" if dry else ""
    ok = abs(dx) <= NEAR_DX and abs(dy) <= NEAR_DY
    print(f"  锚点行: {desc}")
    print(f"  章中心距锚点目标: ({dx:+.0f},{dy:+.0f})pts{tag} "
          f"→ {'✅ 在签署区' if ok else '❌ 偏离签署区'}")
    if not ok:
        print(f"  建议: 加 --offset-x {dx:+.0f} --offset-y {dy:+.0f} 重试"
              "（相对本轮位置的总量）")
    return dx, dy


def _page_count(pdf_path):
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as doc:
            return len(doc.pages)
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
