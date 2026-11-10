# 更新日志

`scanner-config` skill 的所有版本变动统一记录在此。格式参考 Keep a Changelog。

## [1.0.0] - 2026-11-10

### 新增

- SKILL.md v1.0.0：扫码枪 SH-5000-GHD（底座集成 Eport E10 串口联网服务器，TCP-SERVER 8899）网络配置与排障方法论。设备模型必读（工控机静态 192.168.1.230 不要动、目标 192.168.1.220:8899、恢复出厂回 10.10.100.10、DHCP 断网时回落 APIPA 169.254.173.207 由 MAC 决定不变）、配置 API 速查表（POST /cmd + msg=JSON，RC=0 才成功；必须临时文件 + curl --data-binary 发送）与典型场景 SOP（probe/get/set/verify/full 流程）。
- scripts/ScannerTool.ps1：一键网络配置与诊断工具（PowerShell 5.1 兼容、ASCII only），支持 probe / get / backup / set / verify / full 六动作：候选 IP 探测 + 网卡报表、SYS 配置读写、E10.xml 备份、改 IP 后 ping+TCP+回读三重验证、备份→改→验证→config.ini 同步→清理一键跑通；内置恢复出厂后的常见候选地址与 MAC 前缀 ARP 监看。
- references/api-cheatsheet.md：E10 配置 API 速查（CID 10001~10008 / 20001~20003、SYS 节字段实测清单、100-continue 干扰坑、curl --data-binary 发送范式）。

### 说明

- 设备账密 admin/admin 为 Eport E10 出厂默认值，非公司凭据；文档中的 192.168.1.x 为现场 commissioned 拓扑（skill 语境必需）。
- 入库时 frontmatter `name` 由 `Scanner Config` 更正为 `scanner-config`（kebab-case ASCII 硬校验要求）。
