param()
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$BuildPython = Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $BuildPython)) {
    py -3.12 -m venv .build-venv
    if ($LASTEXITCODE -ne 0) { throw '创建构建环境失败' }
}
& $BuildPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw '安装构建依赖失败' }
& $BuildPython -m PyInstaller --noconfirm TelegramAI.spec
if ($LASTEXITCODE -ne 0) { throw 'EXE 构建失败' }
Write-Host 'Build complete: dist\TelegramAI.exe and dist\TelegramAI-console.exe are ready.'
