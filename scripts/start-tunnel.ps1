# CookHero 公网临时隧道（Cloudflare Quick Tunnel）
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\start-tunnel.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\start-tunnel.ps1 -Port 5173
#
# 作用：把本机的前端开发服务器（默认 5173）映射为一个 https 公网地址，供他人临时访问。
# 注意：
#   1. 该地址在进程退出后立即失效，每次启动都会变；
#   2. 关闭窗口 = 关闭公网访问；
#   3. 只映射前端端口，后端 8000 由 Vite 的 /api、/media 代理转发，不要额外暴露数据库端口。

param([int]$Port = 5173)

$Root = Split-Path -Parent $PSScriptRoot

# 依次在项目 .run 目录、PATH 中查找 cloudflared
$exe = Join-Path $Root ".run\cloudflared.exe"
if (-not (Test-Path $exe)) {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { $exe = $cmd.Source }
}

if (-not $exe -or -not (Test-Path $exe)) {
    Write-Host "未找到 cloudflared。" -ForegroundColor Red
    Write-Host "安装方式一（推荐）：winget install --id Cloudflare.cloudflared" -ForegroundColor DarkGray
    Write-Host "安装方式二：下载 cloudflared-windows-amd64.exe 放到 $Root\.run\cloudflared.exe" -ForegroundColor DarkGray
    exit 1
}

# 确认本地服务在监听
$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Write-Host "端口 $Port 没有监听，请先启动前端：cd frontend; npm run dev" -ForegroundColor Red
    exit 1
}

Write-Host "正在建立隧道 → http://localhost:$Port" -ForegroundColor Cyan
Write-Host "地址生成后形如 https://xxxx-yyyy.trycloudflare.com ，按 Ctrl+C 断开。" -ForegroundColor DarkGray
Write-Host ""

& $exe tunnel --url "http://localhost:$Port" --no-autoupdate
