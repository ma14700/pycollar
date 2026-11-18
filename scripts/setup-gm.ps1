$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$basePython = Join-Path $root '.venv\Scripts\python.exe'
$gmRoot = Join-Path $root '.venv\gm-runtime'
$gmPython = Join-Path $gmRoot 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $basePython)) { throw '请先运行 start.bat，创建项目 Python 环境。' }
if (-not (Test-Path -LiteralPath $gmPython)) {
    & $basePython -m venv $gmRoot
    if ($LASTEXITCODE -ne 0) { throw '无法创建掘金独立环境。' }
}
& $gmPython -m pip install -r (Join-Path $root 'requirements-gm.txt')
if ($LASTEXITCODE -ne 0) { throw '掘金 SDK 安装失败，请检查网络。' }
Write-Host '掘金 SDK 安装完成，请启动并登录掘金终端。'
