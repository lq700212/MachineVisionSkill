# -*- coding: utf-8 -*-
"""ViewTurbo 每日签到脚本（纯 HTTP API，无需浏览器）。

用法:
    python checkin.py                 # 按 accounts.json 逐个账号签到
    python checkin.py --json          # 额外输出 JSON 结果（供其他程序解析）

流程（每个账号）:
    1. POST /appuser/reglogin        登录（密码先 MD5），拿 token
    2. GET  /appuser/checkin_status  查今日是否已签
    3. 若未签: POST /appuser/checkin 签到领流量
    4. GET  /appuser/userinfo        查剩余流量，回显结果
"""
import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://api.viewturbo.info"
COMMON_QS = "platform=web&cur_version=0.0.0&deviceinfo=&lang=hk&code=Others"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0 Safari/537.36")
RETRY = 3


def api(method, path, token="", body=None, timeout=20):
    """调 API，带重试；返回 (ok, dict|str)。"""
    url = f"{BASE}{path}?{COMMON_QS}"
    if token:
        url += f"&token={token}"
    data = json.dumps(body).encode() if body is not None else None
    last_err = ""
    for i in range(RETRY):
        try:
            req = urllib.request.Request(url, data=data, headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Referer": "https://web.vtpro.xyz/",
                "User-Agent": UA,
            }, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return True, json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001 - 网络抖动/SSL EOF 等都重试
            last_err = str(e)[:150]
            time.sleep(2 * (i + 1))
    return False, last_err


def fmt_bytes(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} GB"


def checkin_one(email, password):
    """单个账号签到，返回结果 dict。"""
    res = {"email": email, "ok": False, "msg": ""}
    ok, r = api("POST", "/appuser/reglogin",
                body={"email": email,
                      "password": hashlib.md5(password.encode()).hexdigest()})
    if not ok:
        res["msg"] = f"登录请求失败: {r}"
        return res
    if r.get("code") != 0:
        res["msg"] = f"登录失败: {r.get('msg')}"
        return res
    token = r["data"]["token"]

    ok, r = api("GET", "/appuser/checkin_status", token=token)
    if not ok or r.get("code") != 0:
        res["msg"] = f"查询签到状态失败: {r if not ok else r.get('msg')}"
        return res
    st = r["data"]
    res["consecutive"] = st.get("consecutive")
    if st.get("checked_today"):
        res["msg"] = "今日已签到，无需重复领取"
    else:
        ok, r = api("POST", "/appuser/checkin", token=token, body={})
        if not ok:
            res["msg"] = f"签到请求失败: {r}"
            return res
        if r.get("code") != 0:
            res["msg"] = f"签到失败: {r.get('msg')}"
            return res
        data = r.get("data") or {}
        reward = data.get("reward_bytes") or data.get("reward") or ""
        res["msg"] = f"签到成功，领取 {fmt_bytes(reward)}" if reward else "签到成功"

    ok, r = api("GET", "/appuser/userinfo", token=token)
    if ok and r.get("code") == 0:
        res["traffic"] = fmt_bytes(r["data"].get("transfer", 0))
    res["ok"] = True
    return res


def main():
    ap = argparse.ArgumentParser(description="ViewTurbo 每日签到")
    ap.add_argument("--json", action="store_true", help="额外输出 JSON 结果")
    args = ap.parse_args()

    cfg_path = Path(__file__).with_name("accounts.json")
    accounts = json.loads(cfg_path.read_text(encoding="utf-8"))["accounts"]

    results = []
    print(f"共 {len(accounts)} 个账号，开始签到...\n")
    for i, acc in enumerate(accounts, 1):
        email = acc["email"]
        print(f"[{i}/{len(accounts)}] {email} ...")
        try:
            r = checkin_one(email, acc["password"])
        except Exception as e:  # noqa: BLE001 - 保证一个账号异常不影响其他
            r = {"email": email, "ok": False, "msg": f"异常: {e}"}
        results.append(r)
        traffic = f"，剩余流量 {r['traffic']}" if r.get("traffic") else ""
        mark = "OK " if r["ok"] else "FAIL"
        print(f"  [{mark}] {r['msg']}{traffic}\n")
        time.sleep(1)

    ok_n = sum(1 for r in results if r["ok"])
    print(f"完成: {ok_n}/{len(results)} 个账号签到成功")
    if args.json:
        print(json.dumps(results, ensure_ascii=False))
    return 0 if ok_n == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
