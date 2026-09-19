<#
.SYNOPSIS
    通用软件彻底卸载脚本 - 终止进程 / 运行卸载程序 / 清服务与计划任务 / 清理文件与注册表
.DESCRIPTION
    按名称关键词搜索已安装软件，依次执行：
    1. 查找并终止关联进程（进程名/描述/产品/厂商匹配）
    2. 注册表查找已安装信息，优先 QuietUninstallString，运行卸载程序（EXE/MSI，带超时熔断）
    3. 扫描独立卸载程序（unins000.exe 等，跳过已运行过的）
    4. 停止并删除关联 Windows 服务
    5. 注销关联计划任务
    6. 清理安装目录、AppData、ProgramData 残留（带重试）
    7. 清理注册表残留
    8. 清理开始菜单与桌面快捷方式
    支持 -DryRun 预览模式，不执行任何破坏性操作。
    仅依赖 Windows PowerShell 5.1+，无第三方库。
.PARAMETER Name
    软件名称关键词（支持多个）。匹配进程名、安装路径、注册表 DisplayName。
    建议长度 >= 4 个字符，过短关键词误伤面大（此时必须加 -Force 才放行）。
.PARAMETER InstallPath
    已知的安装目录（可选）。脚本会检查其中的卸载程序，并将其加入清理列表。
.PARAMETER ExtraPaths
    额外需要清理的目录列表（可选），如配置文件路径。
.PARAMETER DryRun
    预览模式：只显示将要执行的操作，不实际删除。
.PARAMETER Force
    跳过执行前的 y/N 确认。AI 非交互调用时必须加（否则 Read-Host 会挂起）。
.PARAMETER KeepConfig
    保留配置文件目录（AppData 下的目录）。
.EXAMPLE
    .\uninstall.ps1 -Name "ViewTurboLite" -DryRun
    .\uninstall.ps1 -Name "ViewTurboLite" -Force
    .\uninstall.ps1 -Name "SomeApp" -InstallPath "D:\Program Files\SomeApp" -Force
#>
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Name,

    [string]$InstallPath,
    [string[]]$ExtraPaths,
    [switch]$DryRun,
    [switch]$Force,
    [switch]$KeepConfig
)

$ErrorActionPreference = "SilentlyContinue"
$script:WillCount = 0
$script:OkCount = 0
$script:FailCount = 0
$script:SkipCount = 0
$script:RanUninstallers = @()

function Write-Ok {
    param([string]$Msg)
    $script:OkCount++
    Write-Host "  [OK]    $Msg" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Msg)
    $script:FailCount++
    Write-Host "  [FAIL]  $Msg" -ForegroundColor Red
}

function Write-Skip {
    param([string]$Msg)
    $script:SkipCount++
    Write-Host "  [SKIP]  $Msg" -ForegroundColor DarkGray
}

function Write-Action {
    param([string]$Msg)
    $script:WillCount++
    Write-Host "  [WILL]  $Msg" -ForegroundColor Yellow
}

function Invoke-IfNotDry {
    param([string]$Description, [scriptblock]$Action)
    if ($DryRun) {
        Write-Action $Description
        return
    }
    try {
        & $Action
        Write-Ok $Description
    }
    catch {
        Write-Fail "$Description - $($_.Exception.Message)"
    }
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# 解析卸载命令行 → @{ Exe = ...; Args = ... }
# 处理带空格路径（引号包裹 / 最长已存在前缀），避免 "C:\Program Files\..." 被截断
function Split-UninstallCommand {
    param([string]$Cmd)
    $Cmd = $Cmd.Trim()
    if ($Cmd -match '^\s*"([^"]+)"\s*(.*)$') {
        return @{ Exe = $Matches[1]; Args = $Matches[2].Trim() }
    }
    $tokens = @($Cmd -split '\s+')
    for ($i = $tokens.Count; $i -ge 1; $i--) {
        $cand = ($tokens[0..($i - 1)] -join ' ')
        if (($cand -like '*.exe' -or $cand -like '*.msi') -and (Test-Path -LiteralPath $cand)) {
            $rest = ''
            if ($i -lt $tokens.Count) { $rest = ($tokens[$i..($tokens.Count - 1)] -join ' ') }
            return @{ Exe = $cand; Args = $rest }
        }
    }
    $rest = ''
    if ($tokens.Count -gt 1) { $rest = ($tokens[1..($tokens.Count - 1)] -join ' ') }
    return @{ Exe = $tokens[0]; Args = $rest }
}

# 运行卸载程序，带超时熔断（防 NSIS 系弹 GUI 导致 -Wait 无限挂起）
function Invoke-Uninstaller {
    param([string]$Exe, [string]$Arguments, [string]$Label, [int]$TimeoutSec = 120)
    if ($DryRun) {
        Write-Action "运行卸载程序: $Label"
        return
    }
    $exeKey = $Exe.ToLower()
    if ($script:RanUninstallers -contains $exeKey) {
        Write-Skip "已运行过，跳过: $Label"
        return
    }
    $script:RanUninstallers += $exeKey
    if (($Exe -notmatch '^[A-Za-z0-9_\-\.]+\.exe$') -and (-not (Test-Path -LiteralPath $Exe))) {
        Write-Fail "卸载程序不存在: $Label"
        return
    }
    try {
        $p = Start-Process -FilePath $Exe -ArgumentList $Arguments -WindowStyle Hidden -PassThru -ErrorAction Stop
        $exited = $p.WaitForExit($TimeoutSec * 1000)
        if (-not $exited) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch { }
            Write-Ok "运行卸载程序(超时${TimeoutSec}s已终止，后续继续文件清理): $Label"
        }
        else {
            Start-Sleep -Seconds 2
            Write-Ok "运行卸载程序: $Label"
        }
    }
    catch {
        Write-Fail "运行卸载程序: $Label - $($_.Exception.Message)"
    }
}

# 删除目录，带 3 次重试（应对文件锁延迟释放）
function Remove-PathRetry {
    param([string]$Path, [string]$Label)
    if ($DryRun) {
        Write-Action "删除目录: $Label"
        return
    }
    $done = $false
    $err = ''
    for ($t = 1; $t -le 3; $t++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            $done = $true
            break
        }
        catch {
            $err = $_.Exception.Message
            Start-Sleep -Seconds 1
        }
    }
    if ($done) { Write-Ok "删除目录: $Label" }
    else { Write-Fail "删除目录: $Label - $err" }
}

# ── Banner ──
Write-Host ""
Write-Host "============================================" -ForegroundColor Magenta
Write-Host "  通用软件彻底卸载脚本 v1.1.0" -ForegroundColor Magenta
Write-Host "============================================" -ForegroundColor Magenta
if ($DryRun) {
    Write-Host "  ** 预览模式 (DryRun) - 不执行任何操作 **" -ForegroundColor Yellow
}
Write-Host ""

$allKeywords = @($Name)
Write-Host "搜索关键词: $($allKeywords -join ', ')" -ForegroundColor White
$isAdmin = Test-IsAdmin
if ($isAdmin) { Write-Host "权限: 管理员" -ForegroundColor Green }
else { Write-Host "权限: 普通用户（HKLM 注册表/服务清理可能失败，请考虑以管理员运行）" -ForegroundColor Yellow }
Write-Host ""

# ── 过短关键词拦截：误伤面大，非 -Force 直接中止 ──
$shortKws = @($allKeywords | Where-Object { $_.Length -lt 4 })
if ($shortKws.Count -gt 0 -and -not $Force -and -not $DryRun) {
    Write-Host "  [ABORT] 关键词太短（<$($shortKws -join ',')>），易误伤无关软件。" -ForegroundColor Red
    Write-Host "  请使用 >= 4 字符的关键词，或确认无误后加 -Force 放行。" -ForegroundColor Red
    exit 2
}

# ── 执行前确认（AI 非交互调用请加 -Force 跳过）──
if (-not $DryRun -and -not $Force) {
    Write-Host "即将对关键词 [$($allKeywords -join ', ')] 执行彻底卸载清理（含删除文件与注册表），继续? [y/N]: " -ForegroundColor Yellow -NoNewline
    $ans = Read-Host
    if ($ans -ne 'y' -and $ans -ne 'Y') {
        Write-Host "已取消。" -ForegroundColor DarkGray
        exit 0
    }
    Write-Host ""
}

# ── 路径基址（全部走环境变量，不写死用户名/盘符）──
$pf86 = ${env:ProgramFiles(x86)}
$progRoots = @($env:ProgramFiles, $pf86, "D:\Program Files", "D:\Program Files (x86)") |
    Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
$localAppData = $env:LOCALAPPDATA
$roamingAppData = $env:APPDATA
$localLow = Join-Path $env:USERPROFILE 'AppData\LocalLow'
$programData = $env:ProgramData
$dataRoots = @($localAppData, $roamingAppData, $localLow, $programData) |
    Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

# ═══════════════════════════════════════════
# 阶段 1：查找关联进程（进程名/描述/产品/厂商）
# 不按窗口标题匹配，避免误杀标题含关键词的浏览器等无关进程
# ═══════════════════════════════════════════
Write-Host "=== 阶段 1: 查找关联进程 ===" -ForegroundColor White

$foundProcesses = @()
$seenPids = @()
$allProcs = Get-Process -ErrorAction SilentlyContinue
foreach ($p in $allProcs) {
    if ($seenPids -contains $p.Id) { continue }
    $hit = $false
    try {
        foreach ($kw in $allKeywords) {
            if ($p.ProcessName -like "*$kw*") { $hit = $true; break }
            if ($p.Description -like "*$kw*") { $hit = $true; break }
            if ($p.Product -like "*$kw*") { $hit = $true; break }
            if ($p.Company -like "*$kw*") { $hit = $true; break }
        }
    }
    catch { continue }
    if ($hit) {
        $seenPids += $p.Id
        $foundProcesses += $p
    }
}

if ($foundProcesses.Count -eq 0) {
    Write-Skip "未找到运行中的进程"
}
else {
    foreach ($p in $foundProcesses) {
        $path = ""
        try { $path = $p.MainModule.FileName } catch { }
        $info = "PID=$($p.Id) Name=$($p.ProcessName)"
        if ($path) { $info += " Path=$path" }
        $pidCopy = $p.Id
        $infoCopy = $info
        Invoke-IfNotDry "终止进程 $infoCopy" {
            Stop-Process -Id $pidCopy -Force -ErrorAction Stop
            Start-Sleep -Milliseconds 500
        }
    }
}
Write-Host ""

# ═══════════════════════════════════════════
# 阶段 2：注册表查找已安装信息 → 运行卸载程序
# 优先级：QuietUninstallString > MSI(/X) > EXE；MSI 分支必须先于 EXE 判断
# ═══════════════════════════════════════════
Write-Host "=== 阶段 2: 查找已安装信息 ===" -ForegroundColor White

$uninstallRoots = @(
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
    "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall"
)

$foundApps = @()
$seenAppKeys = @()
foreach ($kw in $allKeywords) {
    foreach ($regRoot in $uninstallRoots) {
        if (-not (Test-Path -LiteralPath $regRoot)) { continue }
        $subs = Get-ChildItem -LiteralPath $regRoot -ErrorAction SilentlyContinue
        foreach ($sub in $subs) {
            $props = Get-ItemProperty -LiteralPath $sub.PSPath -ErrorAction SilentlyContinue
            if (-not $props.DisplayName) { continue }
            if ($props.DisplayName -notlike "*$kw*") { continue }
            $appKey = "$($props.DisplayName)`0$($props.InstallLocation)`0$($props.UninstallString)"
            if ($seenAppKeys -contains $appKey) { continue }
            $seenAppKeys += $appKey
            $foundApps += [PSCustomObject]@{
                DisplayName          = $props.DisplayName
                DisplayVersion       = $props.DisplayVersion
                InstallLocation      = $props.InstallLocation
                UninstallString      = $props.UninstallString
                QuietUninstallString = $props.QuietUninstallString
            }
        }
    }
}

if ($foundApps.Count -eq 0) {
    Write-Skip "注册表中未找到匹配的已安装程序"
}
else {
    foreach ($app in $foundApps) {
        Write-Host "  发现: $($app.DisplayName) v$($app.DisplayVersion)" -ForegroundColor White
        Write-Host "    安装位置: $($app.InstallLocation)" -ForegroundColor DarkGray
        Write-Host "    卸载命令: $($app.UninstallString)" -ForegroundColor DarkGray
        if ($app.QuietUninstallString) {
            Write-Host "    静默卸载: $($app.QuietUninstallString)" -ForegroundColor DarkGray
        }

        if ($app.QuietUninstallString) {
            $parts = Split-UninstallCommand $app.QuietUninstallString
            Invoke-Uninstaller -Exe $parts.Exe -Arguments $parts.Args -Label "$($app.DisplayName) [quiet]"
        }
        elseif ($app.UninstallString -match 'msiexec') {
            $guid = ""
            if ($app.UninstallString -match '\{[^}]+\}') { $guid = $Matches[0] }
            if ($guid) {
                Invoke-Uninstaller -Exe "msiexec.exe" -Arguments "/X $guid /quiet /norestart" -Label "$($app.DisplayName) [msi]"
            }
            else {
                # 无 GUID：把 /I(安装/修复) 改写为 /X(卸载)，防止误装
                $fixedArgs = $app.UninstallString -replace '(?i)/I(?=\s|$)', '/X'
                $parts = Split-UninstallCommand $fixedArgs
                Invoke-Uninstaller -Exe $parts.Exe -Arguments $parts.Args -Label "$($app.DisplayName) [msi-args]"
            }
        }
        elseif ($app.UninstallString) {
            $parts = Split-UninstallCommand $app.UninstallString
            $silentArgs = "$($parts.Args) /SILENT /SUPPRESSMSGBOXES /NORESTART".Trim()
            Invoke-Uninstaller -Exe $parts.Exe -Arguments $silentArgs -Label "$($app.DisplayName)"
        }
    }
}
Write-Host ""

# ═══════════════════════════════════════════
# 阶段 3：扫描独立卸载程序（跳过阶段 2 已运行过的）
# 候选目录 = -InstallPath 本体 + 注册表 InstallLocation 本体 + 关键词命中的子目录
# 名单排除 setup.exe（可能是安装器，误跑会重装）
# ═══════════════════════════════════════════
Write-Host "=== 阶段 3: 扫描独立卸载程序 ===" -ForegroundColor White

$uninstNames = @("unins000.exe", "unins001.exe", "uninstall.exe", "uninst.exe")
$candidateDirs = @()
if ($InstallPath -and (Test-Path -LiteralPath $InstallPath)) { $candidateDirs += $InstallPath }
foreach ($app in $foundApps) {
    if ($app.InstallLocation -and (Test-Path -LiteralPath $app.InstallLocation)) {
        $candidateDirs += $app.InstallLocation
    }
}
foreach ($root in $progRoots) {
    foreach ($kw in $allKeywords) {
        $dirs = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "*$kw*" }
        foreach ($d in $dirs) { $candidateDirs += $d.FullName }
    }
}
$candidateDirs = @($candidateDirs | Where-Object { $_ } | Select-Object -Unique)

$foundUninstallers = @()
foreach ($dir in $candidateDirs) {
    foreach ($uname in $uninstNames) {
        $uexe = Join-Path $dir $uname
        if ((Test-Path -LiteralPath $uexe) -and ($foundUninstallers -notcontains $uexe)) {
            $foundUninstallers += $uexe
        }
    }
}

if ($foundUninstallers.Count -eq 0) {
    Write-Skip "未找到独立卸载程序"
}
else {
    foreach ($uexe in $foundUninstallers) {
        Invoke-Uninstaller -Exe $uexe -Arguments "/SILENT /SUPPRESSMSGBOXES /NORESTART" -Label $uexe
    }
}
Write-Host ""

# ═══════════════════════════════════════════
# 阶段 4：停止并删除关联 Windows 服务（VPN/驱动类软件常驻）
# ═══════════════════════════════════════════
Write-Host "=== 阶段 4: 清理关联服务 ===" -ForegroundColor White

$foundServices = @()
$svcEnumOk = $true
try {
    $allSvcs = Get-Service -ErrorAction Stop
    foreach ($s in $allSvcs) {
        foreach ($kw in $allKeywords) {
            if (($s.Name -like "*$kw*") -or ($s.DisplayName -like "*$kw*")) {
                $foundServices += $s
                break
            }
        }
    }
}
catch {
    $svcEnumOk = $false
    Write-Skip "无法枚举服务：$($_.Exception.Message)"
}

if ($foundServices.Count -eq 0 -and $svcEnumOk) {
    Write-Skip "未找到关联服务"
}
else {
    foreach ($s in $foundServices) {
        $svcName = $s.Name
        $svcDisp = $s.DisplayName
        Invoke-IfNotDry "停止并删除服务: $svcDisp ($svcName)" {
            try { Stop-Service -Name $svcName -Force -ErrorAction Stop } catch { }
            Start-Sleep -Seconds 1
            & sc.exe delete "$svcName" | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "sc.exe delete 返回码 $LASTEXITCODE（可能需要管理员权限）" }
            Start-Sleep -Seconds 1
        }
    }
}
Write-Host ""

# ═══════════════════════════════════════════
# 阶段 5：注销关联计划任务
# ═══════════════════════════════════════════
Write-Host "=== 阶段 5: 清理计划任务 ===" -ForegroundColor White

$foundTasks = @()
$taskEnumOk = $true
try {
    $allTasks = Get-ScheduledTask -ErrorAction Stop
    foreach ($t in $allTasks) {
        foreach ($kw in $allKeywords) {
            if (($t.TaskName -like "*$kw*") -or ($t.TaskPath -like "*$kw*")) {
                $foundTasks += $t
                break
            }
        }
    }
}
catch {
    $taskEnumOk = $false
    Write-Skip "无法枚举计划任务：$($_.Exception.Message)"
}

if ($foundTasks.Count -eq 0 -and $taskEnumOk) {
    Write-Skip "未找到关联计划任务"
}
else {
    foreach ($t in $foundTasks) {
        $tName = $t.TaskName
        $tPath = $t.TaskPath
        Invoke-IfNotDry "注销计划任务: $tPath$tName" {
            Unregister-ScheduledTask -TaskName $tName -TaskPath $tPath -Confirm:$false -ErrorAction Stop
        }
    }
}
Write-Host ""

# ═══════════════════════════════════════════
# 阶段 6：清理残留文件与目录
# 含 -InstallPath 本体；厂商二级目录（如 Roaming\<厂商>\<软件>）一并覆盖
# ═══════════════════════════════════════════
Write-Host "=== 阶段 6: 清理残留文件 ===" -ForegroundColor White

$cleanupPaths = @()
foreach ($kw in $allKeywords) {
    foreach ($app in $foundApps) {
        if ($app.InstallLocation -and (Test-Path -LiteralPath $app.InstallLocation)) {
            $cleanupPaths += $app.InstallLocation.TrimEnd('\')
        }
    }
    foreach ($root in @($progRoots + $dataRoots)) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $hits = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "*$kw*" }
        foreach ($h in $hits) { $cleanupPaths += $h.FullName }
    }
}

if ($InstallPath) {
    if (Test-Path -LiteralPath $InstallPath) { $cleanupPaths += $InstallPath.TrimEnd('\') }
    else { Write-Skip "-InstallPath 不存在: $InstallPath" }
}

if ($ExtraPaths) {
    foreach ($xp in $ExtraPaths) {
        if (Test-Path -LiteralPath $xp) { $cleanupPaths += $xp.TrimEnd('\') }
        else { Write-Skip "-ExtraPaths 不存在: $xp" }
    }
}

# 厂商二级目录：Roaming\<厂商名>\<软件名>
foreach ($kw in $allKeywords) {
    if (-not (Test-Path -LiteralPath $roamingAppData)) { continue }
    $vendors = Get-ChildItem -LiteralPath $roamingAppData -Directory -ErrorAction SilentlyContinue
    foreach ($v in $vendors) {
        $subs = Get-ChildItem -LiteralPath $v.FullName -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "*$kw*" }
        foreach ($sd in $subs) { $cleanupPaths += $sd.FullName }
        if ($v.Name -like "*$kw*") { $cleanupPaths += $v.FullName }
    }
}

$cleanupPaths = @($cleanupPaths | Where-Object { $_ } | Select-Object -Unique | Sort-Object { $_.Length } -Descending)

if ($cleanupPaths.Count -eq 0) {
    Write-Skip "未找到残留目录"
}
else {
    foreach ($cp in $cleanupPaths) {
        if ($KeepConfig -and ($cp -like "$localAppData*" -or $cp -like "$roamingAppData*" -or $cp -like "$localLow*")) {
            Write-Skip "保留配置目录: $cp (--KeepConfig)"
            continue
        }
        Remove-PathRetry -Path $cp -Label $cp
    }
}
Write-Host ""

# ═══════════════════════════════════════════
# 阶段 7：清理注册表残留（HKLM 需管理员）
# ═══════════════════════════════════════════
Write-Host "=== 阶段 7: 清理注册表残留 ===" -ForegroundColor White

$regUninstRoots = @(
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
    "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall"
)
$regSoftRoots = @("HKLM:\Software", "HKCU:\Software")

$regCleaned = 0
foreach ($kw in $allKeywords) {
    foreach ($regRoot in $regUninstRoots) {
        if (-not (Test-Path -LiteralPath $regRoot)) { continue }
        $subs = Get-ChildItem -LiteralPath $regRoot -ErrorAction SilentlyContinue
        foreach ($sub in $subs) {
            $props = Get-ItemProperty -LiteralPath $sub.PSPath -ErrorAction SilentlyContinue
            if ($props.DisplayName -like "*$kw*") {
                $rp = $sub.PSPath
                $rn = $props.DisplayName
                Invoke-IfNotDry "删除注册表项: $rp ($rn)" {
                    Remove-Item -LiteralPath $rp -Recurse -Force -ErrorAction Stop
                }
                $regCleaned++
            }
        }
    }
    foreach ($regRoot in $regSoftRoots) {
        if (-not (Test-Path -LiteralPath $regRoot)) { continue }
        $subs = Get-ChildItem -LiteralPath $regRoot -ErrorAction SilentlyContinue |
            Where-Object { $_.PSChildName -like "*$kw*" }
        foreach ($sub in $subs) {
            $rp = $sub.PSPath
            Invoke-IfNotDry "删除注册表项: $rp" {
                Remove-Item -LiteralPath $rp -Recurse -Force -ErrorAction Stop
            }
            $regCleaned++
        }
    }
}

if ($regCleaned -eq 0) {
    Write-Skip "未找到注册表残留"
}
Write-Host ""

# ═══════════════════════════════════════════
# 阶段 8：清理开始菜单与桌面快捷方式
# ═══════════════════════════════════════════
Write-Host "=== 阶段 8: 清理快捷方式 ===" -ForegroundColor White

$shortcutRoots = @(
    (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'),
    (Join-Path $roamingAppData 'Microsoft\Windows\Start Menu\Programs'),
    (Join-Path $env:PUBLIC 'Desktop'),
    (Join-Path $env:USERPROFILE 'Desktop')
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique

$shortcutCleaned = 0
foreach ($kw in $allKeywords) {
    foreach ($smPath in $shortcutRoots) {
        $hits = Get-ChildItem -LiteralPath $smPath -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "*$kw*" } |
            Sort-Object { $_.FullName.Length } -Descending
        foreach ($h in $hits) {
            $hp = $h.FullName
            Invoke-IfNotDry "删除快捷方式: $hp" {
                Remove-Item -LiteralPath $hp -Recurse -Force -ErrorAction Stop
            }
            $shortcutCleaned++
        }
    }
}

if ($shortcutCleaned -eq 0) {
    Write-Skip "未找到快捷方式残留"
}
Write-Host ""

# ═══════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════
Write-Host "============================================" -ForegroundColor Magenta
if ($DryRun) {
    Write-Host "  预览完成 - [WILL] $script:WillCount 项将执行，[SKIP] $script:SkipCount 项无事可做" -ForegroundColor Yellow
    Write-Host "  确认无误后去掉 -DryRun（AI 调用请加 -Force）即可实际执行" -ForegroundColor Yellow
    Write-Host "============================================" -ForegroundColor Magenta
    Write-Host ""
    exit 0
}

Write-Host "  完成：成功 $script:OkCount / 失败 $script:FailCount / 跳过 $script:SkipCount" -ForegroundColor Green
if (($script:FailCount -gt 0) -and (-not $isAdmin)) {
    Write-Host "  提示：存在失败项且当前非管理员，建议以管理员重跑（HKLM 注册表/服务需要提权）。" -ForegroundColor Yellow
}
Write-Host "============================================" -ForegroundColor Magenta
Write-Host ""

if ($script:FailCount -gt 0) { exit 1 }
exit 0
