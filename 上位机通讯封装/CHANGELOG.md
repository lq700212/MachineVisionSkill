# 更新日志

`上位机通讯封装` skill 的所有版本变动统一记录在此。格式参考 Keep a Changelog。

## [Unreleased]

- 新增 SKILL.md §4.1 重连活锁铁律（HuaJiVision V4.4.70 开机血泪）：固定周期触发＋按完成时间算的时间退避＋离线单次执行耗时超周期三条凑齐即活锁（症状：重连日志停在"已连续 1 次"、ping 通但唯独该链路不自愈）；解法二选一：固定周期触发走旁路（去重保留）或触发周期 ≥ 2×（退避＋最坏执行耗时）；自查口诀同步入库。
- 同步 SKILL.md §七自检清单：新增第 11 条重连无活锁（见 §4.1），原第 11 条顺延为第 12 条。

## [v1.0.0] - 2026-09-05（基线入库）

- 现有 `SKILL.md` 首次纳入本仓库 git 追踪（白名单放行），内容零改动。
- 范式要点：三层架构（服务层/编排层/UI 层）与 UI 线程零网络 IO；BeginConnect + WaitOne
  手动超时、无回调式 EndConnect；连接锁串行化 + 读写失败即断连 + 边沿事件；
  Dispose 限时抢锁 + 锁外强断网；后台心跳 + 节流静默自动重连；事件回 UI 用
  BeginInvoke + IsDisposed 保护；指令/寄存器配置化与保守失败判定；交付自检 11 条。
- 提炼来源：CommandCenter（相机 + PLC 命令中心）、AgingTestSystem（老化测试）
  两个现场跑过的 Windows 上位机项目（.NET Framework 4.7.2 / WinForms / C# 7.3）。
