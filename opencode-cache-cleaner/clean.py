# -*- coding: utf-8 -*-
"""
清理 opencode 中残留的项目缓存（opencode 项目目录缓存清理工具）。

【用途】
opencode 会把每个打开过的项目登记进本地 SQLite 数据库（默认 ~/.local/share/opencode/opencode.db），
并在 snapshot/ 目录留存项目快照。当某个项目在磁盘上被改名 / 移动 / 删除后，
opencode 的项目列表里仍会残留旧的 project / project_directory 记录（指向已不存在的路径），
界面上继续显示旧项目名。本脚本负责把这些残留记录与对应快照清理掉。

【清理内容（对应关系）】
  1. 数据库 project 表            -> 选中的项目行
  2. 数据库 project_directory 表  -> 选中项目的目录行
  3. 磁盘 snapshot/<project_id>/  -> 选中项目的快照目录（目录名 == 数据库里的项目 id）
  4. （可选）孤儿快照             -> snapshot/ 下目录名不属于任何现存项目 = 残留，可一并清理

【安全设计】
  - 删除前会把待删记录完整导出备份到 %TEMP%/opencode-cleaner-backups/，可随时手动恢复。
  - global 项目（id='global'）永远不可删（它是 opencode 的全局工作区，不是真实项目）。
  - 只删除选中项目的记录与快照，绝不触碰其他项目的会话 / 消息 / 事件。
  - 数据库可能正被正在运行的 opencode 占用：连接带 busy_timeout 等待写锁，
    若 opencode 长期持有写锁而失败，会提示先关闭 opencode 再执行。

【用法】
  python clean.py --list                     # 只列出所有项目，不做任何修改
  python clean.py                            # 交互模式：列出所有项目 -> 让你选择 -> 确认后清理
  python clean.py <id1> [id2 ...]            # 直接清理指定项目 id（可多个，适合 AI 调用）
  python clean.py --orphans                  # 只清理孤儿快照（列出后确认）
  python clean.py --list --orphans           # 列出项目 + 列出孤儿快照

【AI 集成建议】
  AI 应先用 `python clean.py --list` 把项目列表展示给用户，询问用户要清理哪个，
  再用 `python clean.py <project_id>` 直接执行，最后验证结果并提示重启 opencode。

【数据库路径探测】
  依次尝试：
    1. 命令行 --db 参数
    2. 环境变量 OPENCODE_DATA（如设置则视为数据目录）
    3. ~/.local/share/opencode/opencode.db（Windows 下为用户目录下同名路径）
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile

# 让中文输出在 Windows 控制台（GBK 默认）下不乱码：把 stdout 重配为 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BACKUP_DIR = os.path.join(tempfile.gettempdir(), "opencode-cleaner-backups")
GLOBAL_PROJECT_ID = "global"


def find_db_path(cli_db: str) -> str:
    """按优先级探测 opencode 数据库路径，找不到就报错退出。"""
    if cli_db:
        if os.path.isfile(cli_db):
            return cli_db
        print(f"[错误] 指定的数据库文件不存在：{cli_db}")
        sys.exit(1)

    data_dir = os.environ.get("OPENCODE_DATA")
    if data_dir:
        candidate = os.path.join(data_dir, "opencode.db")
        if os.path.isfile(candidate):
            return candidate

    candidate = os.path.join(
        os.path.expanduser("~"), ".local", "share", "opencode", "opencode.db"
    )
    if os.path.isfile(candidate):
        return candidate

    print(
        "[错误] 找不到 opencode 数据库。请确认 opencode 已使用过，\n"
        "       或用 --db <完整路径> 显式指定 opencode.db。"
    )
    sys.exit(1)


def connect(db_path: str):
    """打开数据库连接，设置写锁等待（opencode 可能正占用数据库）。"""
    con = sqlite3.connect(db_path, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    return con


def load_projects(con) -> list:
    """读回 project 表里除 global 外的全部项目。"""
    cur = con.cursor()
    cur.execute(
        "SELECT id, worktree, vcs, name, icon_color, time_updated "
        "FROM project WHERE id != ? ORDER BY time_updated DESC",
        (GLOBAL_PROJECT_ID,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def load_project_dirs(con, project_id: str) -> list:
    """读回指定项目的 project_directory 行。"""
    cur = con.cursor()
    cur.execute("SELECT * FROM project_directory WHERE project_id=?", (project_id,))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def display_name(proj: dict) -> str:
    """项目显示名：优先 name 字段，否则取 worktree 最后一段目录名。"""
    if proj.get("name"):
        return proj["name"]
    wt = proj.get("worktree") or ""
    return wt.rstrip("/\\").split("/")[-1] if wt else "(无路径)"


def snapshot_dir_for(project_id: str, data_dir: str) -> str:
    """返回某项目对应的快照目录（即使不存在也返回路径，便于判断）。"""
    return os.path.join(data_dir, "snapshot", project_id)


def list_snapshot_ids(data_dir: str) -> list:
    """列出 snapshot/ 下所有目录名（这些名字是历史项目 id）。"""
    snap_root = os.path.join(data_dir, "snapshot")
    if not os.path.isdir(snap_root):
        return []
    return [d for d in os.listdir(snap_root)
            if os.path.isdir(os.path.join(snap_root, d))]


def find_orphan_snapshots(con, data_dir: str) -> list:
    """找孤儿快照：snapshot/ 下目录名不在现存项目 id 集合里的。"""
    cur = con.cursor()
    cur.execute("SELECT id FROM project")
    known = {r[0] for r in cur.fetchall()}
    snap_ids = list_snapshot_ids(data_dir)
    return [s for s in snap_ids if s not in known]


def backup_rows(project: dict, dirs: list) -> str:
    """把待删记录导出备份为 json，返回备份文件路径。"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = os.path.join(BACKUP_DIR, f"project_{project['id']}_{stamp}.json")
    payload = {"project": project, "project_directory": dirs,
               "backup_time": stamp}
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return fname


def do_clean(con, data_dir: str, project_ids: list) -> dict:
    """执行清理：备份 + 删数据库记录 + 删快照目录。返回结果统计。"""
    result = {"backup_files": [], "deleted_project": [], "deleted_dirs": [],
              "deleted_snapshot": [], "skipped": []}
    cur = con.cursor()
    for pid in project_ids:
        if pid == GLOBAL_PROJECT_ID:
            result["skipped"].append(f"{pid} (global 项目不可删)")
            continue
        cur.execute("SELECT * FROM project WHERE id=?", (pid,))
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        if not row:
            result["skipped"].append(f"{pid} (数据库中不存在)")
            continue
        proj = dict(zip(cols, row))
        dirs = load_project_dirs(con, pid)

        # 1. 先备份，保证可恢复
        bak = backup_rows(proj, dirs)
        result["backup_files"].append(bak)

        # 2. 删数据库记录（同一事务）
        cur.execute("DELETE FROM project WHERE id=?", (pid,))
        cur.execute("DELETE FROM project_directory WHERE project_id=?", (pid,))
        con.commit()

        # 3. 删磁盘快照目录（如果存在）
        snap = snapshot_dir_for(pid, data_dir)
        if os.path.isdir(snap):
            shutil.rmtree(snap, ignore_errors=True)
            if os.path.isdir(snap):
                result["skipped"].append(f"{pid} (快照目录删除失败: {snap})")
            else:
                result["deleted_snapshot"].append(snap)
        else:
            result["skipped"].append(f"{pid} (无快照目录)")

        result["deleted_project"].append(pid)
        result["deleted_dirs"].extend([d.get("directory") or d.get("project_id")
                                       for d in dirs])
    return result


def do_clean_orphans(con, data_dir: str, snap_ids: list) -> list:
    """删除指定的孤儿快照目录，返回删除成功的列表。"""
    removed = []
    for sid in snap_ids:
        p = snapshot_dir_for(sid, data_dir)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
            if os.path.isdir(p):
                print(f"  [失败] 无法删除：{p}")
            else:
                removed.append(p)
    return removed


def pretty_list(projects: list) -> str:
    """把项目列表格式化为易读的多行文本（供展示 / 落日志）。"""
    if not projects:
        return "（没有可清理的项目）"
    lines = []
    for i, p in enumerate(projects, 1):
        snap_flag = "有快照" if p.get("_has_snapshot") else "无快照"
        lines.append(
            f"{i}. [{p['id']}] {display_name(p)}  ({p.get('worktree') or '无路径'})  {snap_flag}"
        )
    return "\n".join(lines)


def parse_selection(text: str, count: int) -> list:
    """解析用户输入的选择（1,3 或 1-3 或 all），返回下标列表。"""
    text = text.strip().lower()
    if text in ("all", "*", "全部"):
        return list(range(count))
    if not text:
        return []
    idxs = set()
    for part in re.split(r"[,，;；\s]+", text):
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            if a.isdigit() and b.isdigit():
                idxs.update(range(int(a) - 1, int(b)))
                continue
        if part.isdigit():
            n = int(part)
            if 1 <= n <= count:
                idxs.add(n - 1)
    return sorted(idxs)


def interactive(con, data_dir: str):
    """交互模式：列出所有项目 -> 询问选择 -> 确认 -> 清理。"""
    projects = load_projects(con)
    if not projects:
        print("当前没有可清理的项目（project 表为空）。")
        return
    snap_ids = set(list_snapshot_ids(data_dir))
    for p in projects:
        p["_has_snapshot"] = p["id"] in snap_ids

    print("=" * 60)
    print("opencode 项目列表：")
    print(pretty_list(projects))
    print("-" * 60)
    print("请输入要清理的项目序号（可多选，如：1 或 1,3 或 1-3；输入 all 清理全部；")
    print("回车跳过 = 不清理，直接进入孤儿快照检查）")

    choice = input("选择 > ").strip()
    idxs = parse_selection(choice, len(projects))
    selected = [projects[i] for i in idxs]

    if selected:
        print("\n即将清理以下项目（记录会先备份）：")
        for p in selected:
            print(f"  - [{p['id']}] {display_name(p)}  {p.get('worktree')}")
        confirm = input("确认删除？(y/N) > ").strip().lower()
        if confirm not in ("y", "yes"):
            print("已取消。")
            return
        result = do_clean(con, data_dir, [p["id"] for p in selected])
        print("\n[清理完成]")
        for f in result["backup_files"]:
            print(f"  备份: {f}")
        for pid in result["deleted_project"]:
            print(f"  已删除项目: {pid}")
        for s in result["deleted_snapshot"]:
            print(f"  已删除快照: {s}")
        for s in result["skipped"]:
            print(f"  跳过: {s}")

    # 孤儿快照检查
    orphans = find_orphan_snapshots(con, data_dir)
    if orphans:
        print("\n检测到孤儿快照（无对应项目记录的 snapshot 目录）：")
        for o in orphans:
            print(f"  - {o}")
        c2 = input("是否一并清理这些孤儿快照？(y/N) > ").strip().lower()
        if c2 in ("y", "yes"):
            removed = do_clean_orphans(con, data_dir, orphans)
            for r in removed:
                print(f"  已删除孤儿快照: {r}")
    else:
        print("\n没有孤儿快照。")


def main():
    parser = argparse.ArgumentParser(description="清理 opencode 残留项目缓存")
    parser.add_argument("ids", nargs="*", help="要清理的项目 id（可多个）")
    parser.add_argument("--list", action="store_true", help="只列出项目，不修改")
    parser.add_argument("--orphans", action="store_true",
                        help="只清理孤儿快照（无项目记录的 snapshot 目录）")
    parser.add_argument("--db", default=None, help="显式指定 opencode.db 路径")
    parser.add_argument("--yes", action="store_true",
                        help="参数模式直接执行，不再二次确认（谨慎使用）")
    args = parser.parse_args()

    db_path = find_db_path(args.db)
    data_dir = os.path.dirname(db_path)
    con = connect(db_path)

    try:
        projects = load_projects(con)
        if args.list:
            snap_ids = set(list_snapshot_ids(data_dir))
            for p in projects:
                p["_has_snapshot"] = p["id"] in snap_ids
            print("opencode 项目列表：")
            print(pretty_list(projects))
            if args.orphans:
                orphans = find_orphan_snapshots(con, data_dir)
                print("\n孤儿快照：", orphans if orphans else "（无）")
            return

        if args.orphans:
            orphans = find_orphan_snapshots(con, data_dir)
            if not orphans:
                print("没有孤儿快照。")
                return
            print("孤儿快照：")
            for o in orphans:
                print("  -", o)
            if args.yes:
                removed = do_clean_orphans(con, data_dir, orphans)
                for r in removed:
                    print("已删除:", r)
            else:
                c = input("确认删除这些孤儿快照？(y/N) > ").strip().lower()
                if c in ("y", "yes"):
                    removed = do_clean_orphans(con, data_dir, orphans)
                    for r in removed:
                        print("已删除:", r)
                else:
                    print("已取消。")
            return

        if args.ids:
            result = do_clean(con, data_dir, args.ids)
            print("[清理完成]")
            for f in result["backup_files"]:
                print(f"  备份: {f}")
            for pid in result["deleted_project"]:
                print(f"  已删除项目: {pid}")
            for s in result["deleted_snapshot"]:
                print(f"  已删除快照: {s}")
            for s in result["skipped"]:
                print(f"  跳过: {s}")
            return

        # 无参数：交互模式
        interactive(con, data_dir)
    finally:
        con.close()


if __name__ == "__main__":
    main()