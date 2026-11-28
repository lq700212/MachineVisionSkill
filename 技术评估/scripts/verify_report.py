# -*- coding: utf-8 -*-
"""verify_report：内部技术评估文档核验。交付前必跑，全 PASS 才算完。

检查项（FAIL 即打回）：
  1) 编码：严格 UTF-8
  2) 内部标记：文档前部含“内部”，并有“勿外发/仅限内部”等提示
  3) 章节完整：结论/背景/输入/未知项/可行性/工作量/风险/周期/成本/决策/行动
  4) 结论位置：结论速览在前 40 行内
  5) 图片：引用的图片文件存在，数量不少于 --min-images
  6) 图片说明：每张图后面 3 行内有“图 N”说明
  7) 占位符：不得残留 TODO / 待补充 / {{...}} / 从截图 等
  8) 表格：同一张表的列数一致；风险表至少 1 条数据且每格非空
  9) 数字一致：project.json 的 numbers 值必须出现在文档里；numbers 不得为空
 10) 工作量：出现“合计/总计”（缺失只 WARN）
 11) 周期：出现日期（缺失只 WARN）
 12) 结论质量：结论速览不得出现“需进一步/待确认/视情况”等空话，必须有明确判断
 13) 未知项质量：验证方法必须具体；责任方/截止不得写“待定/无”
 14) 风险质量：对策不得空泛（如“加强管理”），触发信号不得过短
 15) 行动质量：负责人/截止/产出不得写“待定/无”
 16) 关键表：未知项、风险、行动表不得有空单元格
 17) 全文空话：待定/待确认/视情况/需进一步 合计不得超过 4 处

用法：
  python verify_report.py report/xxx.md --config project.json
  python verify_report.py report/xxx.md --min-images 0
  python verify_report.py report/xxx.md --strict

退出码：0=无 FAIL，1=有 FAIL。
"""

import argparse
import json
import os
import re
import sys

SECTION_GROUPS = [
    ("结论速览", ["结论"]),
    ("背景与现状", ["背景", "现状", "项目概况", "现场"]),
    ("输入与事实", ["输入", "已确认", "技术判断", "事实"]),
    ("未知项 / 信息清单", ["未知", "待确认", "信息清单", "资料清单"]),
    ("可行性", ["可行性", "场景"]),
    ("工作量", ["工作量", "人天", "投入估算"]),
    ("风险", ["风险"]),
    ("周期", ["周期", "排期", "里程碑", "进度"]),
    ("成本 / 投入", ["定价", "成本", "报价", "预算", "投入"]),
    ("决策", ["决策", "接 / 不接", "接不接", "建议"]),
    ("行动", ["行动", "下一步", "待办"]),
]

PLACEHOLDER_BANS = [
    "TODO", "待补充", "待填写", "XXX", "xxx", "???", "占位符",
    "{{", "从截图", "此处省略",
]

IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)")
DATE_RE = re.compile(r"(20\d{2}[-/年]\d{1,2}|\d{1,2}/\d{1,2})")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
SEP_RE = re.compile(r"^:?-{3,}:?$")

# 空话：出现即说明作者没下结论
VAGUE_WORDS = [
    "需进一步", "进一步调研", "进一步确认", "进一步沟通", "待确认", "待定",
    "视情况", "看情况", "待评估", "待补充", "有待", "暂不", "暂定",
    "TBD", "N/A", "暂无", "再说", "想办法", "研究一下", "评估一下",
]
# 验证动作以这些词开头，等于没写
VAGUE_ACTION_PREFIXES = ["进一步", "沟通", "了解", "确认一下", "问一下", "再看看", "再说"]
# 关键列里出现这些值，等于没落实
WEAK_COL_VALUES = {
    "待定", "tbd", "无", "—", "-", "/", "暂无", "待确认", "未知",
    "不明确", "n/a", "na", "没有", "空",
}
# 风险对策里出现这些词且整句很短，判为空泛
WEAK_SOLUTION_WORDS = ["加强", "关注", "留意", "尽快", "尽量", "进一步", "视情况", "待定", "再说", "想办法"]


def split_cells(row):
    s = row.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def find_section(lines, keys):
    """返回 (起始行, 结束行, 标题)；找不到返回 None。"""
    heads = []
    for i, line in enumerate(lines):
        m = HEAD_RE.match(line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    for idx, (i, level, text) in enumerate(heads):
        if any(k in text for k in keys):
            end = len(lines)
            for j, lv, _ in heads[idx + 1:]:
                if lv <= level:
                    end = j
                    break
            return i, end, text
    return None


def resolve_path(p, report_dir, root):
    if os.path.isabs(p):
        cands = [p]
    else:
        cands = [os.path.join(report_dir, p), os.path.join(root, p), os.path.abspath(p)]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def check_table_consistency(lines):
    errors = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            block = []
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                block.append((j + 1, lines[j]))
                j += 1
            counts = {}
            for ln, row in block:
                counts.setdefault(len(split_cells(row)), []).append(ln)
            if len(counts) > 1:
                detail = "，".join(f"{c} 列（行 {ls[0]}）" for c, ls in sorted(counts.items()))
                errors.append(f"行 {block[0][0]} 起的表格列数不一致：{detail}")
            i = j
        else:
            i += 1
    return errors


def section_body(lines, keys):
    """返回章节正文；找不到返回空串。"""
    sec = find_section(lines, keys)
    return "\n".join(lines[sec[0]:sec[1]]) if sec else ""


def table_blocks(lines, start, end):
    """返回章节内的表格：[(表头行号, 表头单元格, [(行号, 单元格), ...])]。"""
    blocks = []
    i = start
    while i < end:
        if lines[i].strip().startswith("|"):
            block = []
            j = i
            while j < end and lines[j].strip().startswith("|"):
                block.append((j + 1, split_cells(lines[j])))
                j += 1
            data = [(ln, c) for ln, c in block if not all(SEP_RE.match(x) for x in c)]
            if data:
                blocks.append((data[0][0], data[0][1], data[1:]))
            i = j
        else:
            i += 1
    return blocks


def col_index(header, keys):
    """按表头关键字找列号；找不到返回 -1。"""
    for i, h in enumerate(header):
        if any(k in h for k in keys):
            return i
    return -1


def vague_hits(text):
    return [w for w in VAGUE_WORDS if w in text]


def cell(cells, idx):
    return cells[idx].strip() if 0 <= idx < len(cells) else ""


def main():
    ap = argparse.ArgumentParser(description="核验内部技术评估文档")
    ap.add_argument("report", help="评估文档路径")
    ap.add_argument("--config", default="", help="project.json（用于数字一致性检查）")
    ap.add_argument("--min-images", type=int, default=2, help="至少几张图，默认 2")
    ap.add_argument("--strict", action="store_true", help="WARN 也视为失败")
    args = ap.parse_args()

    path = os.path.abspath(args.report)
    if not os.path.exists(path):
        print(f"[FAIL] 文档不存在：{path}")
        return 1

    with open(path, "rb") as f:
        raw = f.read()

    passes, warns, fails = [], [], []

    # 1) 编码
    try:
        text = raw.decode("utf-8")
        passes.append("UTF-8 编码")
    except UnicodeDecodeError as e:
        fails.append(f"不是严格 UTF-8：{e}")
        text = raw.decode("utf-8", errors="replace")

    lines = text.splitlines()
    report_dir = os.path.dirname(path)
    root = os.path.dirname(os.path.abspath(args.config)) if args.config else os.getcwd()

    # 2) 内部标记
    head_text = text[:3000]
    if "内部" in head_text:
        passes.append("内部文档标记")
    else:
        fails.append("文档前部缺少“内部”标记，存在误发风险")
    if any(k in head_text for k in ["勿外发", "不对外", "仅限内部", "内部使用", "内部文档"]):
        passes.append("勿外发提示")
    else:
        warns.append("缺少“勿外发 / 仅限内部”提示")

    # 3) 章节
    missing = []
    for label, keys in SECTION_GROUPS:
        if not find_section(lines, keys):
            missing.append(label)
    if missing:
        fails.append("缺少章节：" + "、".join(missing))
    else:
        passes.append(f"章节完整（{len(SECTION_GROUPS)}/{len(SECTION_GROUPS)}）")

    # 4) 结论位置
    sec = find_section(lines, ["结论"])
    if sec:
        if sec[0] <= 40:
            passes.append("结论前置")
        else:
            fails.append(f"结论速览在第 {sec[0] + 1} 行，应在前 40 行内")

    # 5) 图片
    images = []
    for i, line in enumerate(lines):
        for m in IMG_RE.finditer(line):
            images.append((i, m.group(1)))
    missing_imgs = []
    no_caption = []
    for i, p in images:
        if p.startswith(("http://", "https://", "data:")):
            continue
        if not resolve_path(p, report_dir, root):
            missing_imgs.append(f"行 {i + 1}：{p}")
            continue
        nxt = ""
        for j in range(i + 1, min(i + 4, len(lines))):
            if lines[j].strip():
                nxt = lines[j].strip()
                break
        if not re.match(r"^[*_]?图\s*\d+", nxt):
            no_caption.append(f"行 {i + 1}：{p}")

    if len(images) < args.min_images:
        fails.append(f"图片不足：{len(images)} 张，要求至少 {args.min_images} 张")
    else:
        passes.append(f"图片数量（{len(images)} 张）")
    if missing_imgs:
        fails.append("图片文件缺失：" + "；".join(missing_imgs))
    else:
        passes.append("图片路径有效")
    if no_caption:
        fails.append("图片缺少“图 N”说明：" + "；".join(no_caption))
    else:
        passes.append("图片说明齐全")

    # 6) 占位符
    hits = [b for b in PLACEHOLDER_BANS if b in text]
    if hits:
        fails.append("残留占位符 / 禁语：" + "、".join(hits))
    else:
        passes.append("无占位符残留")

    # 7) 表格列数
    table_errors = check_table_consistency(lines)
    if table_errors:
        fails.extend(table_errors)
    else:
        passes.append("表格列数一致")

    # 8) 风险表
    sec = find_section(lines, ["风险"])
    if sec:
        rows = []
        for i in range(sec[0], sec[1]):
            s = lines[i].strip()
            if s.startswith("|"):
                rows.append((i + 1, split_cells(s)))
        data = [(ln, c) for ln, c in rows if not all(SEP_RE.match(x) for x in c)]
        if data:
            header = data[0][1]
            body = data[1:]
            if not body:
                fails.append("风险表没有数据行")
            else:
                bad = [f"行 {ln}" for ln, c in body if len(c) < 3 or any(not x for x in c)]
                if bad:
                    fails.append("风险表存在空单元格或列数不足：" + "、".join(bad))
                else:
                    passes.append(f"风险表（{len(body)} 条，均有对策列）")
                if not any(k in "".join(header) for k in ["对策", "措施", "应对", "缓解", "处理"]):
                    warns.append("风险表表头没有“对策 / 措施”列")
        else:
            fails.append("风险章节没有表格")
    else:
        fails.append("找不到风险章节")

    # 9) 数字一致
    if args.config:
        cfg_path = os.path.abspath(args.config)
        if not os.path.exists(cfg_path):
            warns.append(f"配置文件不存在：{cfg_path}")
        else:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
            nums = cfg.get("numbers") or []
            norm = re.sub(r"\s+", "", text)
            bad_nums = []
            for item in nums:
                if isinstance(item, str):
                    key, val = "", item
                else:
                    key, val = item.get("key", ""), item.get("value", "")
                if val and re.sub(r"\s+", "", str(val)) not in norm:
                    bad_nums.append(f"{key or '配置值'}“{val}”")
            if bad_nums:
                fails.append("数字与 project.json 不一致：" + "、".join(bad_nums))
            elif not nums:
                fails.append("project.json 未配置 numbers，无法核对关键数字")
            else:
                passes.append(f"关键数字一致（{len(nums)} 项）")

    # 10) 工作量合计
    sec = find_section(lines, ["工作量", "人天", "投入估算"])
    if sec:
        body = "\n".join(lines[sec[0]:sec[1]])
        if any(k in body for k in ["合计", "总计"]):
            passes.append("工作量有合计")
        else:
            warns.append("工作量章节没有“合计 / 总计”")

    # 11) 周期日期
    sec = find_section(lines, ["周期", "排期", "里程碑", "进度"])
    if sec:
        body = "\n".join(lines[sec[0]:sec[1]])
        if DATE_RE.search(body):
            passes.append("周期含日期")
        else:
            warns.append("周期章节没有具体日期")

    # 12) 结论质量：不许用“需进一步/待确认/视情况”代替结论
    quality_fail_start = len(fails)
    sec = find_section(lines, ["结论"])
    if sec:
        body = "\n".join(lines[sec[0]:sec[1]])
        hits = vague_hits(body)
        if hits:
            fails.append("结论速览存在无结论表述：" + "、".join(hits))
        probe = body.replace("技术可行性", "").replace("可行性", "")
        if not any(k in probe for k in ["中高", "中等", "中低", "可行", "不可行",
                                        "建议接", "不建议接", "可以接", "不接", "放弃"]):
            fails.append("结论速览没有明确的可行性判断（中高/中等/可行/不可行/不接/放弃）")

    # 13) 未知项质量：验证方法要具体，责任方/截止要落实
    sec = find_section(lines, ["未知", "待确认", "信息清单", "资料清单"])
    if sec:
        for _, header, rows in table_blocks(lines, sec[0], sec[1]):
            vi = col_index(header, ["验证方法", "验证", "方法", "怎么确认"])
            ri = col_index(header, ["责任方", "责任人", "负责"])
            di = col_index(header, ["截止", "期限", "时间"])
            for ln, cells in rows:
                v = cell(cells, vi)
                if vi >= 0:
                    if not v:
                        fails.append(f"未知项表第 {ln} 行验证方法为空")
                    elif any(v.startswith(p) for p in VAGUE_ACTION_PREFIXES):
                        fails.append(f"未知项表第 {ln} 行验证方法太虚：{v}")
                    elif len(v) < 4:
                        fails.append(f"未知项表第 {ln} 行验证方法过短：{v}")
                for idx, name in [(ri, "责任方"), (di, "截止")]:
                    if idx >= 0:
                        val = cell(cells, idx)
                        if not val or val.lower() in WEAK_COL_VALUES:
                            fails.append(f"未知项表第 {ln} 行{name}未落实：{val or '空'}")

    # 14) 风险质量：对策不许空泛，触发信号不许过短
    sec = find_section(lines, ["风险"])
    if sec:
        for _, header, rows in table_blocks(lines, sec[0], sec[1]):
            ci = col_index(header, ["对策", "措施", "应对", "缓解", "处理"])
            ti = col_index(header, ["触发", "信号", "预警", "现象"])
            for ln, cells in rows:
                v = cell(cells, ci)
                if ci >= 0:
                    if len(v) < 8:
                        fails.append(f"风险表第 {ln} 行对策过短/空泛：{v or '空'}")
                    else:
                        weak = [w for w in WEAK_SOLUTION_WORDS if w in v]
                        if weak and len(v) < 16:
                            fails.append(f"风险表第 {ln} 行对策空泛：{v}")
                t = cell(cells, ti)
                if ti >= 0 and len(t) < 6:
                    fails.append(f"风险表第 {ln} 行触发信号过短：{t or '空'}")

    # 15) 行动质量：负责人/截止/产出不许写“待定/无”
    sec = find_section(lines, ["行动", "下一步", "待办"])
    if sec:
        blocks = table_blocks(lines, sec[0], sec[1])
        if blocks:
            for _, header, rows in blocks:
                ai = col_index(header, ["动作", "事项", "任务", "内容"])
                oi = col_index(header, ["负责人", "责任人", "负责"])
                di = col_index(header, ["截止", "期限", "时间"])
                pi = col_index(header, ["产出", "交付", "结果"])
                for ln, cells in rows:
                    a = cell(cells, ai)
                    if ai >= 0 and len(a) < 4:
                        fails.append(f"行动表第 {ln} 行行动过短：{a or '空'}")
                    for idx, name in [(oi, "负责人"), (di, "截止"), (pi, "产出")]:
                        if idx >= 0:
                            val = cell(cells, idx)
                            if not val or val.lower() in WEAK_COL_VALUES:
                                fails.append(f"行动表第 {ln} 行{name}未落实：{val or '空'}")
        else:
            for line in lines[sec[0]:sec[1]]:
                s = line.strip()
                m = re.match(r"^\d+[.、]\s*(.+)$", s)
                if m and len(m.group(1)) < 8:
                    fails.append(f"行动项过短：{s}")

    # 16) 关键表空单元格：未知项 / 风险 / 行动
    for keys, label in [(["未知", "待确认"], "未知项"),
                        (["风险"], "风险"),
                        (["行动", "下一步", "待办"], "行动")]:
        sec = find_section(lines, keys)
        if not sec:
            continue
        for _, header, rows in table_blocks(lines, sec[0], sec[1]):
            for ln, cells in rows:
                if any(not c.strip() for c in cells):
                    fails.append(f"{label}表第 {ln} 行有空单元格")

    # 17) 全文空话计数：超过 4 处说明整篇没有结论
    vague_all = re.findall(r"待定|待确认|视情况|看情况|需进一步|进一步调研|TBD|暂无", text)
    if len(vague_all) >= 5:
        fails.append(f"全文无结论表述过多（{len(vague_all)} 处）：待定/待确认/视情况/需进一步")

    if len(fails) == quality_fail_start:
        passes.append("内容质量检查（结论/未知项/风险/行动）")

    # 输出
    print("== 技术评估文档核验 ==")
    print(f"文件：{path}")
    for p in passes:
        print(f"[PASS] {p}")
    for w in warns:
        print(f"[WARN] {w}")
    for f in fails:
        print(f"[FAIL] {f}")
    print(f"结果：{len(passes)} PASS / {len(warns)} WARN / {len(fails)} FAIL")

    if fails:
        return 1
    if args.strict and warns:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
