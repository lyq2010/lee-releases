#Requires -Version 7.0
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$true
if ($env:RUNTIME_TAG -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$' -or $env:RUNTIME_SHA256 -notmatch '^[a-fA-F0-9]{64}$' -or $env:RELEASE_TARGET -notin @('windows-x86_64','darwin-aarch64')) {throw '私有运行时 Tag、平台或公开仓固定 SHA-256 变量未配置'}
$directory=Join-Path $env:RUNNER_TEMP ('lees-pdf-runtime-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $directory | Out-Null
$name="lees-pdf-runtime-$($env:RELEASE_TARGET).tar.gz"
& gh release download $env:RUNTIME_TAG --repo lyq2010/lees-pdf --pattern $name --dir $directory
if($LASTEXITCODE -ne 0){throw '私有运行时下载失败'}
$archive=Join-Path $directory $name
if ((Get-FileHash $archive).Hash -ne $env:RUNTIME_SHA256) {throw '私有运行时归档哈希不匹配'}
$entries=& tar -tzf $archive
if ($entries | Where-Object {$_ -match '(^/|^[A-Za-z]:|\\|(^|/)\.\.(/|$))' -or $_ -notmatch '^runtime(/|$)'}) {throw '运行时归档包含越界路径'}
& tar -xzf $archive -C $directory
if ($LASTEXITCODE -ne 0) {throw '运行时解压失败'}
$root=Join-Path $directory 'runtime'
if (!(Test-Path (Join-Path $root 'files.sha256.json'))) {throw '运行时清单缺失'}
"LEESPDF_RUNTIME_ROOT=$root" | Out-File $env:GITHUB_ENV -Encoding utf8 -Append

if($env:RELEASE_TARGET -eq 'windows-x86_64'){
    if($env:RUNTIME_SOURCES_SHA256 -notmatch '^[a-fA-F0-9]{64}$'){throw 'Windows source normalization identity is missing'}
    $sourceName='lees-pdf-runtime-windows-x86_64-sources.json'
    & gh release download $env:RUNTIME_TAG --repo lyq2010/lees-pdf --pattern $sourceName --dir $directory
    if($LASTEXITCODE){throw 'Private source identity download failed'}
    $sourceIndex=Join-Path $directory $sourceName
    if((Get-FileHash $sourceIndex).Hash -ne $env:RUNTIME_SOURCES_SHA256){throw 'Source normalization identity mismatch'}
    "LEESPDF_RUNTIME_SOURCE_INDEX=$sourceIndex" | Out-File $env:GITHUB_ENV -Encoding utf8 -Append
    "LEESPDF_RUNTIME_ARCHIVE_SHA256=$($env:RUNTIME_SHA256)" | Out-File $env:GITHUB_ENV -Encoding utf8 -Append
}
