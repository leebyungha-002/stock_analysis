$base   = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "$base\.venv\Scripts\python.exe"
$script = "$base\market_indicator_runner.py"
$logDir = "$base\logs"
$log    = "$logDir\kr_market_indicator.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Add-Content -Path $log -Value $line -Encoding UTF8
}

Write-Log "=== MarketIndicator_KR START ==="
$output = & $python $script --kr 2>&1
$output | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding UTF8 }

if ($LASTEXITCODE -eq 0) {
    Write-Log "SUCCESS"
} else {
    Write-Log "FAILURE (exit: $LASTEXITCODE)"
}
Add-Content -Path $log -Value "================================" -Encoding UTF8
