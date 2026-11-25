# -*- coding: utf-8 -*-
"""
check_readme.py — README 卫生核验（readme skill · 第 5 步脚本）

干什么：对仓库 README.md（或 --file 指定 md）跑十项体检，全 PASS 才算完：
  1. UTF-8 可解码（GBK 落盘必乱码——遇错直接 NG）
  2. H1 标题存在
  3. 头部 hero/徽章行存在（<div align="center"> 或 shields.io 徽章——WARN 级提醒）
  4. 图片相对路径全部落盘（相对 md 所在目录解析；外链 http(s) 跳过）
  5. 文中相对链接 [text](x.md) 目标存在（#anchor 开头/外链跳过；xxx.md#anchor 只验文件）
  6. mermaid 代码块非空且首行语法头合法（graph/flowchart/…，GitHub 原生渲染集）
  7. ``` 围栏代码块成对闭合（奇偶配对）
  8. 空链接 [text]() 拦截
  9. 多端分节：--ends 里每个端在 README 有对应 H2/H3 小节（V1.3.0）
 10. 多端图墙：--ends 里每个端至少 1 张该端图片（V1.3.0）

多端图片归属判定（任一命中即算该端）：
  a. 路径在 docs/images/<end>/ 或 images/<end>/ 下；
  b. 文件名前缀为 <end>_ / <end>- / m_（mobile）/ d_（desktop）；
  c. 图片出现在标题含该端关键词的 H2~H4 小节内。

用法：
    python check_readme.py [repo根]                       # 默认 README.md
    python check_readme.py . --file docs/xx.md            # 检查指定 md
    python check_readme.py . --ends desktop,mobile        # 多端项目：缺一端即 NG
    python check_readme.py . --ends desktop,mobile,web

    --ends 不传时自动探测端：探测到 >=2 个端启用分端检查，但降为 WARN
    （避免把故意不展示的端误判为 NG）；确认端清单后应显式传 --ends 锁成 NG。

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
IMG_HTML_RX = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)
LINK_RX = re.compile(r"\[[^\]]+\]\(([^)]*)\)")
HEAD_RX = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
MERMAID_OK = re.compile(
    r"^(graph\s+(LR|TD|RL|BT)|flowchart\s+(TD|LR|RL|BT)|sequenceDiagram|classDiagram"
    r"|stateDiagram(?:-v2)?|erDiagram|gantt|pie|mindmap|timeline|gitGraph)", re.I)

# 端定义：标题关键词 / 图片目录 / 图片文件名前缀
END_RULES = {
    "desktop": {
        "label": "桌面端",
        "title_kw": ("桌面", "windows", "desktop", "wpf", "winforms"),
        "img_dirs": ("docs/images/desktop", "images/desktop"),
        "img_prefix": ("desktop_", "desktop-", "d_"),
    },
    "mobile": {
        "label": "手机端",
        "title_kw": ("手机", "移动", "android", "ios", "flutter", "现场端", "mobile"),
        "img_dirs": ("docs/images/mobile", "images/mobile"),
        "img_prefix": ("mobile_", "mobile-", "m_"),
    },
    "web": {
        "label": "Web 端",
        "title_kw": ("web", "前端", "浏览器", "网页"),
        "img_dirs": ("docs/images/web", "images/web"),
        "img_prefix": ("web_", "web-", "frontend_"),
    },
    "server": {
        "label": "服务端",
        "title_kw": ("服务端", "后端", "api", "server", "backend"),
        "img_dirs": ("docs/images/server", "images/server"),
        "img_prefix": ("server_", "server-", "backend_", "api_"),
    },
}

NAGS = []   # (级别, 消息)  level: NG / WARN / INFO


def nail(level, msg):
    NAGS.append((level, msg))


def resolve(base, ref):
    if ref.startswith(("http://", "https://", "mailto:", "#")):
        return None
    return os.path.normpath(os.path.join(base, ref.split("#", 1)[0]))


def parse_args(argv):
    """[repo根] + --file <md> + --ends a,b,c（均支持 --key=value）。"""
    repo, file, ends = ".", None, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--file" and i + 1 < len(argv):
            file = argv[i + 1]
            i += 2
        elif a.startswith("--file="):
            file = a.split("=", 1)[1]
            i += 1
        elif a == "--ends" and i + 1 < len(argv):
            ends = [x.strip().lower() for x in argv[i + 1].split(",") if x.strip()]
            i += 2
        elif a.startswith("--ends="):
            ends = [x.strip().lower() for x in a.split("=", 1)[1].split(",") if x.strip()]
            i += 1
        elif not a.startswith("-") and repo == ".":
            repo = a
            i += 1
        else:  # 未知参数不崩
            i += 1
    return repo, file, ends


def detect_ends(repo):
    """自动探测端：只认工程文件/目录名的硬信号，避免文档目录误判。"""
    ends = set()

    def entries_of(path):
        try:
            return {n.lower() for n in os.listdir(path)}
        except OSError:
            return set()

    root = entries_of(repo)
    if "pubspec.yaml" in root:
        ends.add("mobile")
    if any(n.endswith((".sln", ".csproj")) for n in root):
        ends.add("desktop")

    for name in sorted(os.listdir(repo)):
        p = os.path.join(repo, name)
        if not os.path.isdir(p):
            continue
        low = name.lower()
        sub = entries_of(p)
        if "pubspec.yaml" in sub or low in ("mobile", "android", "ios"):
            ends.add("mobile")
        if low in ("desktop", "windows", "wpf", "gui") or any(
                n.endswith((".sln", ".csproj")) for n in sub):
            ends.add("desktop")
        if low in ("web", "frontend", "client", "site") and (
                "index.html" in sub or "package.json" in sub):
            ends.add("web")
        if low in ("server", "backend", "api", "service") and (
                sub & {"go.mod", "pyproject.toml", "package.json", "requirements.txt"}):
            ends.add("server")
    return sorted(ends)


def split_sections(text):
    """返回 [(起始行, 级别, 标题, 结束行)]；结束行 = 下一个同级或更高级标题。"""
    lines = text.splitlines()
    heads = []
    for i, line in enumerate(lines, 1):
        m = HEAD_RX.match(line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    secs = []
    for idx, (ln, lv, title) in enumerate(heads):
        end = len(lines) + 1
        for ln2, lv2, _ in heads[idx + 1:]:
            if lv2 <= lv:
                end = ln2
                break
        secs.append((ln, lv, title, end))
    return secs


def image_refs(text):
    """[(行号, 引用原文)]，同时收 Markdown 图片与 HTML <img src>。"""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in IMG_RX.finditer(line):
            out.append((i, m.group(1).strip()))
        for m in IMG_HTML_RX.finditer(line):
            out.append((i, m.group(1).strip()))
    return out


def classify_image(repo, base, ref):
    """按路径/文件名判定图片属于哪个端；判不出返回 None。"""
    abs_path = os.path.normpath(os.path.join(base, ref.split("#", 1)[0]))
    rel = os.path.relpath(abs_path, repo).replace("\\", "/").lower()
    for end, rule in END_RULES.items():
        for d in rule["img_dirs"]:
            if rel.startswith(d.lower() + "/"):
                return end
    fname = os.path.basename(rel)
    for end, rule in END_RULES.items():
        if any(fname.startswith(pre) for pre in rule["img_prefix"]):
            return end
    return None


def check_ends(repo, base, text, explicit):
    """多端检查：每端要有分节 + 至少 1 张图。explicit=True 时缺项 NG。"""
    detected = detect_ends(repo)
    required = explicit if explicit else detected

    if explicit:
        unknown = [e for e in explicit if e not in END_RULES]
        if unknown:
            nail("ERR", f"未知端名: {', '.join(unknown)}（可选: {', '.join(END_RULES)}）")
            required = [e for e in explicit if e in END_RULES]
    if not required:
        return

    multi = len(required) >= 2
    level = "NG" if explicit else "WARN"
    if explicit:
        nail("INFO", f"多端核验（--ends）: {', '.join(required)}")
    elif multi:
        nail("INFO", f"自动探测到 {len(required)} 个端: {', '.join(required)}；缺项按 WARN 提示")
    else:
        return  # 单端项目不做分端检查（避免误判）

    secs = split_sections(text)
    imgs = image_refs(text)

    # 每端：标题命中 + 图片归属（路径/前缀 + 小节内）
    end_titles = {end: [] for end in required}
    end_imgs = {end: set() for end in required}
    for ln, lv, title, end_ln in secs:
        tl = title.lower()
        for end in required:
            if any(kw in tl for kw in END_RULES[end]["title_kw"]):
                end_titles[end].append(title)
        for img_ln, ref in imgs:
            if ln <= img_ln < end_ln:
                for end in required:
                    if any(kw in tl for kw in END_RULES[end]["title_kw"]):
                        end_imgs[end].add(ref)

    for img_ln, ref in imgs:
        end = classify_image(repo, base, ref)
        if end in end_imgs:
            end_imgs[end].add(ref)

    for end in required:
        rule = END_RULES[end]
        if not end_titles[end]:
            nail(level,
                 f"多端项目缺「{rule['label']}」章节：README 需有 H2/H3 标题含 "
                 f"{'/'.join(rule['title_kw'][:3])} 之一")
        if not end_imgs[end]:
            nail(level,
                 f"多端项目缺「{rule['label']}」界面图：放入 "
                 f"{rule['img_dirs'][0]}/ 并在该端小节引用")
        else:
            nail("INFO", f"{rule['label']}：{len(end_imgs[end])} 张图")


def main():
    argv = sys.argv[1:]
    repo, file, ends = parse_args(argv)
    repo = os.path.abspath(repo or ".")
    target = os.path.join(repo, file) if file else os.path.join(repo, "README.md")
    target = os.path.abspath(target)

    if not os.path.isfile(target):
        nail("NG", f"目标文件不存在: {target}")
        text = ""
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

        # 4) 图片落盘（Markdown 与 HTML <img> 都收）
        for m in IMG_RX.finditer(text):
            r = resolve(base, m.group(1).strip())
            if r is None:
                continue
            if not os.path.isfile(r):
                nail("NG", f"图片不存在: {m.group(1).strip()}（引用于 {relname}）")
        for m in IMG_HTML_RX.finditer(text):
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

        # 9) + 10) 多端分节与分端图墙
        check_ends(repo, base, text, ends)

    # ---- 结论 ----
    n_n, n_w = 0, 0
    for lvl, msg in NAGS:
        print(f"[{lvl}] {msg}")
        if lvl in ("NG", "ERR"):
            n_n += 1
        elif lvl == "WARN":
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
