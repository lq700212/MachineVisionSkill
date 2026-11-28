# -*- coding: utf-8 -*-
"""make_charts：按 project.json 的 charts 配置批量生成图表。

支持 4 种类型：
  architecture  三列架构图（左设备 / 中上位机 / 右服务器）
  workload      分组条形图（传统 vs AI / 方案 A vs B）
  timeline      甘特图（任务 + 里程碑）
  risk_matrix   风险矩阵气泡图（概率 × 影响）
  scenario      场景概率条形图（场景 + 概率 + 工作量）

用法：python make_charts.py --config project.json
"""
import argparse
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import FancyBboxPatch
from datetime import datetime, timedelta

plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "PingFang SC", "Arial Unicode MS"
]
plt.rcParams["axes.unicode_minus"] = False

DEFAULT_COLORS = ["#4C78A8", "#F58518", "#E45756", "#54A24B", "#8E6BB8", "#9AA7B8"]


def save(fig, out):
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    fig.savefig(out, bbox_inches="tight", facecolor="white", dpi=150)
    plt.close(fig)
    print(f"  [OK] {out}")


def chart_architecture(cfg, out):
    nodes = cfg.get("left_nodes") or []
    n = len(nodes)
    fig_h = max(5.0, 1.1 + n * 0.9)
    fig, ax = plt.subplots(figsize=(12, fig_h), dpi=150)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, fig_h)
    ax.axis("off")
    bus_x = 3.25

    def rbox(x, y, w, h, fc, ec):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
                                    boxstyle="round,pad=0.02,rounding_size=0.12",
                                    linewidth=1.4, edgecolor=ec, facecolor=fc))

    def link_label(x, y, text):
        if not text:
            return
        # 长标签自动按 " / " 折行，避免压住连接线和设备框
        if len(text) > 13 and " / " in text:
            parts = text.split(" / ")
            lines, cur = [], ""
            for p in parts:
                cand = f"{cur} / {p}" if cur else p
                if len(cand) <= 13:
                    cur = cand
                else:
                    if cur:
                        lines.append(cur)
                    cur = p
            if cur:
                lines.append(cur)
            text = "\n".join(lines)
        ax.text(x, y, text, ha="center", va="bottom", fontsize=8, color="#555", zorder=6)

    top = fig_h - 1.0
    gap = 0.9
    ys = [top - i * gap for i in range(n)]
    for node, y in zip(nodes, ys):
        color = node.get("color", "#2E6FBF")
        fc = node.get("fill", "#E8F1FB")
        rbox(0.4, y, 2.7, 0.62, fc, color)
        ax.text(1.75, y + 0.31, node.get("label", ""), ha="center", va="center", fontsize=9)
        ax.plot([3.1, bus_x], [y + 0.31, y + 0.31], color="#888", lw=1.2)

    if n:
        ax.plot([bus_x, bus_x], [ys[-1] + 0.31, ys[0] + 0.31], color="#888", lw=1.2)
        mid_y = (ys[0] + ys[-1]) / 2 + 0.31
    else:
        mid_y = fig_h / 2

    center = cfg.get("center") or {}
    cx, cy, cw, ch = 4.25, mid_y - 1.4, 3.2, 2.8
    rbox(cx, cy, cw, ch, center.get("fill", "#EAF6EA"), center.get("color", "#3A8F3A"))
    ax.text(cx + cw / 2, cy + ch - 0.55, center.get("title", ""), ha="center",
            fontsize=13, fontweight="bold")
    if center.get("subtitle"):
        ax.text(cx + cw / 2, cy + ch - 1.05, center["subtitle"], ha="center",
                fontsize=11, color="#333")
    for i, line in enumerate(center.get("lines") or []):
        ax.text(cx + cw / 2, cy + ch - 1.55 - i * 0.42, line, ha="center",
                fontsize=10, color="#555")

    ax.annotate("", xy=(cx, mid_y), xytext=(bus_x, mid_y),
                arrowprops=dict(arrowstyle="-|>", color="#555", lw=1.8))
    link_label((bus_x + cx) / 2, mid_y + 0.16, cfg.get("link_left"))

    right = cfg.get("right") or {}
    rx, ry, rw, rh = 9.0, mid_y - 0.65, 2.6, 1.3
    rbox(rx, ry, rw, rh, right.get("fill", "#FDF0E3"), right.get("color", "#C97A1E"))
    ax.text(rx + rw / 2, ry + rh - 0.45, right.get("title", ""), ha="center",
            fontsize=12, fontweight="bold")
    for i, line in enumerate(right.get("lines") or []):
        ax.text(rx + rw / 2, ry + rh - 0.85 - i * 0.3, line, ha="center",
                fontsize=9, color="#555")

    ax.annotate("", xy=(rx, mid_y), xytext=(cx + cw, mid_y),
                arrowprops=dict(arrowstyle="-|>", color="#555", lw=1.8))
    link_label((cx + cw + rx) / 2, mid_y + 0.16, cfg.get("link_right"))

    for i, line in enumerate(cfg.get("footer") or []):
        ax.text(0.4, 0.55 - i * 0.3, line, fontsize=9, color="#666")

    plt.tight_layout()
    save(fig, out)


def chart_workload(cfg, out):
    items = cfg.get("items") or []
    series = cfg.get("series") or ["传统", "AI 辅助"]
    n = len(items)
    fig, ax = plt.subplots(figsize=(10, max(4.0, 1.6 + n * 0.55)), dpi=150)
    h = 0.36
    ys = list(range(n))
    for si, sname in enumerate(series):
        vals = [it["values"][si] if si < len(it.get("values", [])) else 0 for it in items]
        offset = (si - (len(series) - 1) / 2) * h
        bars = ax.barh([y + offset for y in ys], vals, height=h,
                       color=DEFAULT_COLORS[si % len(DEFAULT_COLORS)], label=sname)
        for bar in bars:
            w = bar.get_width()
            ax.text(w + 0.06, bar.get_y() + bar.get_height() / 2, f"{w:g}",
                    va="center", fontsize=9, color="#333")
    ax.set_yticks(ys)
    ax.set_yticklabels([it.get("name", "") for it in items], fontsize=10)
    ax.set_xlabel(cfg.get("unit", "人天"), fontsize=10)
    ax.set_title(cfg.get("title", "工作量对比"), fontsize=13, fontweight="bold", pad=12)
    ax.legend(loc="lower right", frameon=False, fontsize=10)
    maxv = max((max(it.get("values") or [0]) for it in items), default=1)
    ax.set_xlim(0, maxv * 1.18)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    plt.tight_layout()
    save(fig, out)


def chart_timeline(cfg, out):
    tasks = cfg.get("tasks") or []
    fig, ax = plt.subplots(figsize=(11, max(3.5, 1.6 + len(tasks) * 0.55)), dpi=150)
    for i, t in enumerate(tasks):
        s = datetime.strptime(t["start"], "%Y-%m-%d")
        e = datetime.strptime(t["end"], "%Y-%m-%d")
        color = t.get("color", DEFAULT_COLORS[i % len(DEFAULT_COLORS)])
        ax.barh(i, max((e - s).days, 1), left=s, height=0.5, color=color, alpha=0.88)
        ax.text(s, i + 0.36, t.get("name", ""), fontsize=9, color="#333", va="bottom")

    for m in cfg.get("milestones") or []:
        dt = datetime.strptime(m["date"], "%Y-%m-%d")
        color = m.get("color", "#C0392B")
        ax.axvline(dt, color=color, linestyle="--", lw=1.2, alpha=0.8)
        ax.text(dt, len(tasks) - 0.15, m.get("label", ""), fontsize=8, color=color,
                ha="center", va="bottom")

    ax.set_yticks([])
    ax.set_ylim(-0.6, max(len(tasks) - 0.1, 1))
    starts = [datetime.strptime(t["start"], "%Y-%m-%d") for t in tasks]
    ends = [datetime.strptime(t["end"], "%Y-%m-%d") for t in tasks]
    if starts and ends:
        ax.set_xlim(min(starts) - timedelta(days=1), max(ends) + timedelta(days=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
    ax.set_title(cfg.get("title", "排期"), fontsize=13, fontweight="bold", pad=12)
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    plt.xticks(fontsize=9)
    plt.tight_layout()
    save(fig, out)


def chart_risk_matrix(cfg, out):
    risks = cfg.get("risks") or []
    fig, ax = plt.subplots(figsize=(8.5, 6.5), dpi=150)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axhline(0.5, color="#bbb", lw=0.8, linestyle="--")
    ax.axvline(0.5, color="#bbb", lw=0.8, linestyle="--")
    quadrants = [
        (0.02, 0.98, "低概率 / 高影响", "left", "top"),
        (0.98, 0.98, "高概率 / 高影响", "right", "top"),
        (0.02, 0.02, "低概率 / 低影响", "left", "bottom"),
        (0.98, 0.02, "高概率 / 低影响", "right", "bottom"),
    ]
    for qx, qy, label, ha, va in quadrants:
        ax.text(qx, qy, label, ha=ha, va=va, fontsize=8, color="#aaa")
    for i, r in enumerate(risks):
        p = float(r.get("probability", 0.5))
        im = float(r.get("impact", 0.5))
        color = r.get("color", DEFAULT_COLORS[i % len(DEFAULT_COLORS)])
        ax.scatter(p, im, s=320, color=color, alpha=0.75, edgecolors="white", linewidths=1.5)
        # 靠右的点标签放左侧，靠上的点标签下移，避免压住象限文字
        dx, dy, ha = 10, 6, "left"
        if p > 0.55:
            dx, ha = -10, "right"
        if im > 0.9:
            dy = -14
        ax.annotate(r.get("name", ""), (p, im), textcoords="offset points",
                    xytext=(dx, dy), ha=ha, va="center", fontsize=9, color="#333")
    ax.set_xlabel("发生概率 →", fontsize=10)
    ax.set_ylabel("影响程度 →", fontsize=10)
    ax.set_title(cfg.get("title", "风险矩阵"), fontsize=13, fontweight="bold", pad=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    save(fig, out)


def chart_scenario(cfg, out):
    items = cfg.get("items") or []
    fig, ax = plt.subplots(figsize=(10, max(3.5, 1.4 + len(items) * 0.6)), dpi=150)
    names = [it.get("name", "") for it in items]
    probs = [float(it.get("probability", 0)) for it in items]
    colors = [it.get("color", DEFAULT_COLORS[i % len(DEFAULT_COLORS)]) for i, it in enumerate(items)]
    bars = ax.barh(names, probs, color=colors, alpha=0.85, height=0.55)
    for bar, it in zip(bars, items):
        w = bar.get_width()
        extra = it.get("effort", "")
        label = f"{w*100:.0f}%" + (f"  ·  {extra}" if extra else "")
        ax.text(w + 0.01, bar.get_y() + bar.get_height() / 2, label,
                va="center", fontsize=9, color="#333")
    ax.set_xlim(0, 1.15)
    ax.set_xlabel("概率", fontsize=10)
    ax.set_title(cfg.get("title", "可行性分场景"), fontsize=13, fontweight="bold", pad=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    plt.tight_layout()
    save(fig, out)


CHART_FUNCS = {
    "architecture": chart_architecture,
    "workload": chart_workload,
    "timeline": chart_timeline,
    "risk_matrix": chart_risk_matrix,
    "scenario": chart_scenario,
}


def main():
    ap = argparse.ArgumentParser(description="按 project.json 批量生成图表")
    ap.add_argument("--config", default="project.json", help="project.json 路径")
    ap.add_argument("--only", default="", help="只生成指定 type")
    args = ap.parse_args()

    cfg_path = os.path.abspath(args.config)
    if not os.path.exists(cfg_path):
        print(f"[FAIL] 配置不存在：{cfg_path}")
        return 1
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)

    base_dir = os.path.dirname(cfg_path)
    charts = cfg.get("charts") or []
    if not charts:
        print("[WARN] project.json 里没有 charts 配置")
        return 2

    ok = 0
    for c in charts:
        ctype = c.get("type")
        if args.only and ctype != args.only:
            continue
        func = CHART_FUNCS.get(ctype)
        if not func:
            print(f"  [SKIP] 未知类型：{ctype}")
            continue
        out = c.get("out", f"assets/{ctype}.png")
        if not os.path.isabs(out):
            out = os.path.join(base_dir, out)
        print(f"[CHART] {ctype} -> {out}")
        try:
            func(c, out)
            ok += 1
        except Exception as e:
            print(f"  [FAIL] {ctype}: {e}")

    print(f"[DONE] {ok}/{len(charts)} 张生成成功")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
