# -*- coding: utf-8 -*-
"""extract_images：从 opencode 会话数据库提取用户上传的图片。

场景：用户在对话里发了现场照片/截图，但工作目录里没有原图。
本脚本直接从 opencode.db 的 session_message.data 里解出 base64 图片。

用法：
  python extract_images.py --outdir assets/raw
  python extract_images.py --session-id ses_xxx --outdir assets/raw
  python extract_images.py --latest 3 --outdir assets/raw
  python extract_images.py --list

默认数据库：~/.local/share/opencode/opencode.db
默认会话：环境变量 OPENCODE_SESSION_ID
"""
import argparse
import base64
import json
import os
import sqlite3
import sys

DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".local", "share", "opencode", "opencode.db")
EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


def find_db(explicit):
    if explicit:
        return explicit
    candidates = [
        DEFAULT_DB,
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "opencode", "opencode.db"),
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def iter_images(db, session_id, min_bytes):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cur = con.cursor()
    sql = "select id, seq, data from session_message"
    params = ()
    if session_id:
        sql += " where session_id=?"
        params = (session_id,)
    sql += " order by seq"
    for mid, seq, data in cur.execute(sql, params):
        try:
            obj = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            continue
        for idx, f in enumerate(obj.get("files", [])):
            mime = (f.get("mime") or "").lower()
            b64 = f.get("data") or ""
            if not mime.startswith("image/") or not b64:
                continue
            try:
                raw = base64.b64decode(b64)
            except Exception:
                continue
            if len(raw) < min_bytes:
                continue
            yield mid, seq, idx, mime, f.get("name", ""), raw
    con.close()


def main():
    ap = argparse.ArgumentParser(description="从 opencode 会话提取图片")
    ap.add_argument("--db", help="opencode.db 路径")
    ap.add_argument("--session-id", default=os.environ.get("OPENCODE_SESSION_ID", ""),
                    help="会话 ID，默认取环境变量")
    ap.add_argument("--outdir", default="assets/raw", help="输出目录")
    ap.add_argument("--latest", type=int, default=0, help="只取最近 N 张（0=全部）")
    ap.add_argument("--min-bytes", type=int, default=5000, help="过滤小图，默认 5000 字节")
    ap.add_argument("--list", action="store_true", help="只列出，不保存")
    args = ap.parse_args()

    db = find_db(args.db)
    if not db or not os.path.exists(db):
        print(f"[FAIL] 找不到 opencode.db：{db or '未找到'}")
        return 1

    items = list(iter_images(db, args.session_id, args.min_bytes))
    if not items:
        print("[WARN] 没有找到图片。检查 --session-id，或图片不在数据库里。")
        return 2
    if args.latest > 0:
        items = items[-args.latest:]

    print(f"[OK] 数据库：{db}")
    print(f"[OK] 会话：{args.session_id or '全部'}")
    print(f"[OK] 图片：{len(items)} 张")

    if args.list:
        for mid, seq, idx, mime, name, raw in items:
            print(f"  seq={seq} idx={idx} {mime} {len(raw)}B name={name}")
        return 0

    os.makedirs(args.outdir, exist_ok=True)
    saved = []
    for mid, seq, idx, mime, name, raw in items:
        ext = EXT.get(mime, ".bin")
        out = os.path.join(args.outdir, f"img_{seq:03d}_{idx}{ext}")
        with open(out, "wb") as f:
            f.write(raw)
        saved.append(out)
        print(f"  [SAVE] {out}  {len(raw)}B  {mime}")

    print(f"[OK] 已保存 {len(saved)} 张到 {os.path.abspath(args.outdir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
