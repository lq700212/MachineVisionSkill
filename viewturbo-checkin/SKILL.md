---
name: viewturbo-checkin
description: ViewTurbo 每日签到领流量。Use when user says ViewTurbo签到、每天签到、领取流量、checkin，或要求运行ViewTurbo签到脚本。
---

# ViewTurbo 每日签到

对 `accounts.json` 中的每个账号调用官方 API 完成每日签到（签到领 100MB），纯 HTTP，无需浏览器。

## 执行

```bash
python "C:\Users\Administrator\.config\opencode\skills\viewturbo-checkin\checkin.py"
```

脚本逐个账号输出结果，最后汇总成功数。全部成功时退出码为 0，有失败时为 1。

## 文件说明（都在本 skill 目录下）

- `checkin.py` — 签到脚本：登录（密码 MD5）→ 查 `checkin_status` →
  未签则调 `checkin` → 查 `userinfo` 回显剩余流量。单个账号异常不影响其他，
  网络抖动自动重试 3 次。
- `accounts.json` — 账号配置，格式 `{"accounts": [{"email": ..., "password": ...}]}`。
  增删账号只改这个文件。含明文密码，注意保管，不要外传，不要提交到 git。
  新克隆仓库后复制 `accounts.json.example` 为 `accounts.json` 再填真实账号。

## 接口备忘（api.viewturbo.info，通用 query `platform=web&cur_version=0.0.0&deviceinfo=&lang=hk&code=Others`）

- `POST /appuser/reglogin` body `{"email","password(md5)"}` → `data.token`
- `GET /appuser/checkin_status?token=` → `data.checked_today` 今日是否已签
- `POST /appuser/checkin?token=` body `{}` → 签到；重复签返回 `code 7 今天已签到`
- `GET /appuser/userinfo?token=` → `data.transfer` 剩余流量（字节）

## 备注

- 2026-09-11 验证：4 个账号全部签到成功（`lq700212@gmail.com` 当天已处于已签状态）。
- 若某账号返回"用户名或密码错误"，让用户核对该账号的邮箱/密码后更新 `accounts.json`。
