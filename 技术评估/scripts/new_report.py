# -*- coding: utf-8 -*-
"""new_report：按 project.json 生成评估文档骨架。

用法：
  python new_report.py --config project.json
  python new_report.py --config project.json --out report/xxx.md --force

产出：
  report/<项目名>_内部技术评估_<YYYYMMDD>.md

骨架里的章节和提示注释都保留，AI 只需往对应位置填内容。
"""

import argparse
import json
import os
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(SKILL_DIR, "templates", "report_template.md")

INVALID = '\\/:*?"<>|'


def safe_name(s):
    for ch in INVALID:
        s = s.replace(ch, "_")
    return s.strip() or "未命名项目"


def main():
    ap = argparse.ArgumentParser(description="生成内部技术评估文档骨架")
    ap.add_argument("--config", default="project.json", help="project.json 路径")
    ap.add_argument("--out", default="", help="输出路径，默认 report/<项目名>_内部技术评估_<日期>.md")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的文档")
    args = ap.parse_args()

    cfg_path = os.path.abspath(args.config)
    if not os.path.exists(cfg_path):
        print(f"[FAIL] 配置不存在：{cfg_path}")
        return 1
    if not os.path.exists(TEMPLATE):
        print(f"[FAIL] 模板不存在：{TEMPLATE}")
        return 1

    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    proj = cfg.get("project") or {}

    name = proj.get("name") or "未命名项目"
    date = proj.get("date") or "2026-01-01"
    repl = {
        "{{PROJECT_NAME}}": name,
        "{{DATE}}": date,
        "{{TYPE}}": proj.get("type") or "工业软件 / 上位机",
        "{{CLIENT}}": proj.get("client") or "待确认",
        "{{DEADLINE}}": proj.get("deadline") or "待确认",
    }

    with open(TEMPLATE, encoding="utf-8") as f:
        text = f.read()
    for k, v in repl.items():
        text = text.replace(k, str(v))

    base_dir = os.path.dirname(cfg_path)
    if args.out:
        out = args.out if os.path.isabs(args.out) else os.path.join(base_dir, args.out)
    else:
        fname = f"{safe_name(name)}_内部技术评估_{date.replace('-', '')}.md"
        out = os.path.join(base_dir, "report", fname)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out) and not args.force:
        print(f"[SKIP] 已存在：{out}（--force 覆盖）")
        return 0

    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    print(f"[OK] 文档骨架：{out}")
    print("下一步：")
    print("  1) 先读 templates/example_report.md，照它的密度和句式写")
    print("  2) 按模板注释逐节填写，禁止留空、禁止写“待定/需进一步确认”")
    print("  3) 图片统一用相对路径 assets/xxx.png")
    print(f"  4) python verify_report.py \"{out}\" --config \"{cfg_path}\" --strict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
