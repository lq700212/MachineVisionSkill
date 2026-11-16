#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
resolve_galaxy.py —— 定位 Uiverse galaxy 组件库，找不到就自动 git clone 到本地。

为什么要有这个脚本
------------------
做 UI 设计稿前必须查阅 galaxy 的真实组件（按钮/卡片/表单/开关/加载…），
但 galaxy 在每台机器上的位置不一定相同；每次让 AI 全盘搜索既慢又浪费上下文。
本脚本把"查找 → 验证 → 缓存 → 兜底克隆"固化成一条命令：

    1) --path 显式指定（人工兜底，优先级最高）
    2) SKILL 目录下 config.json 里的 galaxyPath（缓存命中，最快）
    3) 常见候选路径逐个探测（D:\\galaxy / E:\\Project\\galaxy ...）
    4) D:、E: 盘顶层两层的受限扫描（目录名 == galaxy）
    5) 全都没有 → git clone 到 D:\\galaxy（失败自动换 gh-proxy 镜像）

找到后把绝对路径写回 config.json，下次直接命中缓存。

用法
----
    python resolve_galaxy.py                 # 自动解析并打印 JSON
    python resolve_galaxy.py --json          # 同上（机器可读，默认就是 JSON）
    python resolve_galaxy.py --path E:\\Project\\galaxy   # 人工指定
    python resolve_galaxy.py --no-clone      # 只查找，不自动克隆
    python resolve_galaxy.py --refresh       # 忽略缓存重新查找

输出（stdout，UTF-8 JSON）
--------------------------
    {"ok": true, "path": "E:\\\\Project\\\\galaxy", "source": "cache",
     "components": 3802, "categories": ["Buttons", ...], "config": "...config.json"}

    ok=false 时带 "error" 字段，退出码 1。
"""

import argparse
import io
import json
import os
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# 常量：路径与判定标准
# ---------------------------------------------------------------------------

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_DIR, "config.json")

# galaxy 仓库一定有的分类目录（用来识别"这确实是 galaxy，而不是同名空目录"）
REQUIRED_CATEGORIES = ["Buttons", "Cards", "Inputs"]

# 判定有效的下限：组件 html 文件数。官方仓库 3000+，留足余量防误判。
MIN_COMPONENTS = 100

# 缓存未命中时的候选探测路径（按命中概率排序，全部做存在性判断，不报错）
CANDIDATE_PATHS = [
    os.path.join("D:\\", "galaxy"),
    os.path.join("E:\\Project", "galaxy"),
    os.path.join("D:\\Project", "galaxy"),
    os.path.join("E:\\", "galaxy"),
    os.path.join("D:\\", "Project", "galaxy"),
    os.path.join(os.path.expanduser("~"), "galaxy"),
    os.path.join(os.path.expanduser("~"), "Documents", "galaxy"),
    os.path.join(os.path.expanduser("~"), "Desktop", "galaxy"),
]

# 受限扫描的根目录与深度（只扫两层，避免全盘遍历卡死）
SCAN_ROOTS = ["D:\\", "E:\\"]
SCAN_MAX_DEPTH = 2
# 扫描时跳过的目录名（体积大 / 无关 / 无权限）
SCAN_SKIP = {
    "Windows", "Program Files", "Program Files (x86)", "ProgramData",
    "$Recycle.Bin", "System Volume Information", "node_modules", ".git",
    "AppData", "Recovery", "PerfLogs", "MSOCache",
}

# clone 目标与镜像（直连 GitHub 在部分机器不通，镜像兜底）
CLONE_TARGET = os.path.join("D:\\", "galaxy")
CLONE_URLS = [
    "https://github.com/uiverse-io/galaxy.git",
    "https://gh-proxy.com/https://github.com/uiverse-io/galaxy.git",
    "https://ghfast.top/https://github.com/uiverse-io/galaxy.git",
]

# 跳过扫描的盘符（光驱/网络盘常见）
SKIP_DRIVES = {"A:", "B:"}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def eprint(*args):
    """把进度信息打到 stderr，保证 stdout 永远是干净 JSON。"""
    print(*args, file=sys.stderr)


def count_components(root):
    """统计 root 下所有分类目录里的 .html 组件数量。"""
    total = 0
    for name in os.listdir(root):
        sub = os.path.join(root, name)
        if not os.path.isdir(sub) or name.startswith("."):
            continue
        try:
            total += sum(1 for f in os.listdir(sub) if f.lower().endswith(".html"))
        except OSError:
            continue
    return total


def validate_galaxy(path):
    """
    判断一个目录是不是可用的 galaxy 库。
    必须同时满足：目录存在 + 至少 3 个官方分类目录 + 组件总数 >= MIN_COMPONENTS。
    返回 (ok: bool, components: int, categories: list[str])
    """
    if not path or not os.path.isdir(path):
        return False, 0, []
    try:
        names = set(os.listdir(path))
    except OSError:
        return False, 0, []
    hit = [c for c in REQUIRED_CATEGORIES if c in names]
    if len(hit) < 3:
        return False, 0, []
    components = count_components(path)
    if components < MIN_COMPONENTS:
        return False, components, hit
    categories = sorted(
        n for n in names
        if os.path.isdir(os.path.join(path, n)) and not n.startswith(".")
    )
    return True, components, categories


# ---------------------------------------------------------------------------
# 配置文件读写（原子写，UTF-8，兼容不存在/坏 JSON）
# ---------------------------------------------------------------------------

def load_config(path=None):
    path = path or CONFIG_PATH
    if not os.path.isfile(path):
        return {}
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (ValueError, OSError):
        # 配置坏了不该阻断流程，直接当空配置重新生成
        return {}


def save_config(data, path=None):
    """先写临时文件再 os.replace，避免写到一半断电留下半个 JSON。"""
    path = path or CONFIG_PATH
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 各查找阶段
# ---------------------------------------------------------------------------

def from_cache(config):
    """阶段 2：读缓存路径并验证（目录被删/改名后缓存会失效，必须复验）。"""
    p = config.get("galaxyPath")
    if not p:
        return None
    ok, n, cats = validate_galaxy(p)
    if ok:
        return {"path": p, "source": "cache", "components": n, "categories": cats}
    eprint("[resolve] 缓存路径失效，继续查找：" + str(p))
    return None


def scan_drives():
    """
    阶段 4：受限扫描。只扫 D:/E: 顶层两层，目录名精确等于 galaxy（不区分大小写）。
    这是"用户 clone 到别处但没告诉我"场景的兜底，比全盘遍历快几个数量级。
    """
    for root in SCAN_ROOTS:
        if not os.path.isdir(root):
            continue
        try:
            level1 = list(os.scandir(root))
        except OSError:
            continue
        for e1 in level1:
            if not e1.is_dir(follow_symlinks=False):
                continue
            if e1.name in SCAN_SKIP or e1.name.startswith("$"):
                continue
            if e1.name.lower() == "galaxy":
                ok, n, cats = validate_galaxy(e1.path)
                if ok:
                    return {"path": e1.path, "source": "scan", "components": n, "categories": cats}
            if SCAN_MAX_DEPTH < 2:
                continue
            try:
                level2 = list(os.scandir(e1.path))
            except OSError:
                continue
            for e2 in level2:
                if not e2.is_dir(follow_symlinks=False):
                    continue
                if e2.name in SCAN_SKIP or e2.name.startswith("$"):
                    continue
                if e2.name.lower() == "galaxy":
                    ok, n, cats = validate_galaxy(e2.path)
                    if ok:
                        return {"path": e2.path, "source": "scan", "components": n, "categories": cats}
    return None


def clone_galaxy(target):
    """
    阶段 5：git clone。--depth 1 只拉最新提交（仓库约 10MB，浅克隆最快）。
    逐个尝试直连与镜像，任一成功即返回；全失败返回 None。
    """
    if not os.path.isdir("D:\\"):
        # D 盘不存在时退到用户目录，保证脚本仍然可用
        target = os.path.join(os.path.expanduser("~"), "galaxy")
    if os.path.exists(target):
        # 目标已存在但验证不通过（比如半截克隆）：不删用户目录，换一个带时间戳的名字
        target = target + "_" + time.strftime("%Y%m%d%H%M%S")
    parent = os.path.dirname(target)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)

    for url in CLONE_URLS:
        eprint("[resolve] 尝试 clone：" + url)
        cmd = ["git", "clone", "--depth", "1", url, target]
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as ex:
            eprint("[resolve] clone 异常：" + str(ex))
            continue
        if r.returncode == 0:
            ok, n, cats = validate_galaxy(target)
            if ok:
                return {"path": target, "source": "clone", "components": n, "categories": cats}
            eprint("[resolve] clone 完成但内容校验不通过：" + target)
        else:
            tail = r.stdout.decode("utf-8", "replace").strip().splitlines()[-3:]
            eprint("[resolve] clone 失败：" + " | ".join(tail))
    return None


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="定位/克隆 galaxy 组件库并写入缓存")
    ap.add_argument("--path", help="显式指定 galaxy 目录（最高优先级）")
    ap.add_argument("--no-clone", action="store_true", help="只查找，不自动 git clone")
    ap.add_argument("--refresh", action="store_true", help="忽略 config.json 缓存重新查找")
    ap.add_argument("--config", default=CONFIG_PATH, help="配置文件路径（默认 skill/config.json）")
    args = ap.parse_args()

    config = load_config(args.config)

    result = None

    # 1) 人工显式指定
    if args.path:
        ok, n, cats = validate_galaxy(args.path)
        if not ok:
            print(json.dumps({
                "ok": False,
                "error": "指定的路径不是有效 galaxy 库（需含 Buttons/Cards/Inputs 且组件数>=%d）：%s" % (MIN_COMPONENTS, args.path),
            }, ensure_ascii=False, indent=2))
            return 1
        result = {"path": os.path.abspath(args.path), "source": "arg", "components": n, "categories": cats}

    # 2) 缓存
    if not result and not args.refresh:
        result = from_cache(config)

    # 3) 候选路径
    if not result:
        for cand in CANDIDATE_PATHS:
            ok, n, cats = validate_galaxy(cand)
            if ok:
                result = {"path": os.path.abspath(cand), "source": "candidate", "components": n, "categories": cats}
                break

    # 4) 受限扫描
    if not result:
        result = scan_drives()

    # 5) 克隆
    if not result and not args.no_clone:
        result = clone_galaxy(CLONE_TARGET)

    if not result:
        print(json.dumps({
            "ok": False,
            "error": "未找到 galaxy 组件库，且自动 clone 失败。请手动执行：git clone --depth 1 https://github.com/uiverse-io/galaxy.git D:\\galaxy，然后运行 --path D:\\galaxy",
        }, ensure_ascii=False, indent=2))
        return 1

    # 成功后写回缓存（保留其它字段，便于将来扩展）
    config["galaxyPath"] = result["path"]
    config["updatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
    config["lastSource"] = result["source"]
    config["componentCount"] = result["components"]
    try:
        save_config(config, args.config)
    except OSError as ex:
        eprint("[resolve] 缓存写入失败（不影响本次使用）：" + str(ex))

    result["ok"] = True
    result["config"] = args.config
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
