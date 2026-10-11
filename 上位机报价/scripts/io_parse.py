# -*- coding: utf-8 -*-
"""IO 表脚本化摸底（布局无关版）。

只做事实提取，不下报价结论。不同项目的 IO 表长得不一样（标题行数、
信号横排竖排、编码写法都可能不同），所以本脚本不假设任何布局：
  - 数据起始行 = 首个出现地址编码的行，其上方一律视为表头区；
  - 信号文本列 = CJK 密度最高的列（自动浮出，不写死列号）；
  - 地址编码格式可用 --code-pattern 覆盖（缺省 PLC 式 X/Y/R/D/M + 十六进制）。

依赖：openpyxl（pip install openpyxl）。

用法：
  python io_parse.py "xxIO表.xlsx" [-o 输出目录] [--code-pattern 正则]

输出（全部 UTF-8）：
  1) 终端：工作表总览 + 每页角色判定 + 关键发现（照抄进报价文档 §1）
  2) <outdir>/io_dump.txt：小表（<=200 行）全量转储；大表头 30 + 尾 10
  3) <outdir>/io_stats.json：机器可读统计

判定规则：
  - 主信号页：CJK 格最多的一页（信号描述集中处）→ 按此页估有效信号数。
  - 有效信号数 ≈ 信号文本列的去重非空值个数（自动识别，不数标题）。
  - 有表头无数据列：表头区有字、数据区全空（如伺服列）→ 别报这部分活。
  - 纯编码模板页：有效格 ≥95% 匹配地址编码且 CJK 为 0 → 对报价无用。
  - 空白格不脑补：数量空≠0，标“空白待确认”。
"""
import argparse
import json
import os
import re
import sys

DEFAULT_CODE = r"^[A-Za-z]{1,4}[0-9A-Fa-f]+$"
CJK_PAT = re.compile(r"[\u4e00-\u9fff]")


def cell_text(v):
    if v is None:
        return ""
    return str(v).strip()


def main():
    ap = argparse.ArgumentParser(description="IO 表脚本化摸底（布局无关）")
    ap.add_argument("xlsx", help="IO 表 xlsx 路径")
    ap.add_argument("-o", "--outdir", default="io_parse_out", help="输出目录")
    ap.add_argument("--code-pattern", default=DEFAULT_CODE,
                    help="地址编码正则（缺省 PLC 式，如西门子 %%IX0.0/Modbus 40001 请覆盖）")
    args = ap.parse_args()
    try:
        code_pat = re.compile(args.code_pattern)
    except re.error as e:
        print(f"code-pattern 非法：{e}", file=sys.stderr)
        return 2

    try:
        import openpyxl
    except ImportError:
        print("缺依赖：pip install openpyxl", file=sys.stderr)
        return 2
    if not os.path.isfile(args.xlsx):
        print(f"文件不存在：{args.xlsx}", file=sys.stderr)
        return 2

    os.makedirs(args.outdir, exist_ok=True)
    wb = openpyxl.load_workbook(args.xlsx, data_only=True)
    dump_lines = []
    stats = {"file": os.path.basename(args.xlsx), "sheets": []}
    print(f"工作表：{wb.sheetnames}（共 {len(wb.sheetnames)} 页）")

    for s in wb.sheetnames:
        ws = wb[s]
        max_r, max_c = ws.max_row, ws.max_column
        merged = [str(r) for r in ws.merged_cells.ranges]
        grid = [[cell_text(ws.cell(row=r, column=c).value)
                 for c in range(1, max_c + 1)] for r in range(1, max_r + 1)]

        nonempty_rows = sum(1 for row in grid if any(v != "" for v in row))
        total = code = cjk = 0
        col_cjk = [0] * max_c
        col_code = [0] * max_c
        for row in grid:
            for ci, v in enumerate(row):
                if v == "":
                    continue
                total += 1
                if code_pat.match(v):
                    code += 1
                    col_code[ci] += 1
                if CJK_PAT.search(v):
                    cjk += 1
                    col_cjk[ci] += 1

        # 数据起始行：首个出现地址编码的行；找不到则回退到首个≥3 格非空行
        data_start = None
        for i, row in enumerate(grid, start=1):
            if any(code_pat.match(v) for v in row if v != ""):
                data_start = i
                break
        if data_start is None:
            for i, row in enumerate(grid, start=1):
                if sum(1 for v in row if v != "") >= 2:
                    data_start = i
                    break
        hdr_rows = (data_start - 1) if data_start else min(1, max_r)

        # 有表头无数据列：表头区有字、数据区全空
        header_no_data = []
        for ci in range(max_c):
            hdr = any(grid[r][ci] != "" for r in range(min(hdr_rows, max_r)))
            dat = any(grid[r][ci] != "" for r in range(hdr_rows, max_r))
            if hdr and not dat:
                header_no_data.append(ci + 1)
        # 信号文本列候选：CJK 密度最高的列（取前 2）
        ranked = sorted(range(max_c), key=lambda ci: col_cjk[ci], reverse=True)
        sig_cols = [ci + 1 for ci in ranked[:2] if col_cjk[ci] > 0]
        # 有效信号数：信号列在数据区的去重非空值
        sig_values = set()
        for ci in [c - 1 for c in sig_cols]:
            for r in range(hdr_rows, max_r):
                v = grid[r][ci]
                if v != "" and not code_pat.match(v):
                    sig_values.add(v)

        is_template = total > 0 and (code / total) >= 0.95 and cjk == 0
        info = {
            "name": s, "state": ws.sheet_state, "dim": ws.dimensions,
            "rows": max_r, "cols": max_c, "nonempty_rows": nonempty_rows,
            "merged_ranges": len(merged), "data_start_row": data_start,
            "header_no_data_cols": header_no_data,
            "signal_text_cols": sig_cols,
            "signal_distinct": len(sig_values),
            "code_cells": code, "cjk_cells": cjk,
            "is_template_page": is_template,
        }
        stats["sheets"].append(info)

        print(f"--- {s}：{ws.dimensions}，非空行 {nonempty_rows}，"
              f"数据自第 {data_start or '?'} 行起，CJK {cjk} 格")
        if sig_cols:
            print(f"    [信号文本列] 第 {sig_cols} 列，去重 {len(sig_values)} 个→有效信号数约 {len(sig_values)}")
        if is_template:
            print(f"    [纯编码模板页] {code}/{total} 地址编码、无中文→对报价无用")
        if header_no_data:
            print(f"    [有表头无数据] 第 {header_no_data} 列→别报这部分活")

        dump_lines.append(f"===== {s} dim={ws.dimensions} rows={max_r} cols={max_c} =====")
        show = [(i, row) for i, row in enumerate(grid, start=1)
                if any(v != "" for v in row)]
        if len(show) <= 200:
            for i, row in show:
                dump_lines.append(f"{i:03d}: {' | '.join(row)}")
        else:
            for i, row in show[:30]:
                dump_lines.append(f"{i:04d}: {' | '.join(row)}")
            dump_lines.append("...（中间省略；如需逐行先找甲方要带功能文本的表）...")
            for i, row in show[-10:]:
                dump_lines.append(f"{i:04d}: {' | '.join(row)}")
        dump_lines.append("")

    mains = sorted(stats["sheets"], key=lambda x: x["cjk_cells"], reverse=True)
    if mains and mains[0]["cjk_cells"] > 0:
        print(f"主信号页：{mains[0]['name']}（CJK 最多，按此页估信号规模）")
    with open(os.path.join(args.outdir, "io_dump.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(dump_lines))
    with open(os.path.join(args.outdir, "io_stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"已写出：{args.outdir}/io_dump.txt + io_stats.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
