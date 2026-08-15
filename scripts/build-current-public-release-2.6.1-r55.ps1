$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$releaseRoot = Join-Path $projectRoot "release"
$stageRoot = Join-Path $releaseRoot "_stage_current_2.6.1_r55_20260815"
$archiveName = "social-theory-library-current-2.6.1-20260815-r55.tar.gz"
$archivePath = Join-Path $releaseRoot $archiveName
$archiveHashPath = "$archivePath.sha256"
$deployArtifactRoot = Join-Path $projectRoot ".codex-deploy-temp\public-deploy-20260815-r55"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

foreach ($path in @($stageRoot, $archivePath, $archiveHashPath)) {
    if (Test-Path -LiteralPath $path) {
        throw "拒绝覆盖已有发布产物：$path"
    }
}

New-Item -ItemType Directory -Path $stageRoot | Out-Null

$sourceFiles = [System.Collections.Generic.List[string]]::new()

function Assert-SafeRelativePath {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    $normalized = $RelativePath.Replace("\", "/").TrimStart("/")
    if ([string]::IsNullOrWhiteSpace($normalized) -or $normalized -match "(^|/)\.\.(/|$)") {
        throw "非法相对路径：$RelativePath"
    }
    return $normalized
}

function Copy-ProjectFile {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [switch]$AddToSourceManifest
    )

    $normalized = Assert-SafeRelativePath $RelativePath
    $sourcePath = Join-Path $projectRoot ($normalized.Replace("/", "\"))
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "白名单文件不存在：$normalized"
    }
    $targetPath = Join-Path $stageRoot ($normalized.Replace("/", "\"))
    $targetDirectory = Split-Path -Parent $targetPath
    New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    Copy-Item -LiteralPath $sourcePath -Destination $targetPath
    if ($AddToSourceManifest) {
        $sourceFiles.Add($normalized)
    }
}

function Get-WhitelistedDirectoryFiles {
    param([Parameter(Mandatory = $true)][string]$RelativeDirectory)

    $directory = Join-Path $projectRoot $RelativeDirectory
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        throw "白名单目录不存在：$RelativeDirectory"
    }
    Get-ChildItem -LiteralPath $directory -Recurse -File | Where-Object {
        $relative = $_.FullName.Substring($projectRoot.Length + 1)
        $relative -notmatch "(^|\\)(__pycache__|\.pytest_cache|\.next|\.vinext|\.wrangler|node_modules|test-results|playwright-report|coverage)(\\|$)" -and
        $_.Extension -notin @(".pyc", ".pyo", ".log", ".sqlite", ".sqlite3", ".db", ".pdf", ".pem", ".key", ".p12", ".pfx") -and
        $_.Name -ne ".env" -and
        $_.Name -notlike ".env.*" -and
        $_.Name -ne "tsconfig.tsbuildinfo"
    } | ForEach-Object {
        $_.FullName.Substring($projectRoot.Length + 1).Replace("\", "/")
    }
}

$rootFiles = @(
    ".env.example",
    ".env.lan.example",
    ".env.nas.example",
    ".env.nas-192.168.5.6.example",
    ".env.production.example",
    "compose.yaml",
    "compose.nas.yaml",
    "compose.public.yaml",
    "compose.cloudflare.yaml"
)

$apiDirectories = @(
    "api\accounts",
    "api\catalog",
    "api\common",
    "api\config",
    "api\distribution",
    "api\ingestion",
    "api\reading",
    "api\tests"
)
$apiFiles = @(
    "api/.dockerignore",
    "api/Dockerfile",
    "api/manage.py",
    "api/pytest.ini",
    "api/requirements.txt"
)

$webDirectories = @(
    "web\.openai",
    "web\app",
    "web\build",
    "web\components",
    "web\db",
    "web\drizzle",
    "web\lib",
    "web\public",
    "web\scripts",
    "web\tests",
    "web\worker"
)
$webFiles = @(
    "web/.dockerignore",
    "web/.gitignore",
    "web/cloudflare-env.d.ts",
    "web/docker-entrypoint.sh",
    "web/Dockerfile",
    "web/drizzle.config.ts",
    "web/eslint.config.mjs",
    "web/next.config.ts",
    "web/package-lock.json",
    "web/package.json",
    "web/pdfjs-worker.d.ts",
    "web/playwright.public.config.ts",
    "web/postcss.config.mjs",
    "web/README.md",
    "web/tsconfig.json",
    "web/vite.config.ts"
)

$supportFiles = @(
    "deploy/caddy/Caddyfile",
    "deploy/nginx/default.conf.template",
    "offline/api.Dockerfile",
    "offline/web.Dockerfile",
    "offline/python-wheels/PyYAML-6.0.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
    "scripts/verify_public_lan_item.py"
)

foreach ($file in $rootFiles + $apiFiles + $webFiles + $supportFiles) {
    Copy-ProjectFile -RelativePath $file -AddToSourceManifest
}
foreach ($directory in $apiDirectories + $webDirectories) {
    foreach ($file in Get-WhitelistedDirectoryFiles -RelativeDirectory $directory) {
        Copy-ProjectFile -RelativePath $file -AddToSourceManifest
    }
}

foreach ($file in Get-WhitelistedDirectoryFiles -RelativeDirectory "web\dist") {
    Copy-ProjectFile -RelativePath $file
}

foreach ($scriptName in @("apply.sh", "rollback.sh")) {
    $scriptSource = Join-Path $deployArtifactRoot $scriptName
    if (-not (Test-Path -LiteralPath $scriptSource -PathType Leaf)) {
        throw "缺少部署脚本：$scriptSource"
    }
    $normalizedScript = (Get-Content -Raw -LiteralPath $scriptSource).Replace("`r", "")
    [System.IO.File]::WriteAllText((Join-Path $stageRoot $scriptName), $normalizedScript, $utf8NoBom)
}

$orderedSourceFiles = $sourceFiles | Sort-Object -Unique
[System.IO.File]::WriteAllText(
    (Join-Path $stageRoot "source-files.txt"),
    (($orderedSourceFiles -join "`n") + "`n"),
    $utf8NoBom
)

$wheelPath = Join-Path $stageRoot "offline\python-wheels\PyYAML-6.0.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
$manifest = [ordered]@{
    release = "current-2.6.1-r55"
    built_at = (Get-Date).ToString("o")
    source_files = $orderedSourceFiles.Count
    web_dist_files = (Get-ChildItem (Join-Path $stageRoot "web\dist") -Recurse -File).Count
    pyyaml_wheel_sha256 = (Get-FileHash -LiteralPath $wheelPath -Algorithm SHA256).Hash.ToLowerInvariant()
    semantic_v2_default = $false
    production_index_switch = $false
    includes_model_weights = $false
    includes_pdf = $false
    includes_environment = $false
}
[System.IO.File]::WriteAllText(
    (Join-Path $stageRoot "release-manifest.json"),
    (($manifest | ConvertTo-Json -Depth 4) + "`n"),
    $utf8NoBom
)

$forbidden = Get-ChildItem -LiteralPath $stageRoot -Recurse -File | Where-Object {
    $relative = $_.FullName.Substring($stageRoot.Length + 1).Replace("\", "/")
    $relative -match "(^|/)(\.codex|\.wrangler|\.next|\.vinext|node_modules|__pycache__|\.pytest_cache|test-results|playwright-report)(/|$)" -or
    $_.Extension -in @(".pdf", ".sqlite", ".sqlite3", ".db", ".pem", ".key", ".p12", ".pfx", ".safetensors") -or
    $_.Name -eq ".env"
}
if ($forbidden) {
    $forbidden.FullName | ForEach-Object { Write-Error "禁入文件：$_" }
    throw "发布目录包含禁入文件"
}

$privateKeyMarkers = Get-ChildItem -LiteralPath $stageRoot -Recurse -File | Where-Object {
    $_.Length -le 2MB -and $_.Extension -in @(".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".yaml", ".yml", ".md", ".txt", ".sh", ".ps1", "")
} | Select-String -Pattern "BEGIN (OPENSSH|RSA|EC|DSA) PRIVATE KEY" -SimpleMatch:$false
if ($privateKeyMarkers) {
    throw "发布目录出现私钥标记"
}

$checksumFiles = Get-ChildItem -LiteralPath $stageRoot -Recurse -File | Where-Object {
    $_.Name -ne "SHA256SUMS"
} | Sort-Object FullName
$checksumLines = foreach ($file in $checksumFiles) {
    $relative = $file.FullName.Substring($stageRoot.Length + 1).Replace("\", "/")
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  ./$relative"
}
[System.IO.File]::WriteAllText(
    (Join-Path $stageRoot "SHA256SUMS"),
    (($checksumLines -join "`n") + "`n"),
    $utf8NoBom
)

& tar.exe -czf $archivePath -C $stageRoot .
if ($LASTEXITCODE -ne 0) {
    throw "tar 创建发布包失败，退出码 $LASTEXITCODE"
}

$archiveEntries = & tar.exe -tzf $archivePath
if ($LASTEXITCODE -ne 0) {
    throw "tar 读取发布包失败，退出码 $LASTEXITCODE"
}
$unsafeEntries = $archiveEntries | Where-Object {
    $_ -match "^/" -or $_ -match "(^|/)\.\.(/|$)" -or $_ -match "^[A-Za-z]:"
}
if ($unsafeEntries) {
    throw "发布包包含不安全路径：$($unsafeEntries -join ', ')"
}

$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText(
    $archiveHashPath,
    "$archiveHash  $archiveName`n",
    $utf8NoBom
)

$stageBytes = (Get-ChildItem -LiteralPath $stageRoot -Recurse -File | Measure-Object Length -Sum).Sum
[pscustomobject]@{
    Archive = $archivePath
    ArchiveBytes = (Get-Item -LiteralPath $archivePath).Length
    ArchiveSHA256 = $archiveHash
    StageFiles = (Get-ChildItem -LiteralPath $stageRoot -Recurse -File).Count
    StageBytes = $stageBytes
    SourceFiles = $orderedSourceFiles.Count
    WebDistFiles = $manifest.web_dist_files
    ForbiddenFiles = @($forbidden).Count
    UnsafeArchivePaths = @($unsafeEntries).Count
}
