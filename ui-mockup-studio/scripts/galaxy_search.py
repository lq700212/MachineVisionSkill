#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
galaxy_search.py —— 在本地 galaxy 组件库里按关键词检索 UI 组件。

为什么要有这个脚本
------------------
galaxy 有 3800+ 个组件、12 个分类。直接 `ls` 只会看到
`作者_形容词_动物_数字.html` 这种毫无语义的文件名；真正有用的是文件里的
`/* From Uiverse.io by xxx - Tags: button, hover, glass, rounded */` 标签行。
本脚本只读每个文件的前 4KB 抽 tags，按关键词打分排序，一条命令给出候选清单，
避免 AI 在 3800 个文件里反复 grep / read 烧上下文。

用法
----
    # 概览：各分类组件数量
    python galaxy_search.py --list-categories

    # 检索：找"玻璃拟态卡片"
    python galaxy_search.py --category Cards --q glass card

    # 多关键词任一命中（OR 模式）
    python galaxy_search.py --q glass neon --any

    # 只要前 10 条，输出 JSON 供程序消费
    python galaxy_search.py --q toggle switch --limit 10 --json

    # 直接把某个组件的源码打出来（省一次 read 工具调用）
    python galaxy_search.py --show "Cards/0xnihilism_cold-tiger-22.html"

    # 随机抽样看风格（做"选型灵感"用）
    python galaxy_search.py --category Buttons --random 8

检索规则
--------
1. 关键词全部小写，逐个匹配 tags 与文件名；默认 AND（全部命中才算）。
2. 排序分：tags 命中数 * 3 + 文件名命中数，分高在前；同分按路径字典序。
3. 结果默认 20 条，可用 --limit 调整；0 表示不限。
"""

import argparse
import io
import json
import os
import random
import re
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_DIR, "config.json")
TAG_RE = re.compile(r"Tags:\s*(.+?)\s*\*/", re.IGNORECASE)
HEAD_BYTES = 4096


def load_galaxy_path(cli_path=None):
    """优先命令行 --galaxy，其次 config.json 缓存。路径无效直接报错提示先跑 resolve。"""
    if cli_path:
        return os.path.abspath(cli_path)
    if os.path.isfile(CONFIG_PATH):
        try:
            with io.open(CONFIG_PATH, "r", encoding="utf-8") as f:
                p = (json.load(f) or {}).get("galaxyPath")
            if p and os.path.isdir(p):
                return p
        except (ValueError, OSError):
            pass
    return None


def list_categories(root):
    """返回 [{"category": 名称, "count": 组件数}]，给 AI 一个全局概览。"""
    out = []
    for name in sorted(os.listdir(root)):
        sub = os.path.join(root, name)
        if not os.path.isdir(sub) or name.startswith("."):
            continue
        n = sum(1 for f in os.listdir(sub) if f.lower().endswith(".html"))
        if n:
            out.append({"category": name, "count": n})
    return out


def read_tags(path):
    """读文件头 4KB，抽 `Tags: a, b, c`。没有 tags 行就返回空串（老组件可能存在）。"""
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as f:
            head = f.read(HEAD_BYTES)
    except OSError:
        return ""
    m = TAG_RE.search(head)
    return (m.group(1).strip() if m else "")


def iter_components(root, category=None):
    """遍历分类目录下的 html 组件，逐个 yield (分类, 文件名, 绝对路径, tags)。"""
    cats = [category] if category else [
        n for n in sorted(os.listdir(root))
        if os.path.isdir(os.path.join(root, n)) and not n.startswith(".")
    ]
    for cat in cats:
        sub = os.path.join(root, cat)
        if not os.path.isdir(sub):
            continue
        for fn in sorted(os.listdir(sub)):
            if not fn.lower().endswith(".html"):
                continue
            full = os.path.join(sub, fn)
            yield cat, fn, full, read_tags(full)


def score(item, keywords, match_all):
    """打分：tags 命中权重 3，文件名命中权重 1。AND 模式下任一关键词缺失即 0 分。"""
    cat, fn, path, tags = item
    hay_tags = tags.lower()
    hay_name = fn.lower()
    hits = 0
    tag_hits = 0
    name_hits = 0
    for kw in keywords:
        in_tag = kw in hay_tags
        in_name = kw in hay_name
        if in_tag:
            tag_hits += 1
            hits += 1
        if in_name:
            name_hits += 1
            hits += 1
        if match_all and not (in_tag or in_name):
            return 0
    if match_all and hits == 0:
        return 0
    return tag_hits * 3 + name_hits


def main():
    ap = argparse.ArgumentParser(description="galaxy 组件检索")
    ap.add_argument("--galaxy", help="galaxy 根目录（默认读 config.json 缓存）")
    ap.add_argument("--category", help="只查某个分类，如 Cards")
    ap.add_argument("--q", nargs="*", default=[], help="关键词（空格分隔，默认 AND）")
    ap.add_argument("--any", action="store_true", help="OR 模式：任一关键词命中即可")
    ap.add_argument("--limit", type=int, default=20, help="返回条数，0=不限（默认 20）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--list-categories", action="store_true", help="只列出分类与数量")
    ap.add_argument("--random", type=int, default=0, metavar="N", help="随机抽 N 个组件看风格")
    ap.add_argument("--show", help="打印指定组件的完整源码，如 Cards/xxx.html")
    args = ap.parse_args()

    root = load_galaxy_path(args.galaxy)
    if not root:
        print(json.dumps({
            "ok": False,
            "error": "未找到 galaxy 路径。先运行：python resolve_galaxy.py",
        }, ensure_ascii=False, indent=2))
        return 1

    # --show：直接吐源码，路径做存在性与越界校验（防止 ../ 跑到库外）
    if args.show:
        target = os.path.abspath(os.path.join(root, args.show))
        if not target.startswith(os.path.abspath(root) + os.sep):
            print(json.dumps({"ok": False, "error": "路径越界：" + args.show}, ensure_ascii=False))
            return 1
        if not os.path.isfile(target):
            print(json.dumps({"ok": False, "error": "组件不存在：" + target}, ensure_ascii=False))
            return 1
        with io.open(target, "r", encoding="utf-8", errors="replace") as f:
            sys.stdout.write(f.read())
        return 0

    # --list-categories：全局概览
    if args.list_categories:
        cats = list_categories(root)
        if args.json:
            print(json.dumps({"ok": True, "galaxy": root, "categories": cats}, ensure_ascii=False, indent=2))
        else:
            print("galaxy: " + root)
            for c in cats:
                print("  %-18s %5d" % (c["category"], c["count"]))
        return 0

    keywords = [k.lower() for k in args.q if k.strip()]

    # --random：随机抽样（不做关键词过滤，纯粹找灵感）
    if args.random > 0:
        pool = list(iter_components(root, args.category))
        picked = random.sample(pool, min(args.random, len(pool)))
        rows = [{"category": c, "file": f, "path": p, "tags": t} for c, f, p, t in picked]
        if args.json:
            print(json.dumps({"ok": True, "items": rows}, ensure_ascii=False, indent=2))
        else:
            for r in rows:
                print("[%s] %s\n  tags: %s\n  %s" % (r["category"], r["file"], r["tags"] or "-", r["path"]))
        return 0

    if not keywords:
        print(json.dumps({
            "ok": False,
            "error": "缺少检索词。用法示例：--q glass card --category Cards；或先 --list-categories",
        }, ensure_ascii=False, indent=2))
        return 1

    scored = []
    for item in iter_components(root, args.category):
        s = score(item, keywords, match_all=not args.any)
        if s > 0:
            scored.append((s, item))
    # 分值降序；同分按 分类/文件名 升序，保证结果稳定可复现
    scored.sort(key=lambda x: (-x[0], x[1][0], x[1][1]))
    if args.limit and args.limit > 0:
        scored = scored[:args.limit]

    rows = [{
        "score": s,
        "category": c,
        "file": f,
        "path": p,
        "tags": t,
    } for s, (c, f, p, t) in scored]

    if args.json:
        print(json.dumps({"ok": True, "galaxy": root, "count": len(rows), "items": rows}, ensure_ascii=False, indent=2))
    else:
        if not rows:
            print("无匹配。建议：换更通用的词（button/card/input/loader/toggle/notification），或用 --any。")
            return 0
        for r in rows:
            print("[%s] %s  (score %d)" % (r["category"], r["file"], r["score"]))
            print("  tags: " + (r["tags"] or "-"))
            print("  " + r["path"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
