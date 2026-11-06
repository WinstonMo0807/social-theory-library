$ErrorActionPreference = 'Stop'
$showcaseRoot = $PSScriptRoot
& node (Join-Path $showcaseRoot 'build.mjs')
if ($LASTEXITCODE -ne 0) { throw '展示构建失败，请查看上方错误。' }
& node (Join-Path $showcaseRoot 'serve.mjs')
