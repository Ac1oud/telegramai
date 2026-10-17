param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot '.deps'

# 优先使用本机当前已配置的 Python；.deps 中保存了本项目的依赖。
$CodexPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $CodexPython) {
    $PythonExe = $CodexPython
    $PythonPrefix = @()
} elseif (Test-Path -LiteralPath $VenvPython) {
    $PythonExe = $VenvPython
    $PythonPrefix = @()
} else {
    $PythonExe = 'py'
    $PythonPrefix = @('-3.12')
}
$MainFile = Join-Path $ProjectRoot 'main.py'

function Invoke-Assistant([string[]]$ArgumentsForMain) {
    & $PythonExe @PythonPrefix $MainFile @ArgumentsForMain
    if ($LASTEXITCODE -ne 0) {
        Write-Host "程序退出码：$LASTEXITCODE" -ForegroundColor Yellow
    }
}

$ProfileFiles = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'profiles') -Filter '*.env' -File -ErrorAction SilentlyContinue | Sort-Object Name)
if ($ProfileFiles.Count -eq 0) {
    Write-Host 'profiles 目录里还没有账号配置。先运行：python main.py --create-profile new_account --copy-settings-from current'
    exit 1
}

Write-Host '选择 Telegram 账号配置：'
for ($i = 0; $i -lt $ProfileFiles.Count; $i++) {
    Write-Host ("{0}. {1}" -f ($i + 1), $ProfileFiles[$i].BaseName)
}
$Selection = Read-Host '输入序号'
$Index = 0
if (-not [int]::TryParse($Selection, [ref]$Index) -or $Index -lt 1 -or $Index -gt $ProfileFiles.Count) {
    Write-Host '序号无效。'
    exit 1
}
$SelectedProfile = $ProfileFiles[$Index - 1].BaseName

Write-Host "已选择：$SelectedProfile"
Write-Host '1. 启动监听'
Write-Host '2. 新账号二维码登录'
Write-Host '3. 列出该账号的群组 ID'
Write-Host '4. 创建另一个账号配置'
Write-Host '5. 退出'
$Action = Read-Host '选择操作'

switch ($Action) {
    '1' { Invoke-Assistant @('--profile', $SelectedProfile) }
    '2' { Invoke-Assistant @('--profile', $SelectedProfile, '--qr-login') }
    '3' { Invoke-Assistant @('--profile', $SelectedProfile, '--list-chats') }
    '4' {
        $NewProfile = Read-Host '输入新配置名（英文、数字、下划线或连字符）'
        Invoke-Assistant @('--create-profile', $NewProfile, '--copy-settings-from', $SelectedProfile)
        Write-Host '新配置已创建；session 独立，群组白名单从所选配置复制，手机号和 session 不复制。'
    }
    default { Write-Host '已退出。' }
}
