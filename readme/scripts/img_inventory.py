# -*- coding: utf-8 -*-
"""
img_inventory.py — 文档图片资产盘点（readme skill · 第 2 步脚本）

干什么：扫仓库所有 markdown 的图片引用（![](…) 与 <img src>），与磁盘实际
  图片文件做差集，输出三段：
    [DEAD-REF]  文档引用了但磁盘没有 → 必修（md 渲染 404）
    [ORPHAN]    磁盘有但无任何文档引用 → 与用户确认删除或补引用
    [OK]        两头对齐计数
  相对路径一律按**该 md 所在目录**解析（README 引 docs/images/x.png 与
  docs 手册引 images/x.png 两种口径天然都支持）；外链 http(s) 不盘点。

用法：
    python img_inventory.py [repo根]            # 默认当前目录

退出码：0=无死引用；1=有死引用；2=环境错误。
结论行统一 [RESULT: OK] / [RESULT: NG]，AI 只读这一行定去留。
"""
import os
import re
import sys

# ---------- 输出编码（Windows 控制台 GBK 防乱码：统一 UTF-8 stdout） ----------
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

IMG_RX = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
IMG_HTML_RX = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)

# 常见依赖/构建产物目录——盘点时一律跳过（防库存虚胖与误判孤儿；
# 语言无关混扫安全：遇到新类型噪音目录就往这里加）
# resources/Resources：GUI 程序资源目录族（.NET/WPF/Android 的 exe 图标等），
# 文档配图不往这里放——AgingTestSystem 实测 app.png 常驻误报 ORPHAN
EXCLUDE_DIRS = {
    ".git", ".vs", ".idea", ".codegraph",
    "bin", "obj", "build", "dist", "target", "out",
    "node_modules", "vendor", "__pycache__", ".venv", "site-packages",
    "runner", "packages",
    "resources", "Resources",
}

dead_refs = []   # (md_file, line_no, path)
md_refs = set()  # 全仓库被引用的规范化磁盘路径集合
REPO = ""


def norm(path):
    return os.path.normpath(path).lower()


def resolve(base_dir, ref):
    """md 内引用按 md 所在目录解析；带 http 跳过返回 None。"""
    if ref.startswith("http://") or ref.startswith("https://"):
        return None
    return norm(os.path.join(base_dir, ref))


def collect_md_files(root):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        # 排除隐藏目录与依赖/构建产物目录（EXCLUDE_DIRS）
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.lower().endswith(".md"):
                found.append(os.path.join(dirpath, fn))
    return found


def scan_md(path):
    base = os.path.dirname(path)
    with open(path, "r", encoding="utf-8-sig", errors="strict") as f:
        for ln, line in enumerate(f, 1):
            for m in IMG_RX.finditer(line):
                target = resolve(base, m.group(1).strip())
                if target is None:
                    continue
                md_refs.add(target)
                if not os.path.isfile(target):
                    dead_refs.append((os.path.relpath(path, REPO), ln, m.group(1).strip()))
            for m in IMG_HTML_RX.finditer(line):
                target = resolve(base, m.group(1).strip())
                if target is None:
                    continue
                md_refs.add(target)
                if not os.path.isfile(target):
                    dead_refs.append((os.path.relpath(path, REPO), ln, m.group(1).strip()))


def collect_img_files(root):
    imgs = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
                imgs.append(norm(os.path.join(dirpath, fn)))
    return imgs


def main():
    global REPO
    REPO = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")

    if not os.path.isdir(REPO):
        print(f"[ERR] 仓库不存在: {REPO}")
        print("RESULT: NG")
        return 2

    mds = collect_md_files(REPO)
    if not mds:
        print(f"[WARN] 未找到任何 markdown: {REPO}")
        print("RESULT: OK")
        return 0
    for p in mds:
        try:
            scan_md(p)
        except UnicodeDecodeError:
            print(f"[ERR] 非 UTF-8 markdown（先转码再盘）: {rel(p)}")
            print("RESULT: NG")
            return 2

    img_files = collect_img_files(REPO)
    orphans = [p for p in img_files if p not in md_refs]

    print(f"仓库: {REPO}")
    print(f"markdown 数: {len(mds)}；被引用图片: {len([r for r in md_refs if os.path.isfile(r)])}；磁盘图片: {len(img_files)}")
    if dead_refs:
        print(f"\n[DEAD-REF] 死引用 {len(dead_refs)} 处（必修）：")
        for md, ln, ref in dead_refs:
            print(f"  {md}:{ln} -> {ref}")
    if orphans:
        print(f"\n[ORPHAN] 无引用图片 {len(orphans)} 张（与用户确认删除或补引用）：")
        for p in orphans:
            print(f"  {os.path.relpath(p, REPO)}")

    if dead_refs:
        print("\nRESULT: NG")
        return 1
    print("\nRESULT: OK")
    return 0


def rel(p):
    return os.path.relpath(p, REPO)


if __name__ == "__main__":
    try:
        code = main()
    except Exception as ex:  # 环境异常兜底（缺权限等）
        print(f"[ERR] {ex}")
        print("RESULT: NG")
        code = 2
    sys.exit(code)
