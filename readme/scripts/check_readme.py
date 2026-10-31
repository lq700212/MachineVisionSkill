# -*- coding: utf-8 -*-
"""
check_readme.py — README 卫生核验（readme skill · 第 5 步脚本）

干什么：对仓库 README.md（或 --file 指定 md）跑八项体检，全 PASS 才算完：
  1. UTF-8 可解码（GBK 落盘必乱码——遇错直接 NG）
  2. H1 标题存在
  3. 头部 hero/徽章行存在（<div align="center"> 或 shields.io 徽章——WARN 级提醒）
  4. 图片相对路径全部落盘（相对 md 所在目录解析；外链 http(s) 跳过）
  5. 文中相对链接 [text](x.md) 目标存在（#anchor 开头/外链跳过；xxx.md#anchor 只验文件）
  6. mermaid 代码块非空且首行语法头合法（graph/flowchart/…，GitHub 原生渲染集）
  7. ``` 围栏代码块成对闭合（奇偶配对）
  8. 空链接 [text]() 拦截

用法：
    python check_readme.py [repo根]                # 默认 README.md
    python check_readme.py . --file docs/xx.md     # 检查指定 md

退出码：0=全 PASS；1=有 NG；2=环境错误。
结论行统一 [RESULT: OK] / [RESULT: NG]。
"""
import os
import re
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

IMG_RX = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
LINK_RX = re.compile(r"\[[^\]]+\]\(([^)]*)\)")
MERMAID_OK = re.compile(
    r"^(graph\s+(LR|TD|RL|BT)|flowchart\s+(TD|LR|RL|BT)|sequenceDiagram|classDiagram"
    r"|stateDiagram(?:-v2)?|erDiagram|gantt|pie|mindmap|timeline|gitGraph)", re.I)

NAGS = []   # (级别, 消息)  level: NG / WARN / INFO


def nail(level, msg):
    NAGS.append((level, msg))


def resolve(base, ref):
    if ref.startswith(("http://", "https://", "mailto:", "#")):
        return None
    return os.path.normpath(os.path.join(base, ref.split("#", 1)[0]))


def main():
    argv = sys.argv[1:]
    repo = os.path.abspath(argv[0] if argv and not argv[0].startswith("-") else ".")
    rest = argv[1:] if argv and not argv[0].startswith("-") else argv
    target = os.path.join(repo, "README.md")
    if "--file" in rest:
        i = rest.index("--file")
        if i + 1 < len(rest):
            target = os.path.abspath(os.path.join(repo, rest[i + 1]))
    if not os.path.isfile(target):
        nail("NG", f"目标文件不存在: {target}")
    else:
        try:
            text = open(target, "r", encoding="utf-8-sig", errors="strict").read()
        except UnicodeDecodeError:
            nail("NG", "文件不是 UTF-8 可解码（Windows 记事本 GBK 落盘必刺）")
            text = ""

    base = os.path.dirname(target)
    relname = os.path.relpath(target, repo)

    if text:
        # 1) H1
        if not re.search(r"^#\s+.+", text.lstrip("\ufeff").lstrip(), re.M):
            nail("NG", "缺 H1（'# ' 开头标题）")

        # 2) hero/徽章（首 30 行）
        head = "\n".join(text.splitlines()[:30])
        has_badge = ("shields.io" in head) or ('<div align="center">' in head)
        if not has_badge:
            nail("WARN", "头部 30 行未见徽章行（shields.io / 居中 div）——技术栈徽章建议补上")

        # 4) 图片落盘
        for m in IMG_RX.finditer(text):
            r = resolve(base, m.group(1).strip())
            if r is None:
                continue
            if not os.path.isfile(r):
                nail("NG", f"图片不存在: {m.group(1).strip()}（引用于 {relname}）")

        # 5) 相对链接目标存在 + 8) 空链接
        for m in LINK_RX.finditer(text):
            ref = m.group(1).strip()
            if ref == "":
                nail("NG", f"空链接 [text]()（{relname}）")
                continue
            r = resolve(base, ref)
            if r is None:
                continue
            if not os.path.exists(r):
                nail("NG", f"链接目标不存在: {ref}")

        # 6) mermaid 块 + 7) 围栏配对
        fences = re.findall(r"^```(\w*)[^\n]*\n(.*?)^```", text, re.M | re.S)
        fenced = re.findall(r"^\s*```", text, re.M)
        if len(fenced) % 2 != 0:
            nail("NG", "``` 围栏不成对（奇数个——有未闭合代码块）")
        orm = 0
        for lang, body in fences:
            if lang.lower() == "mermaid":
                body_stripped = body.strip()
                if not body_stripped:
                    nail("NG", "空 mermaid 块")
                else:
                    first = body_stripped.splitlines()[0].strip()
                    if not MERMAID_OK.match(first):
                        nail("NG", f"mermaid 语法头可疑: {first!r}（GitHub 只渲染原生集）")
                orm += 1
        if orm == 0:
            nail("WARN", "无 mermaid 架构图（推荐补一节架构图）")

    # ---- 结论 ----
    n_n, n_w = 0, 0
    for lvl, msg in NAGS:
        print(f"[{lvl}] {msg}")
        if lvl == "NG":
            n_n += 1
        else:
            n_w += 1
    print(f"\n检查: NG={n_n} WARN={n_w}")
    print("RESULT: OK" if n_n == 0 else "RESULT: NG")
    return 0 if n_n == 0 else 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception as ex:
        print(f"[ERR] {ex}")
        print("RESULT: NG")
        code = 2
    sys.exit(code)
