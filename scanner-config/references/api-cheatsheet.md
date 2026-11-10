# Eport E10 配置 API 速查表

## 通信方式

- 传输：`POST http://<设备IP>/cmd`
- 认证：HTTP Basic（默认 `admin` / `admin`）
- 头：`Content-Type: application/json; charset=utf-8`，必须带 `-H "Expect:"`（避免 100-continue 干扰）
- 请求体：`msg=<JSON 字符串>`，**必须写入临时文件后用 `curl --data-binary @file` 发送**
  （PowerShell 内联传参会丢失引号，设备收到坏 JSON 时会回显请求头而非执行）

## 命令码（CID）

| CID  | 方向 | 含义         | PL 请求体                                      | 响应 |
| ---- | ---- | ------------ | ---------------------------------------------- | ---- |
| 10001 | →   | 读运行状态   | `[]`                                            | 10002 |
| 10003 | →   | 读配置       | `["SYS"]`（节名数组，节名区分大小写：`SYS`）     | 10004 |
| 10005 | →   | 写配置       | `{"SYS":{...完整节对象...}}`                     | 10006（**可能是单元素数组** `[{"CID":10006,"RC":0}]`） |
| 20001 | →   | 重载配置生效 | `{}`                                            | 20002 |
| 20003 | →   | 整机重启     | `{}`                                            | 20004 |
| 10007 | →   | 取配置 XML   | `[]`                                            | 10008，形如 `{"PL":{"URL":"E10.xml"}}` |

响应统一格式：`{"CID":..,"RC":0,"PL":..}`，`RC=0` 才是成功。

## SYS 节字段（E10 实测）

```json
{
  "User": "admin", "Password": "admin",
  "DhcpEn": 0,
  "IpAddr": "192.168.1.220", "GateWay": "0.0.0.0", "Mask": "255.255.255.0",
  "Dns": "223.5.5.5", "HostName": "Eport-E10",
  "TelnetEn": 0, "TelnetPort": 23, "TelnetEcho": 1,
  "WebEn": 1, "WebPort": 80, "ModbusTime": 0,
  "Ipv6En": 0, "Ipv6Addr": "", "Ipv6DhcpEn": 0,
  "ntpEn": 0, "ntpServer": "", "ntpPort": 0, "ntpGMT": 8,
  "Longitude": 0, "Latitude": 0, "Lang": "CN"
}
```

写配置铁律：**10003 读出整包 → 只改 DhcpEn / IpAddr / Mask → 整包写回 10005 → 回读校验 → 20001 重载**。

## 时序特征（实测）

- SET 成功后设备**不会立刻断开**；发送 20001 重载后网络栈重启，**两个地址同时掉线约 45 秒**，然后以新 IP 上线。
- 若 SET 响应为**空**（连接被掐断）：该次写入**很可能未落盘**。设备下次重启会回退旧配置（DHCP→APIPA 169.254.173.207）。此时应等设备重新上线后**重新执行写入**，而不是反复试探新地址。

## 地址速查

| 地址              | 含义                                       |
| ----------------- | ------------------------------------------ |
| 192.168.1.220     | 目标静态 IP（当前生效）                     |
| 169.254.173.207   | DHCP 无服务器时的 APIPA 地址（由 MAC 决定） |
| 10.10.100.10      | 恢复出厂后的默认 IP                         |
| 40-2A-8F-BA-91-35 | 设备 MAC（ARP 监视用）                      |

## 相关文件

- 软件配置：`config/config.ini` → `[Scanner]` 节（`TcpIp` / `TcpPort` / `Mode=Tcp`）
- 软件日志：`log/<yyyy-MM-dd>/log.txt`，成功连接的关键字：`扫码枪(TCP)已连接`
- 备份目录：`config/scanner-backup/`（`E10_baseline_20261110.xml` 为改 IP 前的原始完整配置）
