# -*- coding: utf-8 -*-
"""vb_audit：甲方参考程序（VB/WinForms 老项目）脚本化体检。

只做事实提取，不下重构结论。凡是命中即记 file:line，原样引用，
AI 写转换理由时逐条认领，禁止无证据的指控（如“明文存密码”必须先 grep 到）。
依赖：仅标准库。

用法：
  python vb_audit.py "E:\\Project\\XXX参考" [-o 输出目录]

排除：bin/ obj/ .vs/ packages/ .git/（现场杂物与依赖噪音不计入）。
输出：
  终端：体检摘要（文件数/总行数/重复组/各类命中数）
  <outdir>/vb_audit.md：证据表（file:line + 命中行原文前 120 字）
"""
import argparse
import hashlib
import os
import re
import sys

SKIP_DIRS = {"bin", "obj", ".vs", "packages", ".git", "TestResults"}

# -*- coding: utf-8 -*-
"""ref_audit：甲方参考程序（老上位机）脚本化体检。原名 vb_audit，重命名不影响用法。

只做事实提取，不下重构结论。凡是命中即记 file:line，原样引用，
AI 写转换理由时逐条认领，禁止无证据的指控（如“明文存密码”必须先 grep 到）。
语言自适应：--lang auto（缺省，按扩展名判定）/vb/csharp/python。
依赖：仅标准库。

用法：
  python vb_audit.py "E:\\Project\\XXX参考" [-o 输出目录] [--lang auto]

排除：bin/ obj/ .vs/ packages/ .git/ node_modules/ __pycache__（现场杂物与依赖噪音不计入）。
输出：
  终端：体检摘要（文件数/总行数/重复组/各类命中数）
  <outdir>/vb_audit.md：证据表（file:line + 命中行原文前 120 字）
"""
import argparse
import hashlib
import os
import re
import sys

SKIP_DIRS = {"bin", "obj", ".vs", "packages", ".git", "TestResults",
             "node_modules", "__pycache__", ".venv", "venv"}

# 通用模式（语言无关）：硬编码与 SQL 是每种语言的通病
COMMON = [
    ("硬编码IP", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")),
    ("硬编码端口", re.compile(r",\s*60\d{2}\)")),
    ("DR地址字面量", re.compile(r'"[DR]\d+[A-Za-z0-9_]*"')),
    ("SQL拼接", re.compile(r'\$"[^"]*\{\w+[^"]*"')),
    ("SQL拼接&", re.compile(r"&\s*\"[^\"]*\"\s*&")),
    ("SQL拼接f串", re.compile(r'f"[^"]*\{\w+[^"]*"')),
    ("SQL拼接%", re.compile(r'"[^"]*%s[^"]*"\s*%')),
    ("登录关键字", re.compile(r"password|login|记住密码", re.IGNORECASE)),
]

# 分语言模式：阻塞弹窗 / 无超时连接 / 旧通讯 / 旧框架
LANG_PATTERNS = {
    "vb": [
        ("ConnectServer", re.compile(r"ConnectServer")),
        ("无超时连接", re.compile(r"ConnectServer\s*(\(\s*\))?$")),
        ("MsgBox阻塞", re.compile(r"MsgBox\s*\(")),
        ("HttpWebRequest旧", re.compile(r"HttpWebRequest")),
        ("FormsTimer", re.compile(r"Windows\.Forms\.Timer|WithEvents\s+Timer\w*")),
        ("框架版本", re.compile(r"TargetFrameworkVersion")),
        ("Hsl引用", re.compile(r"HslCommunication")),
        ("中英切换", re.compile(r"Function\s+Tr\s*\(")),
    ],
    "csharp": [
        ("连接调用", re.compile(r"\.Connect\s*\(|ConnectServer\s*\(")),
        ("无超时连接", re.compile(r"(\.Connect\s*\([^,)]*\)|ConnectServer\s*\(\s*\))\s*;?\s*$")),
        ("弹窗阻塞", re.compile(r"MessageBox\.Show\s*\(")),
        ("Http旧", re.compile(r"HttpWebRequest|WebClient\s*\(")),
        ("UI线程Timer", re.compile(r"System\.Windows\.Forms\.Timer|DispatcherTimer")),
        ("框架版本", re.compile(r"TargetFrameworkVersion|<TargetFramework>")),
        ("通讯库引用", re.compile(r"HslCommunication|S7\.Net|Sharp7|Modbus")),
        ("中英切换", re.compile(r"(Function|func|def)\s+Tr\s*\(")),
    ],
    "python": [
        ("连接调用", re.compile(r"\.connect\s*\(|ConnectServer\s*\(")),
        ("无超时连接", re.compile(r"\.connect\s*\(\s*\)")),
        ("弹窗阻塞", re.compile(r"messagebox\.show\w*\s*\(")),
        ("同步HTTP", re.compile(r"requests\.(get|post)\s*\(")),
        ("UI线程轮询", re.compile(r"after\s*\(\s*\d+|QTimer\s*\(")),
        ("通讯库引用", re.compile(r"pymodbus|python-snap7|HslCommunication")),
    ],
}
LANG_EXTS = {"vb": (".vb", ".vbproj", ".config"),
            "csharp": (".cs", ".csproj", ".config", ".xaml"),
            "python": (".py", ".cfg", ".ini")}

# 二次过滤（降噪，弱模型不用懂为什么，照抄）：
# - 硬编码IP：跳过程序集版本行（含 Version 字样，如 Version=4.0.0.0）
# - SQL拼接：只保留同行含 SQL 动词的（select/insert/update/delete/where/from），
#   普通 $"…" 拼日志/拼界面文字不算证据
SQL_VERB = re.compile(r"select|insert|update|delete|\bwhere\b|\bfrom\b", re.IGNORECASE)


def keep_hit(name, line):
    if name == "硬编码IP" and "version" in line.lower():
        return False
    if name in ("SQL拼接", "SQL拼接&") and not SQL_VERB.search(line):
        return False
    return True


def norm_hash(text):
    norm = re.sub(r"\s+", "", text)
    return hashlib.md5(norm.encode("utf-8", errors="replace")).hexdigest()


def keep_hit(name, line):
    if name == "硬编码IP" and "version" in line.lower():
        return False
    if name.startswith("SQL拼接") and not SQL_VERB.search(line):
        return False
    return True


def norm_hash(text):
    norm = re.sub(r"\s+", "", text)
    return hashlib.md5(norm.encode("utf-8", errors="replace")).hexdigest()


def detect_lang(root):
    ext_count = {"vb": 0, "csharp": 0, "python": 0}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            fl = fn.lower()
            if fl.endswith(LANG_EXTS["vb"]):
                ext_count["vb"] += 1
            elif fl.endswith((".cs", ".csproj")):
                ext_count["csharp"] += 1
            elif fl.endswith(".py"):
                ext_count["python"] += 1
    best = max(ext_count, key=ext_count.get)
    return best if ext_count[best] > 0 else "vb"


def collect_src(root, lang):
    exts = LANG_EXTS[lang]
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.lower().endswith(exts):
                files.append(os.path.join(dirpath, fn))
    return sorted(files)


def main():
    ap = argparse.ArgumentParser(description="参考程序脚本化体检（语言自适应）")
    ap.add_argument("projdir", help="参考项目根目录")
    ap.add_argument("-o", "--outdir", default="vb_audit_out", help="输出目录")
    ap.add_argument("--lang", default="auto", choices=["auto", "vb", "csharp", "python"],
                    help="语言（缺省 auto 按扩展名判定）")
    args = ap.parse_args()

    if not os.path.isdir(args.projdir):
        print(f"目录不存在：{args.projdir}", file=sys.stderr)
        return 2
    os.makedirs(args.outdir, exist_ok=True)

    lang = detect_lang(args.projdir) if args.lang == "auto" else args.lang
    patterns = COMMON + LANG_PATTERNS[lang]
    code_ext = {".vb", ".cs", ".py"}

    files = collect_src(args.projdir, lang)
    line_counts = {}
    hashes = {}
    total_lines = 0
    for fp in files:
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        n = text.count("\n") + 1
        line_counts[fp] = n
        if os.path.splitext(fp)[1].lower() in code_ext:
            total_lines += n
            hashes.setdefault(norm_hash(text), []).append(fp)

    dup_groups = {h: v for h, v in hashes.items() if len(v) > 1}

    hits = {name: [] for name, _ in patterns}
    for fp in files:
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue
        rel = os.path.relpath(fp, args.projdir)
        for i, line in enumerate(lines, start=1):
            for name, pat in patterns:
                if pat.search(line) and keep_hit(name, line):
                    hits[name].append((rel, i, line.strip()[:120]))

    md = ["# 参考程序体检证据表", "", f"根目录：{args.projdir}",
          f"判定语言：{lang}，源码文件：{len(files)} 个，代码总行数：{total_lines} 行", ""]
    md.append("## 文件规模 Top（行数最多 15 个）")
    for fp in sorted(line_counts, key=line_counts.get, reverse=True)[:15]:
        md.append(f"- {os.path.relpath(fp, args.projdir)}：{line_counts[fp]} 行")
    md.append("")
    md.append("## 完全重复文件组（归一化 hash 相同，改一处要改 N 处）")
    if dup_groups:
        for _, group in dup_groups.items():
            md.append(f"- {'; '.join(os.path.relpath(g, args.projdir) for g in group)}")
    else:
        md.append("- 无")
    md.append("")
    for name, _ in patterns:
        md.append(f"## {name}（{len(hits[name])} 处）")
        for rel, ln, txt in hits[name][:30]:
            md.append(f"- {rel}:{ln}：{txt}")
        if len(hits[name]) > 30:
            md.append(f"- …另 {len(hits[name]) - 30} 处省略")
        if not hits[name]:
            md.append("- 无命中（该指控不成立，对外禁止提）")
        md.append("")

    with open(os.path.join(args.outdir, "vb_audit.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"语言 {lang}，文件 {len(files)} 个，代码总行数 {total_lines} 行，重复组 {len(dup_groups)} 个")
    for name, _ in patterns:
        print(f"  {name}：{len(hits[name])} 处")
    print(f"已写出：{args.outdir}/vb_audit.md")
    print("铁律：命中数为 0 的指控（如登录关键字）对外禁止提；转写转换理由时每条必须带 file:line。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
