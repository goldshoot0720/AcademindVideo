<#
  start.ps1 —— 啟動 AcademindVideo 本地伺服器（Windows / PowerShell）
  對應 macOS 的 start.command，行為一致。

  用法：
    .\start.ps1                → http://localhost:8788/ （自動開瀏覽器）
    .\start.ps1 -Port 9000     → 指定埠號
    .\start.ps1 -NoOpen        → 不自動開瀏覽器
    .\start.ps1 -Port 9000 -NoOpen

  若執行原則封鎖，可用：
    powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1

  停止：在此視窗按 Ctrl-C（或雙擊 stop.bat）
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [int]$Port = 8788,

    [switch]$NoOpen
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- 主控台編碼
# Windows 主控台預設可能是 CP950 / CP936，直接輸出中文會變亂碼。
# 這裡統一切到 UTF-8，並讓 PowerShell 以 UTF-8 寫出，兩邊一致才不會亂碼。
try {
    & "$env:SystemRoot\System32\chcp.com" 65001 > $null 2>&1
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [Console]::OutputEncoding = $utf8
    $OutputEncoding = $utf8
} catch { }

# ---------------------------------------------------------------- 定位根目錄
$Root = $PSScriptRoot
if ([string]::IsNullOrEmpty($Root)) {
    $Root = Split-Path -Parent $MyInvocation.MyCommand.Path
}
Set-Location -LiteralPath $Root

$ServePy = Join-Path $Root 'scripts\serve.py'
if (-not (Test-Path -LiteralPath $ServePy)) {
    Write-Host "[X] 找不到 scripts\serve.py" -ForegroundColor Red
    Write-Host "    目前目錄：$Root" -ForegroundColor DarkGray
    exit 1
}

# ---------------------------------------------------------------- 小工具
# 直接對 127.0.0.1 發 HTTP 請求（Proxy 設為 $null，避免系統代理誤判）
function Test-HttpOk {
    param([int]$P)
    try {
        $req = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$P/")
        $req.Proxy = $null
        $req.Timeout = 1500
        $req.ReadWriteTimeout = 1500
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $resp.Close()
        return ($code -ge 200 -and $code -lt 400)
    } catch {
        return $false
    }
}

# 測試某個 python 指令是否為可用的 Python 3
function Test-PythonLauncher {
    param([string]$Exe, [string[]]$Pre = @())

    if ([string]::IsNullOrWhiteSpace($Exe)) { return $false }
    if (-not (Test-Path -LiteralPath $Exe -ErrorAction SilentlyContinue)) {
        if (-not (Get-Command $Exe -ErrorAction SilentlyContinue)) { return $false }
    }
    # 跳過 Microsoft Store 的 python.exe 佔位符（點了會開商店）
    $src = (Get-Command $Exe -ErrorAction SilentlyContinue).Source
    if ($src -and $src -match '\\WindowsApps\\') { return $false }

    try {
        $out = & $Exe @Pre -c "import sys;print(sys.version_info[0])" 2>$null
        if ($LASTEXITCODE -ne 0) { return $false }
        return ("$out".Trim() -eq '3')
    } catch {
        return $false
    }
}

# 依序找出可用的 Python 3，回傳 @{ Exe; Pre }
function Find-Python {
    $candidates = New-Object System.Collections.ArrayList

    # 0) 使用者自訂
    if ($env:ACADEMIND_PYTHON) {
        [void]$candidates.Add(@{ Exe = $env:ACADEMIND_PYTHON; Pre = @() })
    }
    # 1) py 啟動器（Windows 官方推薦）
    [void]$candidates.Add(@{ Exe = 'py'; Pre = @('-3') })
    # 2) PATH 上的 python / python3
    [void]$candidates.Add(@{ Exe = 'python'; Pre = @() })
    [void]$candidates.Add(@{ Exe = 'python3'; Pre = @() })
    # 3) 本工具鏈自帶的 Python
    [void]$candidates.Add(@{ Exe = (Join-Path $env:USERPROFILE '.workbuddy-ai\binaries\python\versions\3.13.12\python.exe'); Pre = @() })
    # 4) 常見安裝路徑（含 python.org 安裝器預設位置）
    $patterns = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python3*\python.exe'),
        'C:\Python3*\python.exe',
        (Join-Path $env:ProgramFiles 'Python3*\python.exe')
    )
    foreach ($p in $patterns) {
        Get-ChildItem -Path $p -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            ForEach-Object { [void]$candidates.Add(@{ Exe = $_.FullName; Pre = @() }) }
    }

    foreach ($c in $candidates) {
        if (Test-PythonLauncher -Exe $c.Exe -Pre $c.Pre) { return $c }
    }
    return $null
}

# ---------------------------------------------------------------- 主流程
$url = "http://localhost:$Port/"

# 同埠已有服務 → 直接開瀏覽器，不重複啟動
if (Test-HttpOk -P $Port) {
    Write-Host "[OK] 伺服器已在運行：$url" -ForegroundColor Green
    if (-not $NoOpen) { Start-Process $url }
    exit 0
}

$py = Find-Python
if ($null -eq $py) {
    Write-Host "[X] 找不到 Python 3。" -ForegroundColor Red
    Write-Host "    請先安裝：https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "    安裝時記得勾選 Add python.exe to PATH" -ForegroundColor DarkGray
    exit 1
}

Write-Host ""
Write-Host "AcademindVideo · 本地字幕課程伺服器" -ForegroundColor Cyan
Write-Host "  根目錄 : $Root" -ForegroundColor DarkGray
Write-Host "  埠號   : $Port" -ForegroundColor DarkGray
Write-Host "  網址   : $url" -ForegroundColor DarkGray
Write-Host "  Python : $($py.Exe) $($py.Pre -join ' ')" -ForegroundColor DarkGray
Write-Host "  停止   : 按 Ctrl-C" -ForegroundColor DarkGray
Write-Host ""

$pyArgs = @()
$pyArgs += $py.Pre
$pyArgs += @($ServePy, '--port', "$Port")
if (-not $NoOpen) { $pyArgs += '--open' }

& $py.Exe @pyArgs
exit $LASTEXITCODE
