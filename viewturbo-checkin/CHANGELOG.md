# 更新日志

`viewturbo-checkin` skill 的所有版本变动统一记录在此。格式参考 Keep a Changelog。

## [Unreleased]

### API 域名被断，签到切换到客户端 HTTP 管理面板入口（2026-11-01）

- **现象**：`https://api.viewturbo.info` 从本机（中国大陆家宽）全断——直连 TCP 可达但 TLS 握手挂起（SNI 阻断特征，多 IP 反复超时）；OpenCode 内置浏览器走既有代理路径则返回 `net::ERR_TUNNEL_CONNECTION_FAILED`。官网 `web.vtpro.xyz` 反而能开，但 SPA 的唯一 API base 就是 `api.viewturbo.info`（扒 bundle 确认无备用域名），UI 登录同样发不出去。与"网站加反爬"无关。
- **解法**：查明 ViewTurbo 桌面客户端自身的管理面板本来就是同一套 `/appuser/*` 接口，地址在 `%APPDATA%/VIEWTURBO PTE. LTD/ViewTurboLite/shared_preferences.json` 的 `flutter.api`（明文 HTTP 国内 IP，本次为 `http://120.233.70.97:8099`）。`checkin.py` 的 `BASE` 换成该地址，其余逻辑不变。实测 reglogin / checkin_status / checkin / userinfo 全正常。
- 验证：5 个账号全部签到成功（lq700212@gmail.com 35.26 GB / 542780477@qq.com 7.08 GB / 2976205258@qq.com 4.40 GB / 3223759551@qq.com 4.66 GB / lq700212@163.com 1.71 GB），退出码 0。
- **排查technique 备忘**：诊断时曾怀疑客户端 TUN 截流，实际 `flutter.tunMode=false` 且注册表/WinHTTP/环境变量均无代理——TLS 交互挂起的锅在链路层 SNI 干扰。浏览器 `network.get` 看 `failure=ERR_TUNNEL_*` 是区分"代理拒绝"与"直连超时"的关键证据。
- 若日后 8099 失效：以最新客户端 shared_preferences.json 的 `flutter.api` 为准更新 BASE，勿回退被断的 HTTPS 域名。

### checkin.py 联网与签到容错两处防御（2026-10-31）

- **强制 IPv4**：模块加载期把 `socket.getaddrinfo` 重定向为恒传 `socket.AF_INET`。根因：本机 IPv6 出口不通（TLS 握手挂起），而 `api.viewturbo.info` 有 AAAA 记录，默认双栈会优先 IPv6 导致所有请求超时——只改解析不改任何请求代码，全部 API 调用一并受益。
- **签到 code==7 视作成功**：`/checkin` 返回 code=7（"今天已签到"）不再记为失败。原因：状态查询可能滞后于服务器时区，重复触发时被误报"签到失败"；现报"今日已签到，无需重复领取"，退出语义与 code==0 相同。
- 自查：`accounts.json`（真实凭据）始终被根 `.gitignore` 忽略，仓库只收 `accounts.json.example` 模板——本次提交前 `git ls-files` 复核无凭据文件。

### 历史说明

- 本文件为随本次提交新建；此前版本变动未集中记录，历史以 git log 为准。
