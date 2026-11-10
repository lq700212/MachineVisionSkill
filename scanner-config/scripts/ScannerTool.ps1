# ============================================================================
# ScannerTool.ps1 - Eport E10 serial-to-Ethernet module (scanner gun base)
# Network configuration and diagnosis tool. ASCII only, PowerShell 5.1 safe.
#
# Usage:
#   ScannerTool.ps1 -Action probe                       # probe candidate IPs + NIC report
#   ScannerTool.ps1 -Action get    -Ip 192.168.1.220    # read SYS config (JSON)
#   ScannerTool.ps1 -Action backup -Ip 192.168.1.220    # backup E10.xml + SYS json
#   ScannerTool.ps1 -Action set    -Ip <current> -NewIp <target> [-Mask x]
#   ScannerTool.ps1 -Action verify -Ip 192.168.1.220    # ping + tcp + config read-back
#   ScannerTool.ps1 -Action full   -NewIp 192.168.1.220 # backup->set->verify->ini->cleanup
# ============================================================================
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('probe','get','backup','set','verify','full')]
    [string]$Action,

    [string]$Ip,
    [string]$NewIp = '192.168.1.220',
    [string]$Mask  = '255.255.255.0',
    [int]$DevicePort = 8899,
    [string]$DeviceUser = 'admin',
    [string]$DevicePass = 'admin',
    [string[]]$Candidates = @('192.168.1.220','169.254.173.207','10.10.100.10'),
    [string]$Mac = '40-2a-8f',                 # device MAC prefix for ARP watch
    [string]$StaleArpIp = '169.254.173.207',   # known stale ARP entry to ignore
    [int]$NicIfIndex = 20,
    [string]$CommissionedNicIp = '192.168.1.230',
    [switch]$NoConfigIniUpdate
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
if (-not $BackupDir) { $BackupDir = Join-Path $ProjectRoot 'config\scanner-backup' }
if (-not $ConfigIni) { $ConfigIni = Join-Path $ProjectRoot 'config\config.ini' }
$Ts = Get-Date -Format 'yyyyMMdd_HHmmss'

function Write-Step([string]$msg) {
    # Write-Host on purpose: log lines must go straight to the console and
    # must NOT be captured by the pipeline when the function result is consumed
    # (e.g. inside `if (Verify-Device ...)`) - classic PS pipeline gotcha.
    Write-Host ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $msg)
}

# --- basic network helpers ---------------------------------------------------
function Test-Ping([string]$targetIp) {
    try {
        $p = New-Object System.Net.NetworkInformation.Ping
        $r = $p.Send($targetIp, 900)
        return ($r.Status -eq [System.Net.NetworkInformation.IPStatus]::Success)
    } catch { return $false }
}

function Test-Tcp([string]$targetIp, [int]$targetPort, [int]$timeoutMs = 3000) {
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $t = $c.BeginConnect($targetIp, $targetPort, $null, $null)
        if ($t.AsyncWaitHandle.WaitOne($timeoutMs) -and $c.Connected) { return $true }
        return $false
    } catch { return $false } finally { try { $c.Close() } catch {} }
}

# --- device API --------------------------------------------------------------
# IMPORTANT: body must go through a temp file. Inline args get mangled by
# PowerShell quoting and the device answers with an echo of the request.
function Invoke-DtuRaw {
    param([string]$targetIp, [string]$body, [int]$timeoutSec = 10)
    $tmp = Join-Path $env:TEMP ('dtu_req_' + [guid]::NewGuid().ToString('N') + '.txt')
    [IO.File]::WriteAllText($tmp, $body, (New-Object System.Text.UTF8Encoding($false)))
    try {
        $raw = & curl.exe -s --max-time $timeoutSec `
            -u ("{0}:{1}" -f $DeviceUser, $DevicePass) `
            -H "Content-Type: application/json; charset=utf-8" `
            -H "Expect:" `
            --data-binary ("@{0}" -f $tmp) `
            ("http://{0}/cmd" -f $targetIp)
        $text = ($raw | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($text)) {
            throw ("empty response from {0}: connection dropped mid-write. " +
                   "Config may NOT have persisted. After a power cycle, re-probe the OLD address before retrying.") -f $targetIp
        }
        $j = $text | ConvertFrom-Json
        if ($j -is [System.Array]) { $j = $j[0] }        # SET replies as single-element array
        if ($null -eq $j.RC) { throw ("malformed response: {0}" -f $text) }
        if ($j.RC -ne 0)     { throw ("device error RC={0}: {1}" -f $j.RC, $text) }
        return $j
    } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
}

function Get-SysConfig([string]$targetIp) {
    $resp = Invoke-DtuRaw -targetIp $targetIp -body 'msg={"CID":10003,"PL":["SYS"]}'
    return $resp.PL.SYS
}

# --- backup ------------------------------------------------------------------
function Backup-Device([string]$targetIp) {
    if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null }
    $tag = ($targetIp -replace '\.', '_')
    $xmlPath  = Join-Path $BackupDir ("E10_{0}_{1}.xml" -f $tag, $Ts)
    $jsonPath = Join-Path $BackupDir ("SYS_{0}_{1}.json" -f $tag, $Ts)
    & curl.exe -s --max-time 10 -u ("{0}:{1}" -f $DeviceUser, $DevicePass) `
        ("http://{0}/E10.xml" -f $targetIp) -o $xmlPath
    if ((Test-Path $xmlPath) -and ((Get-Item $xmlPath).Length -gt 0)) {
        Write-Step ("config XML backed up: {0}" -f $xmlPath)
    } else {
        Write-Step "WARNING: E10.xml backup failed (continuing)"
    }
    try {
        $sys = Get-SysConfig $targetIp
        ConvertTo-Json $sys -Depth 12 | Out-File $jsonPath -Encoding utf8
        Write-Step ("SYS JSON backed up: {0}" -f $jsonPath)
    } catch {
        Write-Step ("WARNING: SYS JSON backup failed: {0}" -f $_.Exception.Message)
    }
}

# --- device discovery ---------------------------------------------------------
function Find-Device([string[]]$list) {
    foreach ($cand in $list) {
        if (Test-Ping $cand) { Write-Step ("device ONLINE at {0}" -f $cand); return $cand }
    }
    # provoke ARP, then watch by MAC; exclude the known stale entry
    foreach ($cand in $list) { $null = Test-Ping $cand }
    $arp = arp -a | Select-String $Mac | Where-Object { $_.ToString() -notmatch [regex]::Escape($StaleArpIp) }
    if ($arp) {
        $ipHit = ($arp[0].ToString() -split '\s+')[1]
        Write-Step ("device found via ARP at {0}" -f $ipHit)
        return $ipHit
    }
    throw ("device not reachable at any candidate: {0}" -f ($list -join ', '))
}

# --- change flow ---------------------------------------------------------------
function Set-DeviceIp([string]$currentIp, [string]$targetIp, [string]$targetMask) {
    Write-Step ("reading current SYS config from {0}" -f $currentIp)
    $sys = Get-SysConfig $currentIp
    Write-Step ("current: DhcpEn={0} IpAddr={1} Mask={2}" -f $sys.DhcpEn, $sys.IpAddr, $sys.Mask)

    # read-modify-write of the FULL object; only touch the network fields
    $sys.DhcpEn = 0
    $sys.IpAddr = $targetIp
    $sys.Mask   = $targetMask
    $body = '{"CID":10005,"PL":{"SYS":' + (ConvertTo-Json $sys -Depth 12 -Compress) + '}}'
    $null = Invoke-DtuRaw -targetIp $currentIp -body $body
    Write-Step "SET accepted (RC=0)"

    $chk = Get-SysConfig $currentIp
    if (-not ($chk.IpAddr -eq $targetIp -and $chk.DhcpEn -eq 0 -and $chk.Mask -eq $targetMask)) {
        throw ("read-back mismatch after SET: DhcpEn={0} IpAddr={1} Mask={2}" -f $chk.DhcpEn, $chk.IpAddr, $chk.Mask)
    }
    Write-Step ("read-back OK: DhcpEn=0 IpAddr={0} Mask={1}" -f $chk.IpAddr, $chk.Mask)

    $null = Invoke-DtuRaw -targetIp $currentIp -body '{"CID":20001,"PL":{}}'
    Write-Step "reload sent (20001). Device drops offline briefly, expect it back at the new address in ~45s."
}

function Wait-Online([string]$targetIp, [int]$timeoutSec = 120) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-Ping $targetIp) { Write-Step ("{0} is ONLINE" -f $targetIp); return $true }
        Start-Sleep -Seconds 5
    }
    throw ("{0} did not come online within {1}s. Check power/link LEDs, then factory reset (RESET 5s) if needed." -f $targetIp, $timeoutSec)
}

# --- config.ini ----------------------------------------------------------------
function Update-ScannerIni([string]$path, [string]$targetIp, [int]$targetPort) {
    if (-not (Test-Path $path)) { throw ("config.ini not found: {0}" -f $path) }
    $bytes = [IO.File]::ReadAllBytes($path)
    $enc = [Text.Encoding]::UTF8
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $enc = [Text.Encoding]::UTF8          # BOM kept
    } elseif ($bytes | Where-Object { $_ -gt 127 } | Select-Object -First 1) {
        $enc = [Text.Encoding]::Default       # ANSI file, keep it
    }
    $text = $enc.GetString($bytes).TrimStart([char]0xFEFF)
    $lines = $text -split "`r?`n"
    $inScanner = $false
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($line in $lines) {
        if ($line -match '^\s*\[([^\]]+)\]') { $inScanner = ($Matches[1] -ieq 'Scanner') }
        if ($inScanner -and $line -match '^\s*TcpIp\s*=')   { $out.Add(("TcpIp={0}"   -f $targetIp));   continue }
        if ($inScanner -and $line -match '^\s*TcpPort\s*=') { $out.Add(("TcpPort={0}" -f $targetPort)); continue }
        $out.Add($line)
    }
    [IO.File]::WriteAllText($path, (($out -join "`r`n") + "`r`n"), $enc)
    Write-Step ("config.ini updated: [Scanner] TcpIp={0} TcpPort={1}" -f $targetIp, $targetPort)
}

# --- NIC helpers ----------------------------------------------------------------
function Get-NicReport {
    $a = Get-NetAdapter -InterfaceIndex $NicIfIndex -ErrorAction Stop
    Write-Step ("NIC '{0}': {1} {2}" -f $a.Name, $a.Status, $a.LinkSpeed)
    Get-NetIPAddress -InterfaceIndex $NicIfIndex -AddressFamily IPv4 |
        ForEach-Object { Write-Step ("NIC IP: {0}/{1} ({2})" -f $_.IPAddress, $_.PrefixLength, $_.PrefixOrigin) }
}

function Add-TempNicIp([string]$tempIp, [int]$prefix) {
    $exists = Get-NetIPAddress -InterfaceIndex $NicIfIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
              Where-Object { $_.IPAddress -eq $tempIp }
    if (-not $exists) {
        New-NetIPAddress -InterfaceIndex $NicIfIndex -IPAddress $tempIp -PrefixLength $prefix -ErrorAction SilentlyContinue | Out-Null
        Write-Step ("temp NIC IP added: {0}/{1} (probe other-subnet candidates)" -f $tempIp, $prefix)
    }
}

function Remove-TempNicIps {
    Get-NetIPAddress -InterfaceIndex $NicIfIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -ne $CommissionedNicIp -and $_.PrefixOrigin -eq 'Manual' } |
        ForEach-Object {
            Remove-NetIPAddress -IPAddress $_.IPAddress -Confirm:$false -ErrorAction SilentlyContinue
            Write-Step ("temp NIC IP removed: {0}" -f $_.IPAddress)
        }
}

# --- verify ---------------------------------------------------------------------
function Verify-Device([string]$targetIp) {
    $r1 = Test-Ping $targetIp
    Write-Step ("ping {0} : {1}" -f $targetIp, $(if ($r1) {'OK'} else {'FAIL'}))
    $r2 = Test-Tcp $targetIp $DevicePort
    Write-Step ("tcp  {0}:{1} : {2}" -f $targetIp, $DevicePort, $(if ($r2) {'OPEN'} else {'FAIL'}))
    $r3 = $true
    try {
        $sys = Get-SysConfig $targetIp
        Write-Step ("config: DhcpEn={0} IpAddr={1} Mask={2}" -f $sys.DhcpEn, $sys.IpAddr, $sys.Mask)
        $r3 = ($sys.IpAddr -eq $targetIp -and $sys.DhcpEn -eq 0)
    } catch {
        Write-Step ("config read FAILED: {0}" -f $_.Exception.Message)
        $r3 = $false
    }
    Get-NicReport
    $ok = $r1 -and $r2 -and $r3
    Write-Step ("VERIFY RESULT: {0}" -f $(if ($ok) {'PASS'} else {'FAIL'}))
    return $ok
}

# === main ========================================================================
switch ($Action) {
    'probe' {
        Get-NicReport
        foreach ($c in $Candidates) {
            Write-Step ("probe {0} : {1}" -f $c, $(if (Test-Ping $c) {'ONLINE'} else {'offline'}))
        }
    }
    'get' {
        if (-not $Ip) { throw "-Ip is required for get" }
        Get-SysConfig $Ip | ConvertTo-Json -Depth 12
    }
    'backup' {
        if (-not $Ip) { throw "-Ip is required for backup" }
        Backup-Device -targetIp $Ip
    }
    'set' {
        $cur = $Ip
        if (-not $cur) { $cur = Find-Device -list $Candidates }
        Backup-Device -targetIp $cur
        Set-DeviceIp -currentIp $cur -targetIp $NewIp -targetMask $Mask
        Wait-Online -targetIp $NewIp -timeoutSec 120
        if (-not (Verify-Device -targetIp $NewIp)) { exit 1 }
    }
    'verify' {
        if (-not $Ip) { throw "-Ip is required for verify" }
        if (-not (Verify-Device -targetIp $Ip)) { exit 1 }
    }
    'full' {
        Get-NicReport
        # 1. locate device (it may sit at the old APIPA address after a revert)
        $cur = Find-Device -list $Candidates
        # 2. backup BEFORE any change
        Backup-Device -targetIp $cur
        # 3. configure if needed
        $sys = Get-SysConfig $cur
        if ($cur -eq $NewIp -and $sys.DhcpEn -eq 0) {
            Write-Step "device already configured as requested (skipping SET)"
        } else {
            Set-DeviceIp -currentIp $cur -targetIp $NewIp -targetMask $Mask
            Wait-Online -targetIp $NewIp -timeoutSec 120
        }
        # 4. keep software config in sync
        if (-not $NoConfigIniUpdate) {
            Update-ScannerIni -path $ConfigIni -targetIp $NewIp -targetPort $DevicePort
        }
        # 5. NIC hygiene: temp IPs only ever exist for foreign subnets; remove them
        Remove-TempNicIps
        # 6. final verification from the commissioned source IP
        if (-not (Verify-Device -targetIp $NewIp)) { exit 1 }
        Write-Step "FULL FLOW COMPLETE. Restart the CureStation software (it reads config.ini at startup)."
    }
    default { throw "unknown action" }
}
