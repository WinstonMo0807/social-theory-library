$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$releaseRoot = Join-Path $projectRoot "release"
$stageRoot = Join-Path $releaseRoot "_stage_editorial_ui_2.6.1_r59_20260816"
$archiveName = "social-theory-library-editorial-ui-2.6.1-20260816-r59.tar.gz"
$archivePath = Join-Path $releaseRoot $archiveName
$archiveHashPath = "$archivePath.sha256"
$deployArtifactRoot = Join-Path $projectRoot ".codex-deploy-temp\public-deploy-20260815-r59"
$verificationRoot = Join-Path $projectRoot "tmp\package-r59-archive-verification"
$r57StageRoot = Join-Path $releaseRoot "_stage_current_2.6.1_r57_20260815"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$frozenFiles = @(
    [ordered]@{
        path = "web/app/editorial-v2.css"
        timestamp = "2026-08-16 00:15:53.100"
        length = 101938
        sha256 = "8140ce5bf7d7edb3ec3b613ac13f5263f24f83d3a4a51d5bd49f14b8560c66af"
    },
    [ordered]@{
        path = "web/dist/server/index.js"
        timestamp = "2026-08-16 00:16:35.429"
        length = 1085916
        sha256 = "417da73d16b7678959ec7be3dd0cc5fe90053b9143c7b196494922dfd082b4b4"
    },
    [ordered]@{
        path = "web/dist/server/assets/index-W_-kgWXz.css"
        timestamp = "2026-08-16 00:16:31.037"
        length = 462152
        sha256 = "d28364a2b16963860807b7ce7ca22a88494d722fab894089c8faf6db06d66416"
    }
)

foreach ($path in @($stageRoot, $archivePath, $archiveHashPath, $verificationRoot)) {
    if (Test-Path -LiteralPath $path) {
        throw "拒绝覆盖已有发布或验证产物：$path"
    }
}

function Assert-SafeRelativePath {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    $normalized = $RelativePath.Replace("\", "/").TrimStart("/")
    if ([string]::IsNullOrWhiteSpace($normalized) -or $normalized -match "(^|/)\.\.(/|$)") {
        throw "非法相对路径：$RelativePath"
    }
    return $normalized
}

function Assert-FrozenFile {
    param(
        [Parameter(Mandatory = $true)][string]$BasePath,
        [Parameter(Mandatory = $true)][System.Collections.IDictionary]$Expected,
        [switch]$CheckTimestamp
    )

    $normalized = Assert-SafeRelativePath $Expected.path
    $path = Join-Path $BasePath ($normalized.Replace("/", "\"))
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "冻结文件不存在：$normalized"
    }
    $item = Get-Item -LiteralPath $path
    if ($item.Length -ne [long]$Expected.length) {
        throw "冻结文件长度不一致：$normalized，当前 $($item.Length)，预期 $($Expected.length)"
    }
    $actualHash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $Expected.sha256) {
        throw "冻结文件哈希不一致：$normalized，当前 $actualHash，预期 $($Expected.sha256)"
    }
    if ($CheckTimestamp) {
        $actualTimestamp = $item.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss.fff")
        if ($actualTimestamp -ne $Expected.timestamp) {
            throw "冻结文件时间不一致：$normalized，当前 $actualTimestamp，预期 $($Expected.timestamp)"
        }
    }
}

foreach ($frozenFile in $frozenFiles) {
    Assert-FrozenFile -BasePath $projectRoot -Expected $frozenFile -CheckTimestamp
}

New-Item -ItemType Directory -Path $stageRoot | Out-Null
$sourceFiles = [System.Collections.Generic.List[string]]::new()

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
    New-Item -ItemType Directory -Path (Split-Path -Parent $targetPath) -Force | Out-Null
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
    "web/next-env.d.ts",
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
$currentDistFiles = @(Get-WhitelistedDirectoryFiles -RelativeDirectory "web\dist" | Sort-Object -Unique)
foreach ($file in $currentDistFiles) {
    Copy-ProjectFile -RelativePath $file
}

foreach ($frozenFile in $frozenFiles) {
    Assert-FrozenFile -BasePath $stageRoot -Expected $frozenFile
}

foreach ($scriptName in @("apply.sh", "rollback.sh", "README.md")) {
    $scriptSource = Join-Path $deployArtifactRoot $scriptName
    if (-not (Test-Path -LiteralPath $scriptSource -PathType Leaf)) {
        throw "缺少 r59 发布文件：$scriptSource"
    }
    $normalizedContent = (Get-Content -Raw -Encoding UTF8 -LiteralPath $scriptSource).Replace("`r", "")
    [System.IO.File]::WriteAllText((Join-Path $stageRoot $scriptName), $normalizedContent, $utf8NoBom)
}

$orderedSourceFiles = @($sourceFiles | Sort-Object -Unique)
$expectedApiSourceFiles = @(
    $apiFiles
    foreach ($directory in $apiDirectories) {
        Get-WhitelistedDirectoryFiles -RelativeDirectory $directory
    }
) | ForEach-Object { $_.Replace("\", "/") } | Sort-Object -Unique
$expectedWebSourceFiles = @(
    $webFiles
    foreach ($directory in $webDirectories) {
        Get-WhitelistedDirectoryFiles -RelativeDirectory $directory
    }
) | ForEach-Object { $_.Replace("\", "/") } | Sort-Object -Unique
$actualApiSourceFiles = @($orderedSourceFiles | Where-Object { $_ -like "api/*" })
$actualWebSourceFiles = @($orderedSourceFiles | Where-Object { $_ -like "web/*" })
if (Compare-Object $expectedApiSourceFiles $actualApiSourceFiles) {
    throw "API 源码清单与当前白名单源码不一致"
}
if (Compare-Object $expectedWebSourceFiles $actualWebSourceFiles) {
    throw "Web 源码清单与当前白名单源码不一致"
}

$stageDistFiles = @(Get-ChildItem -LiteralPath (Join-Path $stageRoot "web\dist") -Recurse -File | ForEach-Object {
    $_.FullName.Substring($stageRoot.Length + 1).Replace("\", "/")
} | Sort-Object -Unique)
if (Compare-Object $currentDistFiles $stageDistFiles) {
    throw "Web dist 文件清单与当前构建成品不一致"
}

foreach ($relativePath in @($orderedSourceFiles + $currentDistFiles)) {
    $sourcePath = Join-Path $projectRoot ($relativePath.Replace("/", "\"))
    $stagedPath = Join-Path $stageRoot ($relativePath.Replace("/", "\"))
    $sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
    $stagedHash = (Get-FileHash -LiteralPath $stagedPath -Algorithm SHA256).Hash
    if ($sourceHash -ne $stagedHash) {
        throw "暂存文件与当前磁盘不一致：$relativePath"
    }
}
[System.IO.File]::WriteAllText(
    (Join-Path $stageRoot "source-files.txt"),
    (($orderedSourceFiles -join "`n") + "`n"),
    $utf8NoBom
)

$stalePageFiles = @(
    "web/app/admin/theory-schools/page.tsx",
    "web/app/admin/theory-schools/[entityId]/page.tsx"
)
foreach ($relativePath in $stalePageFiles) {
    $currentPath = Join-Path $projectRoot ($relativePath.Replace("/", "\"))
    $r57Path = Join-Path $r57StageRoot ($relativePath.Replace("/", "\"))
    if (Test-Path -LiteralPath $currentPath) {
        throw "旧 page.tsx 在当前源码中仍存在：$relativePath"
    }
    if (-not (Test-Path -LiteralPath $r57Path -PathType Leaf)) {
        throw "无法从 r57 基线确认旧 page.tsx：$relativePath"
    }
}
[System.IO.File]::WriteAllText(
    (Join-Path $stageRoot "delete-source-files.txt"),
    (($stalePageFiles -join "`n") + "`n"),
    $utf8NoBom
)

$r57PageFiles = Get-ChildItem -LiteralPath (Join-Path $r57StageRoot "web\app") -Recurse -File -Filter "page.tsx" | ForEach-Object {
    $_.FullName.Substring($r57StageRoot.Length + 1).Replace("\", "/")
}
$currentPageFiles = Get-ChildItem -LiteralPath (Join-Path $projectRoot "web\app") -Recurse -File -Filter "page.tsx" | ForEach-Object {
    $_.FullName.Substring($projectRoot.Length + 1).Replace("\", "/")
}
$removedPageFiles = @($r57PageFiles | Where-Object { $_ -notin $currentPageFiles } | Sort-Object)
$pageRemovalDiff = @(Compare-Object ($stalePageFiles | Sort-Object) $removedPageFiles)
if ($pageRemovalDiff.Count -ne 0) {
    throw "r57 到当前源码的 page.tsx 删除差异与固定清单不一致"
}

$wheelPath = Join-Path $stageRoot "offline\python-wheels\PyYAML-6.0.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
$manifest = [ordered]@{
    release = "editorial-ui-2.6.1-r59"
    built_at = (Get-Date).ToString("o")
    production_base = [ordered]@{
        api = "2.6.1-r58"
        web = "2.6.1-r57"
    }
    source_files = $orderedSourceFiles.Count
    api_source_files = @($orderedSourceFiles | Where-Object { $_ -like "api/*" }).Count
    web_source_files = @($orderedSourceFiles | Where-Object { $_ -like "web/*" }).Count
    web_dist_files = $stageDistFiles.Count
    current_page_files = $currentPageFiles.Count
    deleted_page_files = $stalePageFiles
    required_service_cutover = @("api", "worker", "ingestion-worker", "beat", "web", "edge", "cloudflared")
    api_requirements_sha256 = (Get-FileHash -LiteralPath (Join-Path $stageRoot "api\requirements.txt") -Algorithm SHA256).Hash.ToLowerInvariant()
    web_package_lock_sha256 = (Get-FileHash -LiteralPath (Join-Path $stageRoot "web\package-lock.json") -Algorithm SHA256).Hash.ToLowerInvariant()
    pyyaml_wheel_sha256 = (Get-FileHash -LiteralPath $wheelPath -Algorithm SHA256).Hash.ToLowerInvariant()
    database_migrations_expected = $false
    semantic_v2_default = $false
    semantic_index_switch = $false
    includes_model_weights = $false
    includes_pdf = $false
    includes_environment = $false
    explore_scope = "frozen"
    frozen_files = $frozenFiles
}
[System.IO.File]::WriteAllText(
    (Join-Path $stageRoot "release-manifest.json"),
    (($manifest | ConvertTo-Json -Depth 6) + "`n"),
    $utf8NoBom
)

$requiredStageFiles = @(
    "api/config/version.py",
    "api/catalog/services/semantic_search.py",
    "web/app/editorial-v2.css",
    "web/app/editorial-workspaces.css",
    "web/components/route-transition.tsx",
    "web/public/favicon.ico",
    "web/public/editorial/library-architecture-hero.webp",
    "web/public/editorial/discipline-sociology.webp",
    "web/public/editorial/discipline-anthropology.webp",
    "web/public/editorial/discipline-ethnology.webp",
    "web/public/editorial/scholars-architecture-hero.webp",
    "web/public/editorial/topics-archive-hero.webp",
    "web/dist/server/index.js",
    "web/dist/client/favicon.ico",
    "web/dist/client/editorial/library-architecture-hero.webp",
    "web/dist/client/explore/explore-architecture-hero-v1.webp",
    "offline/python-wheels/PyYAML-6.0.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
)
foreach ($relativePath in $requiredStageFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $stageRoot ($relativePath.Replace("/", "\"))) -PathType Leaf)) {
        throw "r59 关键文件缺失：$relativePath"
    }
}

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
$archiveEntries = @(& tar.exe -tzf $archivePath)
if ($LASTEXITCODE -ne 0) {
    throw "tar 读取发布包失败，退出码 $LASTEXITCODE"
}
$unsafeEntries = @($archiveEntries | Where-Object {
    $_ -match "^/" -or $_ -match "(^|/)\.\.(/|$)" -or $_ -match "^[A-Za-z]:"
})
if ($unsafeEntries) {
    throw "发布包包含不安全路径：$($unsafeEntries -join ', ')"
}

New-Item -ItemType Directory -Path $verificationRoot | Out-Null
& tar.exe -xzf $archivePath -C $verificationRoot
if ($LASTEXITCODE -ne 0) {
    throw "tar 解压验证失败，退出码 $LASTEXITCODE"
}

$stageRelativeFiles = @(Get-ChildItem -LiteralPath $stageRoot -Recurse -File | ForEach-Object {
    $_.FullName.Substring($stageRoot.Length + 1).Replace("\", "/")
} | Sort-Object)
$verifiedRelativeFiles = @(Get-ChildItem -LiteralPath $verificationRoot -Recurse -File | ForEach-Object {
    $_.FullName.Substring($verificationRoot.Length + 1).Replace("\", "/")
} | Sort-Object)
$fileListDiff = @(Compare-Object $stageRelativeFiles $verifiedRelativeFiles)
if ($fileListDiff) {
    throw "归档解压后的文件清单与暂存目录不一致"
}

$verifiedChecksums = Get-Content -Encoding UTF8 (Join-Path $verificationRoot "SHA256SUMS")
foreach ($line in $verifiedChecksums) {
    if ($line -notmatch '^([0-9a-f]{64})  \./(.+)$') {
        throw "SHA256SUMS 行格式无效：$line"
    }
    $expectedHash = $Matches[1]
    $relativePath = Assert-SafeRelativePath $Matches[2]
    $verifiedPath = Join-Path $verificationRoot ($relativePath.Replace("/", "\"))
    if (-not (Test-Path -LiteralPath $verifiedPath -PathType Leaf)) {
        throw "SHA256SUMS 指向不存在的文件：$relativePath"
    }
    $actualHash = (Get-FileHash -LiteralPath $verifiedPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        throw "归档内文件哈希不一致：$relativePath"
    }
}
$verifiedChecksumPaths = @($verifiedChecksums | ForEach-Object {
    if ($_ -match '^([0-9a-f]{64})  \./(.+)$') { $Matches[2] }
} | Sort-Object -Unique)
$expectedChecksumPaths = @($verifiedRelativeFiles | Where-Object { $_ -ne "SHA256SUMS" } | Sort-Object -Unique)
if (Compare-Object $expectedChecksumPaths $verifiedChecksumPaths) {
    throw "SHA256SUMS 文件名清单与解压文件不一致"
}
$verifiedNonChecksumCount = @(Get-ChildItem -LiteralPath $verificationRoot -Recurse -File | Where-Object { $_.Name -ne "SHA256SUMS" }).Count
if ($verifiedChecksums.Count -ne $verifiedNonChecksumCount) {
    throw "SHA256SUMS 条目数与归档文件数不一致"
}

foreach ($frozenFile in $frozenFiles) {
    Assert-FrozenFile -BasePath $verificationRoot -Expected $frozenFile
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
    StageFiles = $stageRelativeFiles.Count
    StageBytes = $stageBytes
    SourceFiles = $orderedSourceFiles.Count
    ApiSourceFiles = $manifest.api_source_files
    WebSourceFiles = $manifest.web_source_files
    WebDistFiles = $manifest.web_dist_files
    CurrentPageFiles = $currentPageFiles.Count
    DeletedPageFiles = $stalePageFiles.Count
    ForbiddenFiles = @($forbidden).Count
    UnsafeArchivePaths = $unsafeEntries.Count
    VerifiedArchiveFiles = $verifiedRelativeFiles.Count
    VerificationRoot = $verificationRoot
}
