---
name: 软件卸载清理
description: 通用软件彻底卸载与残留清理：终止进程→运行卸载程序→清服务/计划任务→清理安装目录/AppData/注册表/快捷方式。当用户说"卸载XX软件"、"删干净XX"、"XX软件白屏/打不开想重装"、"彻底清理XX残留"、"软件异常要重装"时使用。脚本为主，支持 -DryRun 预览模式，AI 执行必须加 -Force。
---

# 通用软件彻底卸载清理

## 背景

软件断电/异常退出后可能配置损坏，表现为白屏、打不开、卡死等问题。常规卸载经常残留配置文件和注册表项，重装后问题依旧。本 skill 提供**一键彻底清理**：终止进程 → 运行卸载程序 → 清服务/计划任务 → 删除安装目录 → 清理 AppData/ProgramData → 清理注册表 → 清理快捷方式。

## 触发词

- 卸载 XX 软件 / 删干净 XX
- XX 软件白屏 / 打不开 / 异常，想重装
- 彻底清理 XX 残留 / 删掉 XX 所有文件
- XX 软件配置损坏，重装也不行

## 工具与位置

- 脚本：`scripts/uninstall.ps1`（与本 SKILL.md 同目录）
- 依赖：仅 PowerShell 5.1+，无第三方库

## 工作流程（AI 必须遵守）

### 第一步：预览（DryRun）

**必须先跑 DryRun 确认范围，再执行清理。**

```powershell
powershell -ExecutionPolicy Bypass -File "<skill目录>\scripts\uninstall.ps1" -Name "<软件名>" -DryRun
```

可选参数：
- `-InstallPath "D:\Program Files\XXX"` 已知安装路径时直接指定（本体也会被清理）
- `-ExtraPaths "路径1","路径2"` 额外清理路径

将 DryRun 输出展示给用户，确认 [WILL] 列表无误。

### 第二步：执行清理

用户确认后执行（**AI 调用必须加 `-Force`**，否则脚本内的 `Read-Host` 确认在非交互环境会挂起）：

```powershell
powershell -ExecutionPolicy Bypass -File "<skill目录>\scripts\uninstall.ps1" -Name "<软件名>" -Force
```

如需保留配置文件：加 `-KeepConfig`。

### 第三步：验证

脚本执行后检查：
- 进程是否已终止（`Get-Process | Where-Object {$_.ProcessName -like "*XX*"}`）
- 安装目录是否已删除（`Test-Path`）
- 注册表是否已清理

### 第四步：提示重装

告知用户：
- 已清理的项目列表
- 可以重新安装
- 安装后建议先不要修改高级设置（如全局代理模式），确认基础功能正常再调整

## 脚本参数速查

| 参数 | 作用 | 必填 |
| --- | --- | --- |
| `-Name "关键词"` | 软件名称关键词，支持多个，建议 ≥4 字符 | 是 |
| `-InstallPath "路径"` | 已知安装目录（本体也会被清理） | 否 |
| `-ExtraPaths "路径"` | 额外清理目录 | 否 |
| `-DryRun` | 预览模式，不执行操作 | 否 |
| `-Force` | 跳过执行前 y/N 确认（AI 调用必加） | 否 |
| `-KeepConfig` | 保留 AppData 配置目录 | 否 |

## 脚本执行流程（v1.1.0，8 阶段）

```
阶段 1: 查找关联进程 → 终止（进程名/描述/产品/厂商匹配，不按窗口标题，避免误杀浏览器）
阶段 2: 注册表查已安装 → 运行卸载程序（优先级 QuietUninstallString > MSI /X > EXE + 静默参数，120s 超时熔断）
阶段 3: 扫描独立卸载程序（unins000.exe 等，跳过已运行过的；名单排除 setup.exe 防误装）
阶段 4: 停止并删除关联 Windows 服务（sc.exe delete）
阶段 5: 注销关联计划任务
阶段 6: 清理残留文件（安装目录 + AppData + ProgramData，删除带 3 次重试）
阶段 7: 清理注册表残留（Uninstall 键 + Software 键，HKLM 需管理员）
阶段 8: 清理开始菜单与桌面快捷方式
```

## 典型场景

### 场景 1：ViewTurboLite 断电后白屏

```powershell
# 预览
powershell -ExecutionPolicy Bypass -File "...\uninstall.ps1" -Name "ViewTurboLite" -DryRun
# 执行
powershell -ExecutionPolicy Bypass -File "...\uninstall.ps1" -Name "ViewTurboLite" -Force
# 结果：进程终止 + D:\Program Files\ViewTurboLite 删除 + AppData\Roaming\VIEWTURBO PTE. LTD 删除 + 注册表清理
```

### 场景 2：已知安装路径的软件

```powershell
powershell -ExecutionPolicy Bypass -File "...\uninstall.ps1" -Name "SomeApp" -InstallPath "D:\SomeApp" -DryRun
```

### 场景 3：保留配置重装

```powershell
powershell -ExecutionPolicy Bypass -File "...\uninstall.ps1" -Name "SomeApp" -KeepConfig -Force
```

## 安全红线

1. **先 DryRun 后执行**：AI 必须先跑 DryRun 让用户确认范围。
2. **AI 执行必加 `-Force`**：脚本默认有 y/N 确认，非交互环境会挂起；DryRun 已确认过范围，执行时加 `-Force` 跳过。
3. **关键词 ≥4 字符**：过短关键词（如 `App`、`助手`两字）误伤面大；非 `-Force` 模式下脚本直接中止，AI 必须换更长的关键词。
4. **保留配置可选**：加 `-KeepConfig` 保留 AppData 下的配置和数据。
5. **强制终止有风险**：`Stop-Process -Force` 会丢失未保存数据，但白屏场景下通常无影响。
6. **管理员权限**：HKLM 注册表与服务清理需管理员；普通用户运行时对应步骤报 FAIL，脚本汇总会提示提权重跑。
7. **NSIS 系卸载程序**：静默参数可能不生效而弹出 GUI，脚本 120s 超时后自动终止并继续文件清理，属预期行为。
8. **不碰系统组件**：脚本只处理第三方用户级软件，不涉及 Windows 更新、驱动等。
