[CmdletBinding()]
param(
    [ValidateSet("start", "run", "stop", "status", "credentials")]
    [string]$Mode = "start"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StateDirectory = Join-Path $ProjectRoot ".powerquery-public"
$LogDirectory = Join-Path $ProjectRoot "logs"
$PidPath = Join-Path $StateDirectory "public-offline.pid"
$MetadataPath = Join-Path $StateDirectory "public-offline.json"
$CredentialsPath = Join-Path $StateDirectory "admin-credentials.json"
$LauncherLog = Join-Path $LogDirectory "public-offline-launcher.log"
$PowerQueryExecutable = Join-Path $ProjectRoot ".venv\Scripts\powerquery.exe"
$DatabasePath = Join-Path $ProjectRoot "data\processed\power.db"
$TailscaleExecutable = "C:\Program Files\Tailscale\tailscale.exe"
$LocalPort = 8766
$PublicPort = 8443
$LocalHealthUrl = "http://127.0.0.1:$LocalPort/api/health"

function Initialize-Directories {
    New-Item -ItemType Directory -Force -Path $StateDirectory, $LogDirectory | Out-Null
}

function Write-ServiceLog {
    param([Parameter(Mandatory = $true)][string]$Message)

    Initialize-Directories
    $line = "{0} {1}" -f ([DateTimeOffset]::Now.ToString("o")), $Message
    Add-Content -LiteralPath $LauncherLog -Value $line -Encoding UTF8
    Write-Host $Message
}

function Get-TrackedProcess {
    if (-not (Test-Path -LiteralPath $PidPath)) {
        return $null
    }

    $rawPid = (Get-Content -LiteralPath $PidPath -Raw).Trim()
    $processId = 0
    if (-not [int]::TryParse($rawPid, [ref]$processId)) {
        Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
        return $null
    }

    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
        return $null
    }

    $actualPath = $null
    try {
        $actualPath = $process.Path
    }
    catch {
        $actualPath = $null
    }
    if (-not $actualPath -or
        -not [string]::Equals(
            [IO.Path]::GetFullPath($actualPath),
            [IO.Path]::GetFullPath($PowerQueryExecutable),
            [StringComparison]::OrdinalIgnoreCase
        )) {
        Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
        return $null
    }
    return $process
}

function Get-OfflineHealth {
    try {
        $health = Invoke-RestMethod -Uri $LocalHealthUrl -TimeoutSec 2
        if ($health.success -eq $true -and
            $health.online_llm -eq $false -and
            $health.mode.active_mode -eq "offline") {
            return $health
        }
    }
    catch {
        return $null
    }
    return $null
}

function Test-LocalPortInUse {
    try {
        return $null -ne (Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $LocalPort -State Listen -ErrorAction Stop | Select-Object -First 1)
    }
    catch {
        return $false
    }
}

function Get-PublicUrl {
    $statusJson = & $TailscaleExecutable status --json 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "無法讀取 Tailscale 狀態。"
    }
    $status = $statusJson | ConvertFrom-Json
    $dnsName = [string]$status.Self.DNSName
    $dnsName = $dnsName.Trim().TrimEnd(".")
    if (-not $dnsName) {
        throw "Tailscale 尚未提供本機 DNS 名稱。"
    }
    return "https://${dnsName}:$PublicPort/"
}

function Enable-PublicFunnel {
    $output = & $TailscaleExecutable funnel --bg "--https=$PublicPort" $LocalPort 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Tailscale Funnel 啟用失敗：$($output -join ' ')"
    }
    return Get-PublicUrl
}

function New-RandomAdminPassword {
    $bytes = New-Object byte[] 48
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes)
}

function Get-OrCreateAdminCredentials {
    Initialize-Directories
    if (Test-Path -LiteralPath $CredentialsPath -PathType Leaf) {
        $saved = Get-Content -LiteralPath $CredentialsPath -Raw | ConvertFrom-Json
        if ($saved.username -and $saved.password) {
            return $saved
        }
        throw "Public administrator credential file is invalid: $CredentialsPath"
    }

    $credentials = [ordered]@{
        username = "powerquery-admin"
        password = New-RandomAdminPassword
        created_at = [DateTimeOffset]::Now.ToString("o")
    }
    $credentials | ConvertTo-Json | Set-Content -LiteralPath $CredentialsPath -Encoding UTF8
    return [pscustomobject]$credentials
}

function Show-AdminCredentials {
    $credentials = Get-OrCreateAdminCredentials
    Write-Host "Public data-center account: $($credentials.username)"
    Write-Host "Public data-center password: $($credentials.password)"
    Write-Host "Credential file: $CredentialsPath"
}

function Start-PublicOfflineService {
    Initialize-Directories

    if (-not (Test-Path -LiteralPath $TailscaleExecutable -PathType Leaf)) {
        throw "找不到 Tailscale：$TailscaleExecutable"
    }
    if (-not (Test-Path -LiteralPath $PowerQueryExecutable -PathType Leaf)) {
        throw "找不到 PowerQuery 虛擬環境。請先執行專案根目錄的 啟動.bat。"
    }
    if (-not (Test-Path -LiteralPath $DatabasePath -PathType Leaf)) {
        throw "找不到資料庫：$DatabasePath"
    }

    $publicUrl = Get-PublicUrl
    $publicHost = ([Uri]$publicUrl).Host
    $credentials = Get-OrCreateAdminCredentials
    $tracked = Get-TrackedProcess
    if ($null -ne $tracked) {
        $health = Get-OfflineHealth
        if ($null -eq $health) {
            throw "已追蹤的公開程序存在，但離線健康檢查失敗。請先執行 停止公開服務.bat。"
        }
        $publicUrl = Enable-PublicFunnel
        Write-ServiceLog "公開離線服務已在執行：$publicUrl"
        Show-AdminCredentials
        return
    }

    if ($null -ne (Get-OfflineHealth) -or (Test-LocalPortInUse)) {
        throw "本機連接埠 $LocalPort 已被未追蹤的程序占用；為避免誤把線上服務公開，啟動已中止。"
    }

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $stdoutLog = Join-Path $LogDirectory "public-offline-$stamp.stdout.log"
    $stderrLog = Join-Path $LogDirectory "public-offline-$stamp.stderr.log"
    $savedEnvironment = @{
        OPENAI_API_KEY = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "Process")
        POWERQUERY_ADMIN_USERNAME = [Environment]::GetEnvironmentVariable("POWERQUERY_ADMIN_USERNAME", "Process")
        POWERQUERY_ADMIN_PASSWORD = [Environment]::GetEnvironmentVariable("POWERQUERY_ADMIN_PASSWORD", "Process")
        POWERQUERY_ADMIN_ALLOWED_HOSTS = [Environment]::GetEnvironmentVariable("POWERQUERY_ADMIN_ALLOWED_HOSTS", "Process")
        PYTHONUNBUFFERED = [Environment]::GetEnvironmentVariable("PYTHONUNBUFFERED", "Process")
    }

    try {
        [Environment]::SetEnvironmentVariable("OPENAI_API_KEY", $null, "Process")
        [Environment]::SetEnvironmentVariable("POWERQUERY_ADMIN_USERNAME", [string]$credentials.username, "Process")
        [Environment]::SetEnvironmentVariable("POWERQUERY_ADMIN_PASSWORD", [string]$credentials.password, "Process")
        [Environment]::SetEnvironmentVariable("POWERQUERY_ADMIN_ALLOWED_HOSTS", "127.0.0.1,localhost,::1,$publicHost", "Process")
        [Environment]::SetEnvironmentVariable("PYTHONUNBUFFERED", "1", "Process")

        $startParameters = @{
            FilePath = $PowerQueryExecutable
            ArgumentList = @("--serve", "--host", "127.0.0.1", "--port", "$LocalPort")
            WorkingDirectory = $ProjectRoot
            WindowStyle = "Hidden"
            RedirectStandardOutput = $stdoutLog
            RedirectStandardError = $stderrLog
            PassThru = $true
        }
        $process = Start-Process @startParameters
    }
    finally {
        foreach ($name in $savedEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")
        }
    }

    Set-Content -LiteralPath $PidPath -Value $process.Id -Encoding ASCII
    $healthy = $false
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        if ($process.HasExited) {
            break
        }
        if ($null -ne (Get-OfflineHealth)) {
            $healthy = $true
            break
        }
        Start-Sleep -Milliseconds 500
        $process.Refresh()
    }

    if (-not $healthy) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
        throw "公開離線服務未能通過健康檢查。請查看 $stderrLog"
    }

    try {
        $publicUrl = Enable-PublicFunnel
    }
    catch {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
        throw
    }

    $metadata = [ordered]@{
        mode = "offline"
        pid = $process.Id
        local_url = "http://127.0.0.1:$LocalPort/"
        public_url = $publicUrl
        public_port = $PublicPort
        started_at = [DateTimeOffset]::Now.ToString("o")
        stdout_log = $stdoutLog
        stderr_log = $stderrLog
        query_error_log = Join-Path $ProjectRoot "data\processed\.powerquery-data\query-errors.jsonl"
    }
    $metadata | ConvertTo-Json | Set-Content -LiteralPath $MetadataPath -Encoding UTF8
    Write-ServiceLog "公開離線服務已啟動：$publicUrl"
    Write-ServiceLog "服務日誌：$stdoutLog；錯誤日誌：$stderrLog"
    Show-AdminCredentials
}

function Run-PublicOfflineService {
    Initialize-Directories

    if (-not (Test-Path -LiteralPath $TailscaleExecutable -PathType Leaf)) {
        throw "找不到 Tailscale：$TailscaleExecutable"
    }
    if (-not (Test-Path -LiteralPath $PowerQueryExecutable -PathType Leaf)) {
        throw "找不到 PowerQuery 虛擬環境。請先執行專案根目錄的 啟動.bat。"
    }
    if (-not (Test-Path -LiteralPath $DatabasePath -PathType Leaf)) {
        throw "找不到資料庫：$DatabasePath"
    }
    if ($null -ne (Get-TrackedProcess) -or (Test-LocalPortInUse)) {
        throw "公開離線服務已在執行。請先關閉原本的終端機，或執行 停止公開服務.bat。"
    }

    $publicUrl = Get-PublicUrl
    $publicHost = ([Uri]$publicUrl).Host
    $credentials = Get-OrCreateAdminCredentials
    $savedEnvironment = @{
        OPENAI_API_KEY = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "Process")
        POWERQUERY_ADMIN_USERNAME = [Environment]::GetEnvironmentVariable("POWERQUERY_ADMIN_USERNAME", "Process")
        POWERQUERY_ADMIN_PASSWORD = [Environment]::GetEnvironmentVariable("POWERQUERY_ADMIN_PASSWORD", "Process")
        POWERQUERY_ADMIN_ALLOWED_HOSTS = [Environment]::GetEnvironmentVariable("POWERQUERY_ADMIN_ALLOWED_HOSTS", "Process")
        PYTHONUNBUFFERED = [Environment]::GetEnvironmentVariable("PYTHONUNBUFFERED", "Process")
    }

    $process = $null
    $funnelEnabled = $false
    try {
        try {
            [Environment]::SetEnvironmentVariable("OPENAI_API_KEY", $null, "Process")
            [Environment]::SetEnvironmentVariable("POWERQUERY_ADMIN_USERNAME", [string]$credentials.username, "Process")
            [Environment]::SetEnvironmentVariable("POWERQUERY_ADMIN_PASSWORD", [string]$credentials.password, "Process")
            [Environment]::SetEnvironmentVariable("POWERQUERY_ADMIN_ALLOWED_HOSTS", "127.0.0.1,localhost,::1,$publicHost", "Process")
            [Environment]::SetEnvironmentVariable("PYTHONUNBUFFERED", "1", "Process")
            $process = Start-Process -FilePath $PowerQueryExecutable `
                -ArgumentList @("--serve", "--host", "127.0.0.1", "--port", "$LocalPort") `
                -WorkingDirectory $ProjectRoot -NoNewWindow -PassThru
        }
        finally {
            foreach ($name in $savedEnvironment.Keys) {
                [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")
            }
        }

        Set-Content -LiteralPath $PidPath -Value $process.Id -Encoding ASCII
        $healthy = $false
        for ($attempt = 0; $attempt -lt 120; $attempt++) {
            $process.Refresh()
            if ($process.HasExited) {
                break
            }
            if ($null -ne (Get-OfflineHealth)) {
                $healthy = $true
                break
            }
            Start-Sleep -Milliseconds 500
        }
        if (-not $healthy) {
            throw "公開離線服務未能通過健康檢查。"
        }

        $publicUrl = Enable-PublicFunnel
        $funnelEnabled = $true
        $metadata = [ordered]@{
            mode = "offline"
            launch_mode = "foreground"
            pid = $process.Id
            local_url = "http://127.0.0.1:$LocalPort/"
            public_url = $publicUrl
            public_port = $PublicPort
            started_at = [DateTimeOffset]::Now.ToString("o")
        }
        $metadata | ConvertTo-Json | Set-Content -LiteralPath $MetadataPath -Encoding UTF8
        Write-ServiceLog "公開離線服務在此終端機執行：$publicUrl"
        Write-Host "關閉此終端機或按 Ctrl+C，即停止伺服器。"

        $process.WaitForExit()
        if ($process.ExitCode -ne 0 -and (Test-Path -LiteralPath $PidPath)) {
            throw "公開離線程序異常停止，退出碼：$($process.ExitCode)"
        }
    }
    finally {
        if ($null -ne $process) {
            $process.Refresh()
            if (-not $process.HasExited) {
                Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                $process.WaitForExit(5000) | Out-Null
            }
        }
        if ($funnelEnabled) {
            $output = & $TailscaleExecutable funnel "--https=$PublicPort" off 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-ServiceLog "警告：無法關閉 $PublicPort Funnel：$($output -join ' ')"
            }
        }
        if ($null -ne $process -and (Test-Path -LiteralPath $PidPath)) {
            $recordedPid = (Get-Content -LiteralPath $PidPath -Raw).Trim()
            if ($recordedPid -eq [string]$process.Id) {
                Remove-Item -LiteralPath $PidPath, $MetadataPath -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

function Stop-PublicOfflineService {
    Initialize-Directories

    if (Test-Path -LiteralPath $TailscaleExecutable -PathType Leaf) {
        $output = & $TailscaleExecutable funnel "--https=$PublicPort" off 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-ServiceLog "警告：無法關閉 $PublicPort Funnel：$($output -join ' ')"
        }
    }

    $process = Get-TrackedProcess
    if ($null -ne $process) {
        Stop-Process -Id $process.Id -Force
        $process.WaitForExit(5000) | Out-Null
        Write-ServiceLog "公開離線程序已停止。"
    }
    else {
        Write-ServiceLog "沒有找到執行中的公開離線程序。"
    }

    Remove-Item -LiteralPath $PidPath, $MetadataPath -Force -ErrorAction SilentlyContinue
}

function Show-PublicOfflineStatus {
    Initialize-Directories
    $process = Get-TrackedProcess
    $health = Get-OfflineHealth
    if ($null -eq $process -or $null -eq $health) {
        Write-Host "狀態：未執行"
        exit 1
    }

    $publicUrl = Get-PublicUrl
    Write-Host "狀態：執行中（offline）"
    Write-Host "本機：http://127.0.0.1:$LocalPort/"
    Write-Host "公開：$publicUrl"
    Write-Host "PID：$($process.Id)"
}

try {
    switch ($Mode) {
        "start" { Start-PublicOfflineService }
        "run" { Run-PublicOfflineService }
        "stop" { Stop-PublicOfflineService }
        "status" { Show-PublicOfflineStatus }
        "credentials" { Show-AdminCredentials }
    }
}
catch {
    Write-ServiceLog "錯誤：$($_.Exception.Message)"
    exit 1
}
