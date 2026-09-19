# 软件卸载清理 - 变更记录

## v1.1.0（2026-09-19）

### 修复（代码审计，未发布即修）

- **致命**：移除 PS 7 专属三元运算符 `? :`，脚本在 PowerShell 5.1 下原本无法解析
- **致命**：去重键 `$foundApps.DisplayNames` 属性名写错，去重永不生效 → 同一卸载程序会被重复运行，改为 DisplayName+InstallLocation+UninstallString 复合键
- **致命**：MSI 分支在 EXE 分支之后，`msiexec.exe /X` 永远走 EXE 分支 → MSI 分支提前，并优先使用 `QuietUninstallString`
- `-Force` 参数声明了但从未使用 → 补上执行前 y/N 确认（`-Force` 跳过；AI 调用必加）
- Stage 3 只扫 `-InstallPath` 子目录，本体漏扫；且 `-InstallPath` 本体从未加入清理 → 本体纳入候选与清理
- 进程匹配去掉 `MainWindowTitle`（误杀标题含关键词的浏览器），改匹配描述/产品/厂商
- 卸载名单移除 `setup.exe`（误跑可能变成安装/修复）
- `$matches` 被用作普通变量名 → 改名，避免覆盖 `-match` 自动变量
- `UninstallString` 含 `/I{guid}` 会触发修复/安装 → 改写为 `/X`
- 带空格路径解析：引号包裹优先，否则取最长已存在前缀（原来直接按空格切，`C:\Program Files\...` 必断）
- 快捷方式删除补 `-Recurse`（开始菜单项可能是目录）
- 安装路径去尾部 `\`，消除 `Git\` 与 `Git` 重复项；删除按路径深度降序（先子后父，防父删后子报 FAIL）

### 新增

- 阶段 4：停止并删除关联 Windows 服务（`sc.exe delete`）
- 阶段 5：注销关联计划任务
- 阶段 8 扩展到桌面快捷方式（公共桌面 + 用户桌面）
- 卸载程序 120s 超时熔断（防 NSIS 系弹 GUI 导致 `-Wait` 无限挂起），超时终止后继续文件清理
- 目录删除 3 次重试（应对文件锁延迟释放）
- 短关键词（<4 字符）拦截：非 `-Force` 直接中止
- 全部用户路径走环境变量（`$env:APPDATA` 等），不再写死 `C:\Users\user`
- 汇总计数 + 失败退出码 1（供 AI 判定）+ 非管理员失败提示提权
- 同一卸载程序跨阶段去重（`$RanUninstallers`）

## v1.0.0（2026-09-19）

### 新增

- 通用 PowerShell 卸载脚本 `scripts/uninstall.ps1`
  - 六阶段流程：查杀进程 → 注册表卸载 → 独立卸载程序 → 清理文件 → 清理注册表 → 清理开始菜单
  - `-DryRun` 预览模式
  - `-Force` 跳过确认
  - `-KeepConfig` 保留配置目录
  - `-InstallPath` / `-ExtraPaths` 扩展清理范围
- SKILL.md 文档：触发词、工作流程、参数速查、典型场景、安全红线
- 来源场景：ViewTurboLite 断电后白屏，手动卸载残留导致重装无效
