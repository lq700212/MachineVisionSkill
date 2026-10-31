# 更新日志

`viewturbo-checkin` skill 的所有版本变动统一记录在此。格式参考 Keep a Changelog。

## [Unreleased]

### checkin.py 联网与签到容错两处防御（2026-10-31）

- **强制 IPv4**：模块加载期把 `socket.getaddrinfo` 重定向为恒传 `socket.AF_INET`。根因：本机 IPv6 出口不通（TLS 握手挂起），而 `api.viewturbo.info` 有 AAAA 记录，默认双栈会优先 IPv6 导致所有请求超时——只改解析不改任何请求代码，全部 API 调用一并受益。
- **签到 code==7 视作成功**：`/checkin` 返回 code=7（"今天已签到"）不再记为失败。原因：状态查询可能滞后于服务器时区，重复触发时被误报"签到失败"；现报"今日已签到，无需重复领取"，退出语义与 code==0 相同。
- 自查：`accounts.json`（真实凭据）始终被根 `.gitignore` 忽略，仓库只收 `accounts.json.example` 模板——本次提交前 `git ls-files` 复核无凭据文件。

### 历史说明

- 本文件为随本次提交新建；此前版本变动未集中记录，历史以 git log 为准。
