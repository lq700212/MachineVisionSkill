# -*- coding: utf-8 -*-
"""init_project：初始化技术评估工作目录。

用法：
  python init_project.py "E:\\项目\\评估" --name "RFID 过账项目" --date 2026-11-28
  python init_project.py . --name "某视觉项目" --type "机器视觉"

产出：
  <dir>/project.json          评估配置（图片裁剪、图表数据、文档元信息）
  <dir>/assets/raw/           原始截图
  <dir>/assets/               标注图与图表
  <dir>/report/               评估文档
"""
import argparse
import json
import os
import shutil
import sys
from datetime import date

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(SKILL_DIR, "templates", "project.example.json")


def main():
    ap = argparse.ArgumentParser(description="初始化技术评估工作目录")
    ap.add_argument("target", help="项目工作目录")
    ap.add_argument("--name", required=True, help="项目名称")
    ap.add_argument("--date", default=date.today().isoformat(), help="评估日期 YYYY-MM-DD")
    ap.add_argument("--type", default="工业上位机", help="项目类型，如 工业上位机/机器视觉/嵌入式/软件集成")
    ap.add_argument("--client", default="", help="客户/现场（可空）")
    ap.add_argument("--deadline", default="", help="交付截止日（可空）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的 project.json")
    args = ap.parse_args()

    root = os.path.abspath(args.target)
    os.makedirs(os.path.join(root, "assets", "raw"), exist_ok=True)
    os.makedirs(os.path.join(root, "report"), exist_ok=True)

    cfg_path = os.path.join(root, "project.json")
    if os.path.exists(cfg_path) and not args.force:
        print(f"[SKIP] {cfg_path} 已存在（--force 覆盖）")
    else:
        if not os.path.exists(TEMPLATE):
            print(f"[FAIL] 模板不存在：{TEMPLATE}")
            return 1
        with open(TEMPLATE, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["project"]["name"] = args.name
        cfg["project"]["date"] = args.date
        cfg["project"]["type"] = args.type
        cfg["project"]["client"] = args.client
        cfg["project"]["deadline"] = args.deadline
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print(f"[OK] 配置：{cfg_path}")

    print(f"[OK] 目录：{root}")
    print("下一步：")
    print("  1) 原始截图放 assets/raw/，或跑 extract_images.py 从会话提取")
    print("  2) 编辑 project.json 的 images / charts")
    print("  3) python crop_annotate.py --config project.json")
    print("  4) python make_charts.py --config project.json")
    print("  5) 按 templates/report_template.md 写文档到 report/")
    print("  6) python verify_report.py report/xxx.md --config project.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
