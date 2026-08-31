#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
precommit_check.py — Git 提交前安全与卫生检查（AI/人工通用，结果只有 OK / NG）

为什么要有这个脚本：
  提交前的"改动范围确认 + 不该入库文件拦截 + 机密泄露扫描 + 编码自查"是每次提交
  都该做的固定动作，但人工/AI 口头执行容易漏项、标准不一致。固化为脚本后：
  AI 只需调用本脚本并读取最后一行 `RESULT: OK` 或 `RESULT: NG`，
  OK → 放心走提交流程；NG → 按 [NG-*] 编号明细处理后再提交。

检查项（每项输出 [OK-*] 或 [NG-n]/[WARN-n]）：
  1. 待提交改动清单（status --porcelain 全量列出，供人工复核范围）
  2. 禁止入库文件名检测：运行时数据（Users.json/TestSession.json 等）、日志、
     构建产物、机密类文件变体（*.pem/*.key/.env/*credential*/*secret*…）
  3. 机密内容变体扫描（对将提交的文本 diff 内容）：
     私钥块、api_key/secret/token/password 赋值、连接串 pwd=…
     命中分 ERROR（高危，判 NG）/ WARN（可疑，人工判断）
  4. 中文文本文件编码自查：必须能按 UTF-8 解码（项目铁律，GBK 落盘即乱码）
  5. 超大文件提醒（>10MB 列 WARN）

用法：
  python precommit_check.py [仓库路径]        # 默认当前目录
  python precommit_check.py . --quiet         # 只输出结论行（供脚本链消费）

退出码：0 = RESULT: OK；1 = RESULT: NG；2 = 环境错误（非 git 仓库等）
依赖：Python 3.8+，git 在 PATH。无第三方库。
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ============ 规则配置（按需增删） ============

# 文件名级禁止/警惕规则（不区分大小写，匹配相对路径或文件名）
FILENAME_DENY = [
    # 运行时生成的数据（含机密或环境专属状态）
    r"(^|[\\/])users?\.json$", r"rememberedlogin\.json$",
    r"recipes\.json$", r"stationsettings\.json$", r"testsession\.json$",
    # 日志与临时文件
    r"(^|[\\/])logs([\\/]|$)", r"\.log$", r"\.tmp$", r"\.bak$", r"~\$",
    # 构建产物（双保险，正常已被 .gitignore 拦截）
    r"(^|[\\/])bin([\\/]|$)", r"(^|[\\/])obj([\\/]|$)",
]
FILENAME_SECRET_VARIANTS = [
    # 机密文件变体（命中即 NG：这类文件几乎不可能该入库）
    r"\.pem$", r"\.key$", r"\.pfx$", r"\.p12$", r"\.jks$",
    r"id_rsa", r"id_dsa", r"id_ed25519", r"\.env($|\.)",
    r"credential", r"passwd", r"secret", r"\.kdbx$", r"secrets\.ya?ml$",
    # 商业组件授权文件（泄露 = 别人盗用商用授权）。V1.59 教训：
    # HslLicense.dat / hsl.dat（HSL 工业通讯库授权码）曾不在规则里会被漏掉。
    # 注意不要用裸 "license" 关键词——开源协议文本 LICENSE.md 必须放行，
    # 所以只匹配"授权语义 + 数据/授权扩展名"的组合：
    r"licen[cs]e.*\.(dat|bin|data|db)$",   # HslLicense.dat 等授权数据库文件
    r"^hsl[^\\/]*\.dat$",                   # hsl.dat 及其变体（HSL 库授权）
    r"\.lic$", r"\.licen[cs]e$",
    # .NET 强名称私钥（签名密钥，绝不入库）
    r"\.snk$",
]

# 内容级机密正则：(编译后的正则, 说明)。命中 → ERROR 判 NG
CONTENT_SECRET_ERROR = [
    (re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
     "私钥块"),
    (re.compile(r"\b(api[_-]?key|apikey)\s*[=:]\s*[\"'][^\"']{8,}[\"']", re.I),
     "API Key 明文赋值"),
    (re.compile(r"\b(secret|client[_-]?secret)\s*[=:]\s*[\"'][^\"']{8,}[\"']", re.I),
     "Secret 明文赋值"),
    (re.compile(r"\b(token|access[_-]?token)\s*[=:]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']", re.I),
     "Token 明文赋值"),
    (re.compile(r"(pwd|password)\s*=\s*[^;\"\s]{4,}\s*(;|$)", re.I | re.M),
     "连接串明文密码"),
]
# 可疑但常误报（默认密码注释、占位符、哈希字段名等）→ WARN 不判 NG
CONTENT_SECRET_WARN = [
    (re.compile(r"\bpassword\b\s*[:=]\s*[\"'][^\"']{3,}[\"']", re.I), "password 字面量（请人工确认非真实密码）"),
]
# 占位符白名单：值长这样视为非机密（your_xxx / xxx / <...> / ${...} / changeme）
PLACEHOLDER_RE = re.compile(
    r"^(\$\{.*\}|<.*>|your[_-].*|xxx+|\{\{.*\}\}|changeme|example.*)$", re.I)

# 编码检查覆盖的文本扩展名（含中文时必须 UTF-8 可解码）
TEXT_EXTS_FOR_UTF8 = {".cs", ".md", ".json", ".txt", ".xml", ".config", ".ps1",
                      ".py", ".sql", ".htm", ".html", ".yml", ".yaml"}

MAX_CONTENT_SCAN_BYTES = 1 * 1024 * 1024   # 单文件内容扫描上限 1MB（防卡）
BIG_FILE_WARN_BYTES = 10 * 1024 * 1024     # >10MB 提醒

# ---------- 输出辅助 ----------
_issues = []      # [(级别, 编号, 描述)]，只记 NG/WARN


def _print_tagged(level: str, n: int, desc: str):
    tag = f"[{level}-{n}]" if level in ("NG", "WARN") else "[OK]"
    print(f"  {tag} {desc}")


def ok(msg: str):
    _print_tagged("OK", 0, msg)


def ng(msg: str):
    n = len(_issues) + 1
    _issues.append(("NG", n, msg))
    _print_tagged("NG", n, msg)


def warn(msg: str):
    n = len(_issues) + 1
    _issues.append(("WARN", n, msg))
    _print_tagged("WARN", n, msg)


def git(*args, cwd):
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {proc.stderr.strip()}")
    return proc.stdout


def is_binary(data: bytes) -> bool:
    """粗判二进制：含 NUL 即二进制（与 git 核心判定一致）。"""
    return b"\x00" in data[:8000]


def placeholder_like(value: str) -> bool:
    return bool(PLACEHOLDER_RE.match(value.strip()))


def scan_text_for_secrets(text: str, where: str):
    """对一个文本内容做机密模式扫描；ERROR 判 NG，WARN 仅提示。"""
    for rex, label in CONTENT_SECRET_ERROR:
        for m in rex.finditer(text):
            frag = m.group(0)
            # 取赋值右侧做占位符豁免
            tail = re.split(r"[=:]", frag, maxsplit=1)[-1].strip(" \"';")
            if placeholder_like(tail):
                continue
            ng(f"{where}: 疑似{label} → {frag[:60]}...")
            break   # 同一文件同类只报第一处，避免刷屏
    for rex, label in CONTENT_SECRET_WARN:
        for m in rex.finditer(text):
            frag = m.group(0)
            tail = re.split(r"[=:]", frag, maxsplit=1)[-1].strip(" \"';")
            if placeholder_like(tail):
                continue
            warn(f"{where}: {label} → {frag[:60]}...")
            break


def run_checks(repo: Path, quiet: bool = False) -> int:
    """
    执行全部检查并打印报告；返回退出码（0=OK / 1=NG）。
    独立成函数供 git_commit_push.py 在提交流程内自动调用。
    """
    global _issues
    _issues = []   # 支持同进程多次调用（重置计数）

    status_lines = [ln for ln in git("status", "--porcelain", cwd=repo).splitlines()
                    if ln.strip()]
    if not status_lines:
        print("工作区干净，没有待提交改动。")
        print("RESULT: OK")
        return 0

    if not quiet:
        print(f"待提交改动共 {len(status_lines)} 处：")
        for ln in status_lines:
            print(f"  {ln}")

    # ===== 收集"将要进入版本库"的文件集合 =====
    # 已跟踪修改：diff HEAD；未跟踪：?? 文件原样读
    tracked_changed = []
    try:
        tracked_changed = [ln[3:].strip() for ln in
                           git("diff", "--name-status", "HEAD", cwd=repo).splitlines()
                           if ln.strip()]
    except RuntimeError:
        pass   # 首次提交无 HEAD
    untracked = [ln[2:].strip().strip('"') for ln in status_lines if ln.startswith("??")]
    all_files = list(dict.fromkeys(tracked_changed + untracked))   # 去重保序

    print("\n===== 1. 禁止入库文件名检测 =====")
    for f in all_files:
        low = f.lower().replace("\\", "/")
        base = low.rsplit("/", 1)[-1]
        hit_denied = next((pat for pat in FILENAME_DENY
                           if re.search(pat, low, re.I)), None)
        hit_secret = next((pat for pat in FILENAME_SECRET_VARIANTS
                           if re.search(pat, base, re.I)), None)
        if hit_secret:
            ng(f"机密类文件变体待提交：{f}（匹配 /{hit_secret}/）——机密文件绝不入库")
        elif hit_denied:
            ng(f"运行时数据/产物待提交：{f}（匹配 /{hit_denied}/）——应加入 .gitignore")

    print("\n===== 2. 机密内容变体扫描（diff 与新文件内容）=====")
    scanned = 0
    for f in all_files:
        fp = repo / f
        if not fp.is_file() or fp.stat().st_size > MAX_CONTENT_SCAN_BYTES:
            continue
        try:
            raw = fp.read_bytes()
        except OSError:
            continue
        if is_binary(raw):
            continue
        ext = fp.suffix.lower()
        if ext not in TEXT_EXTS_FOR_UTF8 and ext != "":
            # 未跟踪的未知文本类型也粗扫一下机密（用 errors=replace 防炸）
            text = raw.decode("utf-8", errors="replace")
            scan_text_for_secrets(text, f)
            scanned += 1
            continue
        text = raw.decode("utf-8", errors="replace")
        scan_text_for_secrets(text, f)
        scanned += 1
    print(f"  已扫描 {scanned} 个文本文件的内容。")

    print("\n===== 3. 中文文本文件 UTF-8 编码自查 =====")
    enc_bad = 0
    for f in all_files:
        fp = repo / f
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in TEXT_EXTS_FOR_UTF8:
            continue
        try:
            raw = fp.read_bytes()
        except OSError:
            continue
        if is_binary(raw):
            continue
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as ex:
            enc_bad += 1
            ng(f"非 UTF-8 编码（会乱码）：{f}（offset {ex.start}）——转成 UTF-8 再提交")
    if enc_bad == 0:
        ok("全部中文文本文件均为合法 UTF-8。")

    print("\n===== 4. 超大文件提醒 =====")
    big = [f for f in all_files
           if (repo / f).is_file() and (repo / f).stat().st_size > BIG_FILE_WARN_BYTES]
    if big:
        for f in big:
            warn(f"大文件 >10MB：{f}（{(repo/f).stat().st_size//1024//1024}MB）——确认确有必要入库")
    else:
        ok("无超大文件。")

    # ===== 结论 =====
    ng_count = sum(1 for lv, _, _ in _issues if lv == "NG")
    warn_count = sum(1 for lv, _, _ in _issues if lv == "WARN")
    print("\n" + "=" * 64)
    if ng_count > 0:
        print(f"RESULT: NG（{ng_count} 个必须处理的问题，{warn_count} 个提醒）")
        for lv, n, desc in _issues:
            if lv == "NG":
                print(f"  [NG-{n}] {desc}")
        return 1
    if warn_count > 0:
        print(f"RESULT: OK（无阻断问题；{warn_count} 条提醒请人工过目）")
        for lv, n, desc in _issues:
            if lv == "WARN":
                print(f"  [WARN-{n}] {desc}")
        return 0
    print("RESULT: OK（改动范围、机密卫生、文件编码均通过）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Git 提交前安全与卫生检查（OK/NG）")
    parser.add_argument("path", nargs="?", default=".", help="仓库路径（默认当前目录）")
    parser.add_argument("--quiet", action="store_true", help="只打印结论与问题明细")
    args = parser.parse_args()

    repo = Path(args.path).resolve()
    try:
        git("rev-parse", "--is-inside-work-tree", cwd=repo)
    except Exception:
        print(f"RESULT: NG（不是 Git 仓库：{repo}）")
        return 2

    return run_checks(repo, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
