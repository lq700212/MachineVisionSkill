# -*- coding: utf-8 -*-
"""quote_calc：报价阶梯计算器。输入对内数字，输出对外阶梯 + 毛利表。

公式（本 skill 唯一口径，弱模型不许自创）：
  对内成本低  = dev_min*day_cost + site_min*day_cost + travel_min + overhead
  对内成本高  = dev_max*day_cost + site_max*day_cost + travel_max + overhead
  对外合计    = sum(分项 A/B/C/D/E…)
  锚价        = 对外合计（先报这个）
  让步价      = 对外合计 - give（给客户砍一刀的成交甜点）
  底线        = floor（破了不签，经理拍板）
  毛利        = 报价 - 对内成本高（按悲观成本算，诚实）

用法示例：
  python quote_calc.py --dev 8-10 --site 3-5 --day-cost 1300 ^
    --travel 3000-6000 --overhead 5000 ^
    --parts A:48000,B:52000,C:12000,D:10000,E:6000 ^
    --give 10000 --floor 105000
输出 markdown 表（贴进报价文档 §4/§5）。
"""
import argparse
import sys


def parse_range(s):
    if "-" in s:
        a, b = s.split("-", 1)
        return float(a), float(b)
    return float(s), float(s)


def parse_parts(s):
    parts = []
    for item in s.split(","):
        item = item.strip()
        if not item:
            continue
        k, v = item.split(":", 1)
        parts.append((k.strip(), float(v.strip())))
    return parts


def fmt(x):
    if x >= 10000:
        return f"{x / 10000:.2f}万"
    return f"{x:.0f}元"


def main():
    ap = argparse.ArgumentParser(description="报价阶梯计算器")
    ap.add_argument("--dev", required=True, help="代码人天区间，如 8-10")
    ap.add_argument("--site", required=True, help="现场天数区间，如 3-5")
    ap.add_argument("--day-cost", type=float, required=True, help="综合日成本，如 1300")
    ap.add_argument("--travel", required=True, help="差旅区间，如 3000-6000")
    ap.add_argument("--overhead", type=float, default=0, help="分摊，如 5000")
    ap.add_argument("--parts", required=True, help="对外分项，如 A:48000,B:52000,C:12000")
    ap.add_argument("--give", type=float, default=0, help="让步池（锚价-让步价）")
    ap.add_argument("--floor", type=float, required=True, help="底线（破了不签）")
    args = ap.parse_args()

    dev_min, dev_max = parse_range(args.dev)
    site_min, site_max = parse_range(args.site)
    tr_min, tr_max = parse_range(args.travel)
    parts = parse_parts(args.parts)

    cost_low = dev_min * args.day_cost + site_min * args.day_cost + tr_min + args.overhead
    cost_high = dev_max * args.day_cost + site_max * args.day_cost + tr_max + args.overhead
    total = sum(v for _, v in parts)
    anchor, sweet, floor = total, total - args.give, args.floor

    out = []
    out.append("| 口径 | 金额 | 毛利(按悲观成本) | 说明 |")
    out.append("|---|---|---|---|")
    out.append(f"| 对内成本 | {fmt(cost_low)}~{fmt(cost_high)} | - | 代码{args.dev}天+现场{args.site}天，日成本{args.day_cost:.0f}，差旅{args.travel}，分摊{args.overhead:.0f} |")
    out.append(f"| 锚价(先报) | {fmt(anchor)} | {fmt(anchor - cost_high)} | 分项合计：" + "、".join(f"{k}{fmt(v)}" for k, v in parts) + " |")
    out.append(f"| 让步价(甜点) | {fmt(sweet)} | {fmt(sweet - cost_high)} | 给客户砍一刀，奔这个成交 |")
    out.append(f"| 底线(不破) | {fmt(floor)} | {fmt(floor - cost_high)} | 破了不签，经理拍板 |")
    if floor < cost_high:
        out.append("")
        out.append(f"⚠ 底线 {fmt(floor)} 已低于悲观成本 {fmt(cost_high)}：亏本线，floor 必须上调。")
    if sweet > anchor:
        out.append("")
        out.append("⚠ 让步价高于锚价：give 填错了。")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
