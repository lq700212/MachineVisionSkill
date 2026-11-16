#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
new_mockup.py —— 从模板生成一份 UI 设计稿工作台到项目的 Docs 目录。

为什么要有这个脚本
------------------
设计稿的骨架（5 套方案 Token / 三栏工作台 / 跳转图 / 总览 / 动效开关）每次手写
既慢又容易漏结构。本脚本把模板复制过去、替换项目名与 galaxy 路径，
AI 只需要往里面填"页面 / 弹窗 / 状态"，结构天然齐全。

用法
----
    # 在项目根目录执行（自动找 Docs/docs，没有就建 Docs）
    python new_mockup.py --project 视觉检测系统

    # 指定输出文件 / 项目根 / 标题
    python new_mockup.py --root E:\\Project\\HJVision --out Docs/ui_design_mockups.html

    # 已存在时覆盖（默认拒绝覆盖，防止冲掉人工改稿）
    python new_mockup.py --project 视觉检测系统 --force

输出
----
    {"ok": true, "path": "...", "size": 12345, "pages": 3, "dialogs": 2}
"""

import argparse
import io
import json
import os
import re
import sys
import time

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(SKILL_DIR, "templates", "mockup_base.html")
CONFIG_PATH = os.path.join(SKILL_DIR, "config.json")

DEFAULT_FILENAME = "ui_design_mockups.html"


def read_galaxy_path():
    """读缓存里的 galaxy 路径；没有就返回空串（设计稿里只作注释展示，不阻断生成）。"""
    if not os.path.isfile(CONFIG_PATH):
        return ""
    try:
        with io.open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return (json.load(f) or {}).get("galaxyPath", "") or ""
    except (ValueError, OSError):
        return ""


def pick_docs_dir(root):
    """
    选设计稿目录：已有 Docs 用 Docs；只有 docs 用 docs；都没有则新建 Docs。
    这样既尊重项目现有命名，又不强迫用户手动建目录。
    """
    for name in ("Docs", "docs", "DOCS"):
        p = os.path.join(root, name)
        if os.path.isdir(p):
            return p
    p = os.path.join(root, "Docs")
    os.makedirs(p, exist_ok=True)
    return p


def main():
    ap = argparse.ArgumentParser(description="生成 UI 设计稿工作台 HTML")
    ap.add_argument("--root", default=os.getcwd(), help="项目根目录（默认当前目录）")
    ap.add_argument("--out", help="输出文件路径（绝对路径或相对项目根）")
    ap.add_argument("--project", help="项目名（默认取根目录名）")
    ap.add_argument("--title", help="浏览器标题")
    ap.add_argument("--galaxy", help="galaxy 路径（默认读 config.json）")
    ap.add_argument("--stack", choices=["winforms", "wpf"], default="winforms",
                    help="目标技术栈（决定规范视图的落地映射以哪套为主，默认 winforms）")
    ap.add_argument("--force", action="store_true", help="已存在时覆盖")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(json.dumps({"ok": False, "error": "项目根目录不存在：" + root}, ensure_ascii=False))
        return 1
    if not os.path.isfile(TEMPLATE):
        print(json.dumps({"ok": False, "error": "模板缺失：" + TEMPLATE}, ensure_ascii=False))
        return 1

    if args.out:
        out = args.out if os.path.isabs(args.out) else os.path.join(root, args.out)
    else:
        out = os.path.join(pick_docs_dir(root), DEFAULT_FILENAME)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    if os.path.exists(out) and not args.force:
        print(json.dumps({
            "ok": False,
            "error": "目标已存在，未覆盖（确认要重写请加 --force）：" + out,
        }, ensure_ascii=False, indent=2))
        return 1

    project = args.project or os.path.basename(root.rstrip("\\/")) or "项目"
    title = args.title or (project + " · UI 设计稿工作台")
    galaxy = args.galaxy or read_galaxy_path() or "（未解析，先运行 resolve_galaxy.py）"

    with io.open(TEMPLATE, "r", encoding="utf-8") as f:
        html = f.read()

    # 占位符全部替换；模板里只允许这 4 个占位符，检查脚本会兜底查残留
    for k, v in {
        "{{PROJECT}}": project,
        "{{TITLE}}": title,
        "{{DATE}}": time.strftime("%Y-%m-%d"),
        "{{GALAXY}}": galaxy,
    }.items():
        html = html.replace(k, v)

    # 目标技术栈：模板默认值可能变，用正则替换首个 data-stack，保证幂等
    html = re.sub(r'data-stack="[^"]*"', 'data-stack="%s"' % args.stack, html, count=1)

    with io.open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)

    # 统计页面/弹窗数量，方便 AI 确认骨架生成成功
    body = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    pages = len(re.findall(r'<section\b[^>]*\bclass="[^"]*\bpage\b[^"]*"', body))
    dialogs = len(re.findall(r'<div\b[^>]*\bdata-dialog="', body))

    print(json.dumps({
        "ok": True,
        "path": out,
        "size": os.path.getsize(out),
        "pages": pages,
        "dialogs": dialogs,
        "stack": args.stack,
        "next": "编辑页面/弹窗后运行 check_mockup.py 核验，再用浏览器打开目检",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
