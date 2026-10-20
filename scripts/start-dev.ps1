# CookHero 本地开发一键启动 / 停止
# 用法：
#   powershell -ExecutionPolicy Bypass -File start-dev.ps1          启动
#   powershell -ExecutionPolicy Bypass -File start-dev.ps1 -Stop    停止
#   powershell -ExecutionPolicy Bypass -File start-dev.ps1 -Check   只检查环境，不启动
#   powershell -ExecutionPolicy Bypass -File start-dev.ps1 -Root D:\xianmu2   手动指定仓库根目录
#
# 脚本可放在任意位置（桌面、scripts、甚至 U 盘）：默认会从脚本所在目录向上查找仓库根目录，
# 找不到时才回退到 -Root 参数或内置默认路径。
#
# 说明：基础设施跑在 Docker 里（PostgreSQL / Redis / Milvus / MinIO / Etcd），
#       后端与前端在宿主机上各占一个终端窗口运行。

param(
    [switch]$Stop,
    [switch]$Check,
    [string]$Root
)

# ---- 定位仓库根目录：app\main.py + config.yml + frontend\package.json 三者同时存在即为根目录 ----
function Test-RepoRoot([string]$dir) {
    if (-not $dir) { return $false }
    if (-not (Test-Path $dir -PathType Container)) { return $false }
    return (
        (Test-Path (Join-Path $dir "app\main.py")) -and
        (Test-Path (Join-Path $dir "config.yml")) -and
        (Test-Path (Join-Path $dir "frontend\package.json"))
    )
}

function Find-RepoRoot([string]$startDir, [int]$maxUp = 10) {
    if (-not $startDir) { return $null }
    $dir = $startDir
    for ($i = 0; $i -le $maxUp; $i++) {
        if (Test-RepoRoot $dir) { return (Resolve-Path $dir).Path }
        $parent = Split-Path -Parent $dir
        if (-not $parent -or $parent -eq $dir) { break }
        $dir = $parent
    }
    return $null
}

$RootSource = "自动查找"
if ($Root) {
    if (-not (Test-RepoRoot $Root)) {
        Write-Host "指定的 -Root 不是有效的 CookHero 仓库根目录：$Root" -ForegroundColor Red
        Write-Host "该目录下必须同时存在 app\main.py、config.yml、frontend\package.json。" -ForegroundColor DarkGray
        exit 1
    }
    $RootSource = "参数指定"
} else {
    $Root = Find-RepoRoot $PSScriptRoot
    if (-not $Root) { $Root = Find-RepoRoot (Get-Location).Path }
    if (-not $Root -and (Test-RepoRoot "D:\xianmu2")) { $Root = "D:\xianmu2"; $RootSource = "内置默认路径" }
    if (-not $Root) {
        Write-Host "未能定位 CookHero 仓库根目录。" -ForegroundColor Red
        Write-Host "请用 -Root 指定，例如：powershell -ExecutionPolicy Bypass -File start-dev.ps1 -Root D:\xianmu2" -ForegroundColor DarkGray
        exit 1
    }
}

$RunDir = Join-Path $Root ".run"
if (-not (Test-Path $RunDir)) { New-Item -ItemType Directory -Path $RunDir | Out-Null }

if ($Check) {
    Write-Host "仓库根目录：$Root  （来源：$RootSource）" -ForegroundColor Green
    Write-Host "脚本位置：  $PSScriptRoot" -ForegroundColor DarkGray
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { Write-Host "Docker：    引擎已就绪" -ForegroundColor Green }
    else { Write-Host "Docker：    引擎未运行（启动时会尝试拉起 Docker Desktop）" -ForegroundColor Yellow }
    if (Test-Path (Join-Path $Root ".venv\Scripts\python.exe")) { Write-Host "Python：    .venv 存在" -ForegroundColor Green }
    else { Write-Host "Python：    未找到 .venv" -ForegroundColor Red }
    if (Test-Path (Join-Path $Root "frontend\node_modules")) { Write-Host "Node：      node_modules 存在" -ForegroundColor Green }
    else { Write-Host "Node：      node_modules 缺失，需先在 frontend 下 npm install" -ForegroundColor Yellow }
    exit 0
}

function Stop-PortProcess($port) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conns) {
        $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($p in $pids) {
            Write-Host "  停止端口 $port 上的进程 $p" -ForegroundColor Yellow
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host "  端口 $port 无监听进程" -ForegroundColor DarkGray
    }
}

if ($Stop) {
    Write-Host "== 停止后端与前端 ==" -ForegroundColor Cyan
    Stop-PortProcess 8000
    Stop-PortProcess 5173
    Write-Host "== 停止基础设施容器 ==" -ForegroundColor Cyan
    Push-Location (Join-Path $Root "deployments")
    docker compose stop
    Pop-Location
    Write-Host "已停止。数据保留在 Docker volume 中，下次启动直接恢复。" -ForegroundColor Green
    exit 0
}

Write-Host "== 1/3 检查 Docker ==" -ForegroundColor Cyan
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $exe = "D:\Program Files\Docker\Docker Desktop.exe"
    if (Test-Path $exe) {
        Write-Host "  Docker 引擎未运行，正在拉起 Docker Desktop..." -ForegroundColor Yellow
        Start-Process -FilePath $exe
        for ($i = 1; $i -le 24; $i++) {
            Start-Sleep -Seconds 5
            docker info *> $null
            if ($LASTEXITCODE -eq 0) { break }
            Write-Host "  等待引擎就绪 ($($i*5)s)..." -ForegroundColor DarkGray
        }
    } else {
        Write-Host "  未找到 Docker Desktop，请手动启动后重试。" -ForegroundColor Red
        exit 1
    }
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Docker 引擎仍不可用，请手动打开 Docker Desktop 后再运行本脚本。" -ForegroundColor Red
    exit 1
}
Write-Host "  Docker 就绪" -ForegroundColor Green

Write-Host "== 2/3 启动基础设施 ==" -ForegroundColor Cyan
Push-Location (Join-Path $Root "deployments")
docker compose up -d
Pop-Location
Start-Sleep -Seconds 8
docker ps --format "  {{.Names}}`t{{.Status}}"

Write-Host "== 3/3 启动后端与前端（各开一个窗口）==" -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$Root'; `$host.UI.RawUI.WindowTitle='CookHero 后端 :8000'; .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
)
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$Root\frontend'; `$host.UI.RawUI.WindowTitle='CookHero 前端 :5173'; npm run dev"
)

Write-Host ""
Write-Host "启动中，后端首次加载模型约需 20-40 秒。" -ForegroundColor Green
Write-Host "  前端      http://localhost:5173" -ForegroundColor White
Write-Host "  后端      http://localhost:8000" -ForegroundColor White
Write-Host "  API 文档  http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "日志：后端窗口直接输出；如需落盘可改用 .run\backend.out.log。" -ForegroundColor DarkGray
