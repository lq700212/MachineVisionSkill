---
name: scanner-config
description: 扫码枪/SH-5000/Eport-E10 串口联网模块的网络配置与排障。当需要修改扫码枪 IP、配置 8899 端口、排查扫码枪连接超时/离线、处理 169.254.x.x 地址、恢复出厂后重建配置时使用。Use when configuring the network scanner gun (Eport-E10 serial-to-Ethernet module in the scanner base), changing its IP, or troubleshooting scanner connection timeouts.
---

# 扫码枪网络配置（Eport-E10 模块）

## 设备模型（必读）

- 扫码枪 SH-5000-GHD 通过串口接入**底座内集成的 Eport E10 串口联网服务器**，E10 以 TCP-SERVER 监听 **8899** 桥接串口数据。用户看不到独立的"E10 盒子"。
- 网络拓扑：`工控机(192.168.1.230) ─ biaze 独立供电扩展坞 ─ 交换机 ─ 产线设备(耦合器 .20 等)`，扫码枪底座也接在 biaze 上。
- 工控机网卡 commissioned 配置：**静态 192.168.1.230/24**（ifIndex 通常为 20）。**不要改动它**，探测其他网段用临时辅助 IP，用完删除。
- 扫码枪目标地址：**192.168.1.220:8899**，软件配置在 `config/config.ini` 的 `[Scanner]` 节，软件**启动时**读取。
- E10 异常状态地址：DHCP 开启且网内无 DHCP 服务器时自动回落 APIPA **169.254.173.207**（由 MAC 40-2A-8F-BA-91-35 决定，地址确定不变）；**恢复出厂后为 10.10.100.10**。
- Web 管理端口 80，HTTP Basic 认证，默认账号 **admin/admin**。

## 配置 API 速查

`POST http://<ip>/cmd`，body 为 `msg=<JSON>`（Content-Type: application/json; charset=utf-8）：

| CID  | 含义       | PL                                          |
| ---- | ---------- | ------------------------------------------- |
| 10003 | 读配置     | `["SYS"]`                                    |
| 10005 | 写配置     | `{"SYS":{...完整对象...}}`                    |
| 20001 | 重载生效   | `{}`                                         |
| 20003 | 整机重启   | `{}`                                         |
| 10007 | 取配置 XML | `[]` → 响应告知 XML 文件名（E10.xml）          |

- 完整配置 XML：`GET http://<ip>/E10.xml`（带 Basic 认证）。
- 响应格式 `{"CID":..,"RC":0,"PL":..}`；**SET 的响应是单元素数组**（如 `[{"CID":10006,"RC":0}]`）。
- **每次写操作必须 RC=0 才算成功；响应为空 = 写入可能未落盘**。

## 铁律（本次事故的教训）

1. **必须整包写回**：先用 10003 读出完整 SYS 对象，只改 `DhcpEn/IpAddr/Mask` 三个字段，再整体写回。不要发部分字段。
2. **写完必须回读验证（10003）+ 发 20001 重载**。重载时设备短暂双地址掉线，约 **45 秒**后在新地址上线。
3. **响应为空/中断 ≠ 设备死了**：那可能是配置未落盘且网络栈重启了。设备重启后会**回退到旧配置**（DHCP→169.254.173.207），先探测旧地址再决定下一步，不要盲目重写。
4. **curl 请求体必须写临时文件用 `--data-binary @file` 发送**。PowerShell 内联传参会丢引号，设备收到坏请求会回显请求头而不是执行。必须加 `-H "Expect:"`。
5. **ping 的源 IP 很重要**：耦合器等 PLC 设备会忽略非登记来源 IP 的探测（表现为"来自 x.x.x.x 的回复：无法访问目标主机"）。最终验证必须以 commissioned 的 192.168.1.230 为源。**辅助 IP 只加给其他网段**（169.254.x、10.10.100.x），不影响 192.168.1.x 的源选择。
6. **网卡改静态后，169.254/10.10.100 的路由消失**——设备在那些地址时"ping 不到"≠离线，需临时加同网段辅助 IP（/16、/24）再测。
7. **ARP 缓存有残留**：旧 IP→MAC 条目不会自动消失，会造成"设备上线"的假象。按 MAC 找设备前先 `arp -d *`，并排除已知残留条目。
8. 网段安静≠网络死了：该网段没有周期广播流量，收包数为 0 是正常的。判断存活用"ARP 应答 + ping"，不要只看 RX 计数。
9. 模块"卡死"恢复阶梯：底座断电 10 秒 → 看 biaze 扩展坞上扫码枪口的绿灯（亮=有电有链路）→ 仍不通则**按 RESET 孔 5 秒恢复出厂**（上线为 10.10.100.10，工控机需临时加 10.10.100.100/24 去接管，然后用备份重建配置）。
10. 改完 `config.ini` 必须**重启 CureStation 软件**才生效。最终验收看 `log\<yyyy-MM-dd>\log.txt` 中出现"扫码枪(TCP)已连接 192.168.1.220:8899"。

## 标准流程（优先用脚本，已脚本化）

脚本：`scripts/ScannerTool.ps1`（PowerShell 5.1 兼容，英文输出避免编码问题）

```powershell
# 一键全流程：探测→备份→改IP→重载→轮询→验证→更新config.ini→清理网卡
powershell -ExecutionPolicy Bypass -File scripts/ScannerTool.ps1 -Action full -NewIp 192.168.1.220

# 只探测（候选地址全试一遍 + 网卡状态）
powershell -ExecutionPolicy Bypass -File scripts/ScannerTool.ps1 -Action probe

# 只读配置
powershell -ExecutionPolicy Bypass -File scripts/ScannerTool.ps1 -Action get -Ip 192.168.1.220

# 备份配置（改设备前必做）
powershell -ExecutionPolicy Bypass -File scripts/ScannerTool.ps1 -Action backup -Ip 192.168.1.220

# 只验证（ping + 8899 端口 + 配置回读 + 网卡状态）
powershell -ExecutionPolicy Bypass -File scripts/ScannerTool.ps1 -Action verify -Ip 192.168.1.220
```

`full` 内置流程：候选地址探测（192.168.1.220 / 169.254.173.207 / 10.10.100.10）→ E10.xml + SYS 备份到 `config/scanner-backup/` → 读改写 SYS（DHCP off）→ 回读校验 → 20001 重载 → 轮询新 IP（≤120s）→ 8899 端口测试 → 更新 config.ini → 网卡临时 IP 清理 → 最终验证。

## 手工兜底（脚本不可用时的 curl 模板）

```sh
# 读配置（请求体先写入文件 msg.txt：msg={"CID":10003,"PL":["SYS"]}）
curl -s -u admin:admin -H "Content-Type: application/json; charset=utf-8" -H "Expect:" --data-binary @msg.txt http://169.254.173.207/cmd

# 备份完整配置 XML
curl -s -u admin:admin http://169.254.173.207/E10.xml -o E10.xml

# 重载使配置生效（msg={"CID":20001,"PL":{}}）
curl -s -u admin:admin -H "Content-Type: application/json; charset=utf-8" -H "Expect:" --data-binary @reload.txt http://169.254.173.207/cmd
```

写 SYS 的请求体结构（在脚本外手工构造时）：

```json
msg={"CID":10005,"PL":{"SYS":{ ...10003 读到的完整对象，仅改 DhcpEn:0, IpAddr, Mask... }}}
```

## 恢复出厂后重建

1. 工控机临时加 `10.10.100.100/24`（脚本 `-Action probe` 会提示）。
2. 备份目录 `config/scanner-backup/` 取最新 XML/JSON 作为基准。
3. 用 10003 读出厂 SYS → 按铁律 1 整包写回（DhcpEn=0、IpAddr=目标 IP、Mask=255.255.255.0，其余字段以备份为准）→ 回读 → 20001 重载 → 验证 8899。
4. 确认 `config.ini` 与目标一致，重启 CureStation。

## 参考

- `references/api-cheatsheet.md`：API 明细、响应样例、本次基线配置快照说明。
- 基线备份：`config/scanner-backup/E10_baseline_20261110.xml`（改 IP 前的原始完整配置）。
