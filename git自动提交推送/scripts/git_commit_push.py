#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
git_commit_push.py — 一键提交并推送 Git 仓库（自动生成 commit message）

设计目标：
  1. 不依赖任何 AI，人工直接运行本脚本即可把工程上传 GitHub；
  2. commit message 尽量"写得好"——优先从仓库内 CHANGELOG.md 的"最新版本条目"
     提取版本号+标题作为提交说明（这正是工程规范要求"改动同步记 CHANGELOG"的
     自然延续，commit 与版本记录天然一致）；
  3. 无 CHANGELOG 或提取不到时，回退为按改动文件统计生成的类型化摘要；
  4. 所有破坏性动作前都有预览与确认，支持 --dry-run / --no-push / --force 等开关。

 用法：
   python git_commit_push.py                 # 提交全部改动并推送（自动生成消息，需确认）
   python git_commit_push.py -m "fix: xxx"   # 手动指定 commit message
   python git_commit_push.py --no-push       # 只提交不推送
   python git_commit_push.py --dry-run       # 只预览将执行的动作，不真正提交/推送
   python git_commit_push.py --force         # 跳过确认（CI 等无人值守场景）
   python git_commit_push.py --explicit --force  # 显式暂存模式：跳过自动 add -A，
                                             # 只提交已暂存内容（现场运行目录必用）
   提交前自动跑两道检查：precommit_check（待提交增量）+ 仓库自带的
   repo-hygiene 体检（.gitignore 规则/全库健康，有则跑，无则跳过）。

依赖：Python 3.8+，git 在 PATH 中。无第三方库，标准库实现。
"""

import argparse
import importlib.util
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# Windows 控制台默认 GBK 代码页会导致中文输出乱码，强制 stdout/stderr 用 UTF-8。
# （GitHub Actions / Linux 终端天然 UTF-8，不受影响；此处仅在非 UTF-8 环境适配。）
if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------- 输出辅助 ----------

def info(msg: str):
    print(msg)


def ok(msg: str):
    print(f"\033[32m{msg}\033[0m")


def warn(msg: str):
    print(f"\033[33m[警告] {msg}\033[0m")


def err(msg: str):
    print(f"\033[31m[错误] {msg}\033[0m", file=sys.stderr)


# ---------- git 辅助 ----------

def git(*args: str, cwd: Path) -> str:
    """执行 git 命令，成功返回 stdout 去尾空白；失败抛异常。"""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} 失败（code {proc.returncode}）:\n{proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def git_quiet(*args: str, cwd: Path) -> bool:
    """执行 git 命令，只返回成功与否，不抛异常。"""
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8"
    )
    return proc.returncode == 0


def git_lines(*args: str, cwd: Path) -> list:
    """执行 git 命令，返回非空 stdout 行列表。"""
    out = git(*args, cwd=cwd)
    return [ln for ln in out.splitlines() if ln.strip()]


# ---------- commit message 生成 ----------

def extract_latest_version(changelog: Path) -> tuple:
    """
    解析 CHANGELOG.md 的"最新版本条目"，返回 (版本头文本, 该版本下的 ### 小节标题列表)。

    兼容三种主流 CHANGELOG 写法（历史教训两次：
      V4.3.2 教训 —— 旧版只取第一个 ## 标题行当主题，而 Keep-a-Changelog 格式的
        标题行只是版本号+日期、真正的改动摘要在下面若干 "### 修复：xxx" 小节里，
        导致 commit message 毫无信息量；
      V1.59 教训 —— AgingTestSystem 的格式是"版本行自带完整摘要 + ### 改动范围/
        为什么这么改/验证 只是段落分组标签"，旧逻辑见 ### 就走小节拼接，
        把分组标签当成摘要，commit 标题变成"V1.59 改动范围；为什么这么改；验证"。
        必须按"版本头是否自带实质摘要"来区分，而不是简单看有没有 ### 小节）：

      A) 标题即摘要型 / 混合型（AgingTestSystem 等）：
         ## V1.0.0（2026-08-15）新增 CommonLib 通用设备通讯库（...）
         ## V1.59 — 业务串联完善：三阶段老化状态机 + 断电恢复（2026-08-26）
         ### 改动范围 / ### 为什么这么改 / ### 验证   ← 只是段落分组，不是摘要条目
         → 版本头剥掉版本号/日期后还有实质文字 → 直接用整行当主题（小节名进正文）

      B) Keep-a-Changelog 型（裸版本头，HuaJiVision 等项目在用）：
         ## [V4.3.2] - 2026-08-25                    ← 除版本号+日期外没有实质文字
         ### 修复：主窗体显示后加载画面迟迟不消失
         ### 功能：开发者面板 Designer 化
         → 主题由版本号 + 各小节标题拼接而成，完整清单进正文

    解析失败返回 ("", [])。
    """
    try:
        lines = changelog.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return "", []
    version_line = None
    subsections = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("### "):
            # 只收集最新版本条目内部的小节；版本头出现前的散落 ### 不算
            if version_line is not None:
                subsections.append(clean_markdown(s[4:].strip()))
            continue
        if s.startswith("## "):
            if version_line is None:
                version_line = clean_markdown(s[3:].strip())
            else:
                break   # 已进入下一个版本条目 → 最新条目收集完毕
    if version_line is None:
        return "", []
    return version_line, subsections


def version_header_has_summary(version_line: str) -> bool:
    """
    判断版本头除"版本号 + 日期 + 装饰分隔符"之外，是否还有实质摘要文字。

    例：
      "[V4.3.2] - 2026-08-25"                                  → False（裸版本头）
      "V1.59 — 业务串联完善：三阶段老化状态机 + 断电恢复（2026-08-26）" → True
    """
    s = version_line
    s = re.sub(r"^(\[?[Vv]\d[\w.\-]*\]?)", "", s)                 # 去开头版本号
    s = re.sub(r"[（(]?\d{4}[-/.]\d{1,2}[-/.]\d{1,2}[）)]?", "", s)  # 去日期
    s = re.sub(r"[\s\-—–_*#.·]+", "", s)                          # 去装饰符与空白
    return len(s) >= 8   # 至少 8 个实质字符才认为版本头自带摘要


def build_changelog_subject(version_line: str, subsections: list) -> str:
    """
    由版本头与小节标题拼装 commit 主题行：

      - 无小节，或版本头自带实质摘要（混合型）→ 直接用版本头整行
        （小节名只是段落分组标签，拼进标题只会产生"改动范围；验证"这种零信息量主题）；
      - 裸版本头 + 小节（Keep-a-Changelog 型）→ "版本号 小节1；小节2；…"，
        超长截断加省略号（git 惯例主题一行内；完整小节清单由调用方写入正文）。
    """
    if not subsections or version_header_has_summary(version_line):
        subject = version_line
    else:
        # 提取版本号前缀（如 "[V4.3.2]"、"V1.0.0"）；取不到就用版本头第一个空格前的词
        m = re.match(r"^(\[?[Vv]\d[\w.\-]*\]?)", version_line)
        ver = m.group(1) if m else (version_line.split()[0] if version_line.split() else "")
        subject = (ver + " " if ver else "") + "；".join(subsections)
    if len(subject) > SUBJECT_MAX_LEN:
        subject = subject[:SUBJECT_MAX_LEN].rstrip() + "…"
    return subject


# commit 主题行长度上限：git 社区惯例单行主题宜短（GitHub 网页 ~72 字符后省略），
# 中文信息密度高，放宽到 100 字符；超出部分进正文而非硬塞主题
SUBJECT_MAX_LEN = 100

# ---------- 正文要点细节提炼（2026-09-05 从 HJVision 项目 skill 合并进来） ----------
# 背景：V4.3.2 的 commit 正文曾只有"对应 CHANGELOG.md 最新版本条目"一句空话——
# 主题只抄了版本头、真正的干货（### 小节下的 - 条目与 ①②③ 续行）全丢了。
# 以下规则把"版本小节 → 结构化正文"的提炼固定下来，AI 不再手打正文：
BULLET_MAX_LEN = 140   # 单条要点上限（截断加 …；关键词不断腰靠 140 冗余保证）
MAX_PER_SECTION = 8    # 每个 ### 小节最多收录条数
MAX_BULLETS = 32       # 全文最多收录条数（超限加"完整改动见 CHANGELOG"尾行）
BULLET_ENUM_RE = re.compile(r"^[\u2460-\u2468]\s*(.+)$")  # ①②③④⑤⑥⑦⑧⑨ 枚举行
BULLET_DASH_RE = re.compile(r"^\s*-\s+(.+)$")              # - 条目行
BULLET_CONT_RE = re.compile(r"^\s+\S")                     # 缩进续行（拼回上一条）


def _clean_bullet(text: str) -> str:
    """清洗单条要点：去 markdown 标记、压空白、超长截断（与 clean_markdown 互补，专供正文）。"""
    text = clean_markdown(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > BULLET_MAX_LEN:
        text = text[:BULLET_MAX_LEN - 1].rstrip() + "…"
    return text


def _is_pure_title(bullet: str) -> bool:
    """纯标题头判定：太短或以 ：/ : 结尾的是分组标签不是干货，直接丢弃。"""
    return len(bullet) <= 6 or bullet.endswith("：") or bullet.endswith(":")


def extract_latest_sections(changelog: Path) -> tuple:
    """
    解析 CHANGELOG 最新版本小节的结构化正文，返回 (版本头文本, sections)。

    sections = [{"title": 小节标题, "bullets": [要点, ...]}, ...]，要点已按
    BULLET_MAX_LEN / MAX_PER_SECTION / MAX_BULLETS 截断前的原始上限做节内截断
    （总量截断由调用方做，以便统一追加溢出尾行）。

    抓取规则（与 HJVision 原 New-CommitMessage.ps1 对齐）：
      - `### 标题` 开新节；
      - `- xxx` 条目行收一条；
      - `①②③… xxx` 枚举行收一条；
      - 缩进续行拼回上一条（CHANGELOG 把长干货写在续行里，只抓 - 行会丢信息）；
      - 以 ：/: 结尾的纯标题头丢弃。
    解析失败返回 ("", [])。
    """
    try:
        raw = changelog.read_bytes()
    except OSError:
        return "", []
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
        except (OSError, UnicodeDecodeError):
            return "", []
    if not text or "\ufffd" in text:
        return "", []  # 含替换符 = 已损坏，不硬拼正文，调用方回退标题清单
    if text and text[0] == "\ufeff":
        text = text[1:]
    lines = text.splitlines()

    version_line = ""
    sections: list = []
    cur = None  # {"title": str, "raw": [str, ...]}
    in_latest = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("## "):
            if not in_latest:
                version_line = clean_markdown(s[3:].strip())
                in_latest = True
            else:
                break  # 下一个版本条目 → 最新条目收集完毕
            continue
        if not in_latest:
            continue  # 版本头出现前的散落 ### 不算
        m_sec = re.match(r"^###\s+(.+)$", ln.strip())
        if m_sec:
            if cur is not None:
                sections.append(cur)
            cur = {"title": _clean_bullet(m_sec.group(1)), "raw": []}
            continue
        if cur is None:
            continue
        m_dash = BULLET_DASH_RE.match(ln)
        if m_dash:
            cur["raw"].append(m_dash.group(1))
            continue
        m_enum = BULLET_ENUM_RE.match(ln.strip())
        if m_enum:
            cur["raw"].append(m_enum.group(1))
            continue
        if BULLET_CONT_RE.match(ln) and cur["raw"]:
            cur["raw"][-1] += " " + ln.strip()
    if cur is not None:
        sections.append(cur)

    if not version_line:
        return "", []
    # 清洗 + 过滤 + 节内截断
    cleaned: list = []
    for sec in sections:
        bullets: list = []
        for r in sec["raw"]:
            if len(bullets) >= MAX_PER_SECTION:
                break
            b = _clean_bullet(r)
            if _is_pure_title(b):
                continue
            bullets.append(b)
        cleaned.append({"title": sec["title"], "bullets": bullets})
    return version_line, cleaned


def clean_markdown(text: str) -> str:
    """去掉 commit 标题里常见的 markdown 标记（`、**、[x](url)）。"""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return text.strip()


def build_type_summary(changed: list) -> str:
    """
    无 CHANGELOG 可用时，按改动文件类型统计生成提交摘要。

    例如：新增 2 个文件、修改 5 个文件、删除 1 个文件
    """
    counter = Counter()
    for status in changed:
        if status.startswith("A") or status.startswith("??"):
            counter["新增"] += 1
        elif status.startswith("D"):
            counter["删除"] += 1
        elif status.startswith("R"):
            counter["重命名"] += 1
        else:
            counter["修改"] += 1
    parts = [f"{name} {cnt} 个文件" for name, cnt in counter.items()]
    return "、".join(parts)


def find_changelog(repo: Path) -> Path:
    """在仓库内找 CHANGELOG.md（优先根目录，其次常见大小写变体）。"""
    for name in ("CHANGELOG.md", "changelog.md", "CHANGELOG.MD"):
        p = repo / name
        if p.is_file():
            return p
    return None


# ---------- 提交前安全检查（precommit_check.py 集成） ----------
def run_precommit_check(repo: Path) -> int:
    """
    调用同目录 precommit_check.py 做提交前检查（机密变体/禁入文件/编码/大文件），
    返回其退出码：0=OK 可提交；1=NG 必须处理；2=脚本缺失（降级跳过检查并提示）。
    """
    check_path = Path(__file__).with_name("precommit_check.py")
    if not check_path.is_file():
        warn("未找到 precommit_check.py，跳过提交前检查（建议补齐该脚本）。")
        return 2
    try:
        spec = importlib.util.spec_from_file_location("precommit_check", str(check_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.run_checks(repo, quiet=False)
    except Exception as ex:
        warn(f"提交前检查执行异常（不阻断提交）：{ex}")
        return 2


def run_repo_hygiene(repo: Path) -> int:
    """
    仓库自带卫生体检（repo-hygiene）的提交前联动。

    发现 `<repo>/.opencode/skills/repo-hygiene/Test-GitignoreHygiene.ps1` 即用
    非 Strict 模式跑一遍。必须用非 Strict：Strict 下 H6 见脏即 FAIL，而待提交
    的改动本身就是脏（硬用 Strict 会挡住每一次正常提交）；非 Strict 下只有
    H1-H5 的硬伤（.gitignore 规则失效/必跟踪文件被误伤/死规则/敏感内容/坏编码）
    才 exit 1，H6 工作区脏列表（含本次待提交改动，属正常）仅 WARN 展示。

    返回：0=通过或无自带脚本（不阻断）；1=有 FAIL 必须处理；2=环境不支持
    （非 Windows 或无 powershell，降级跳过并提示）。
    """
    script = repo / ".opencode" / "skills" / "repo-hygiene" / "Test-GitignoreHygiene.ps1"
    if not script.is_file():
        return 0  # 通用仓库无自带体检：precommit_check 已覆盖待提交增量，不阻断
    if os.name != "nt":
        warn("仓库自带 repo-hygiene 体检为 PowerShell 脚本，非 Windows 环境跳过。")
        return 2
    try:
        proc = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            cwd=str(repo), capture_output=True, text=True, encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        warn("未找到 powershell，跳过 repo-hygiene 体检。")
        return 2
    except Exception as ex:
        warn(f"repo-hygiene 体检执行异常（不阻断提交）：{ex}")
        return 2
    out = (proc.stdout or "").strip()
    if out:
        print(out)
    if proc.returncode != 0:
        return 1
    return 0


def build_commit_message(repo: Path, changed: list) -> tuple:
    """
    组装 commit message。

    返回 (subject, body)：
      - subject 优先用 CHANGELOG 最新版本条目标题（三种格式自适应，见上）；
      - body 为结构化正文：版本条目标注 + 每个 ### 小节的 `· 标题` /
        `  - 要点`（要点来自 - 条目与 ①②③ 续行，纯标题头已过滤）；
        无要点可抓时回退为小节标题清单；无 CHANGELOG 时回退为类型摘要+文件清单。
      - 正文绝不只剩"对应 CHANGELOG.md 最新版本条目"一句空话（V4.3.2 教训）。
    """
    changelog = find_changelog(repo)
    if changelog is not None:
        version_line, subs = extract_latest_version(changelog)
        if version_line:
            subject = build_changelog_subject(version_line, subs)
            _v2, sections = extract_latest_sections(changelog)
            body_lines = [f"对应 {changelog.name} 最新版本条目：{version_line}", ""]
            used = 0
            truncated = False
            for sec in sections:
                if used >= MAX_BULLETS:
                    truncated = True
                    break
                body_lines.append(f"· {sec['title']}")
                for b in sec["bullets"]:
                    if used >= MAX_BULLETS:
                        truncated = True
                        break
                    body_lines.append(f"  - {b}")
                    used += 1
            if truncated:
                m_ver = re.search(r"\[?V[\d.]+\]?", version_line)
                ver = m_ver.group(0) if m_ver else version_line[:20]
                body_lines.append(f"  …（完整改动见 {changelog.name} {ver} 小节）")
            elif used == 0 and subs:
                # 有小节标题但无 - /①②③ 干货：标题清单进正文，保证不丢信息
                body_lines.extend(f"- {s}" for s in subs)
            return subject, "\n".join(body_lines)

    # 回退：类型摘要 + 文件明细
    subject = build_type_summary(changed)
    files = [ln.split("\t")[-1] for ln in git_lines(
        "diff", "--name-status", "HEAD", cwd=repo)] if git_quiet("rev-parse", "HEAD", cwd=repo) else []
    files += [ln[3:].strip() for ln in changed if ln.startswith("??")]
    body = "本次改动文件：\n" + "\n".join(f"- {f}" for f in files[:50])
    return subject, body


# ---------- 主流程 ----------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="一键提交并推送 Git 仓库（自动生成 commit message）"
    )
    parser.add_argument("path", nargs="?", default=".", help="仓库路径（默认当前目录）")
    parser.add_argument("-m", "--message", default="", help="手动指定 commit message（覆盖自动生成）")
    parser.add_argument("--no-push", action="store_true", help="只提交，不推送")
    parser.add_argument("--dry-run", action="store_true", help="只预览将执行的动作，不真正提交/推送")
    parser.add_argument("--force", action="store_true", help="跳过确认（无人值守场景）")
    parser.add_argument("--skip-check", action="store_true",
                        help="跳过提交前安全检查（precommit_check + repo-hygiene 联动）")
    parser.add_argument("--explicit", action="store_true",
                        help="显式暂存模式：跳过自动 git add -A，只提交已暂存内容；"
                             "无已暂存时中止（现场运行目录/含运行时数据仓库必用，防误收）")
    args = parser.parse_args()

    repo = Path(args.path).resolve()
    if not repo.is_dir():
        err(f"目录不存在：{repo}")
        return 1
    if not git_quiet("rev-parse", "--is-inside-work-tree", cwd=repo):
        err(f"不是 Git 仓库：{repo}")
        return 1

    branch = git("branch", "--show-current", cwd=repo)
    info(f"仓库：{repo}")
    info(f"分支：{branch or '(detached)'}")

    # 1. 查看改动
    changed = git_lines("status", "--porcelain", cwd=repo)
    if not changed:
        info("工作区干净，无改动可提交。")
        return 0
    info(f"\n共 {len(changed)} 处改动：")
    for ln in changed:
        info(f"  {ln}")
    info("\n改动统计：")
    stat = git_lines("diff", "--stat", cwd=repo)
    for ln in stat:
        info(f"  {ln}")

    # 1.5 提交前安全检查（机密变体/禁入文件/编码/大文件）：NG 直接中止
    if not args.skip_check:
        print("\n===== 提交前安全检查（precommit_check）=====")
        check_code = run_precommit_check(repo)
        print("=" * 64)
        if check_code == 1:
            err("提交前检查 NG：请先处理上方 [NG-*] 问题（机密/禁入文件/编码），"
                "确属误报可用 --skip-check 强制提交。")
            return 1
        if args.dry_run and check_code == 0:
            info("[precommit] OK。")

    # 1.6 仓库自带卫生体检联动（repo-hygiene：.gitignore 规则/全库编码/敏感内容）
    # 非 Strict：H1-H5 的 FAIL 阻断提交；H6 脏列表仅展示（待提交改动本身会上榜，正常）
    if not args.skip_check:
        print("\n===== 仓库卫生体检（repo-hygiene，仓库自带时）=====")
        hyg_code = run_repo_hygiene(repo)
        print("=" * 64)
        if hyg_code == 1:
            err("仓库卫生体检 FAIL：请先处理上方 [FAIL] 问题（.gitignore/机密/编码），"
                "确属误报可用 --skip-check 强制提交。")
            return 1

    # 2. 生成 commit message
    if args.message.strip():
        subject = args.message.strip()
        body = ""
    else:
        subject, body = build_commit_message(repo, changed)

    # 3. 预览与确认（正文最多展示 12 行，足够看到版本条目的小节清单）
    print("\n" + "=" * 64)
    print(f"提交标题：{subject}")
    if body:
        preview = body.splitlines()[:12]
        print("提交正文：")
        for pl in preview:
            print(f"  {pl}")
        if len(body.splitlines()) > 12:
            print("  ...")
    print("=" * 64)

    if args.dry_run:
        info("\n[dry-run] 将执行：")
        if args.explicit:
            staged_preview = git_lines("diff", "--cached", "--name-only", cwd=repo)
            if not staged_preview:
                info("  （显式模式：暂存区为空 → 真实运行时将中止，需先逐个 git add）")
            else:
                info(f"  （显式模式：跳过 git add，只提交已暂存的 {len(staged_preview)} 个文件）")
        else:
            info("  git add -A")
        info(f"  git commit -m \"{subject}\"")
        if not args.no_push:
            info("  git push")
        info("[dry-run] 未做任何实际改动。")
        return 0

    if not args.force:
        try:
            answer = input("\n确认提交并推送？[y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer not in ("y", "yes"):
            info("已取消。")
            return 0

    # 4. 暂存 + 提交（显式模式跳过自动 add，只收已暂存；防现场数据误入库）
    if args.explicit:
        staged = git_lines("diff", "--cached", "--name-only", cwd=repo)
        if not staged:
            err("显式模式（--explicit）下暂存区为空，已中止：请先逐个 "
                "`git add <路径>` 确认范围后再跑（禁止用 git add -A 盲加）。")
            return 1
        info(f"\n显式模式：跳过自动暂存，仅提交已暂存的 {len(staged)} 个文件。")
    else:
        info("\n暂存全部改动...")
        git("add", "-A", cwd=repo)
        ok("暂存完成。")

    if args.message.strip():
        proc = subprocess.run(
            ["git", "commit", "-m", subject],
            cwd=str(repo), capture_output=True, text=True, encoding="utf-8",
        )
    else:
        # 带正文提交：使用 heredoc 多行消息
        full_msg = f"{subject}\n\n{body}\n" if body else subject
        proc = subprocess.run(
            ["git", "commit", "-m", full_msg],
            cwd=str(repo), capture_output=True, text=True, encoding="utf-8",
        )
    print(proc.stdout.strip())
    if proc.returncode != 0:
        err(proc.stderr.strip())
        return 1
    ok("提交完成。")

    # 5. 推送
    if args.no_push:
        info("已按 --no-push 跳过推送。")
        return 0
    info("推送到远程...")
    push = subprocess.run(
        ["git", "push"], cwd=str(repo), capture_output=True, text=True, encoding="utf-8",
    )
    print(push.stdout.strip())
    if push.returncode != 0:
        warn(push.stderr.strip())
        err("推送失败，请检查远程分支/凭据。")
        return 1
    ok("推送完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
