#Requires -Version 7.0
param([Parameter(Mandatory)][string]$SourceRoot,[Parameter(Mandatory)][string]$OutputRoot)
$ErrorActionPreference='Stop'
$source=[IO.Path]::GetFullPath($SourceRoot)
$output=[IO.Path]::GetFullPath($OutputRoot)
if(!$IsWindows -or $env:RELEASE_TARGET -ne 'windows-x86_64'){throw '原生macOS尚待验收；禁止回落到旧应用构建'}
if($env:SOURCE_TAG -notmatch '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' -or $env:RELEASE_VERSION -ne $env:SOURCE_TAG.Substring(1)){throw '源码Tag或版本无效'}
$revision=(& git -C $source rev-parse HEAD).Trim()
if((& git -C $source rev-parse "$($env:SOURCE_TAG)^{commit}").Trim() -ne $revision){throw '源码Tag与检出不符'}
& git -C $source merge-base --is-ancestor $revision origin/main
if($LASTEXITCODE){throw '源码Tag不在主线'}
if((Get-Content -Raw -Encoding UTF8 (Join-Path $source 'package.json') | ConvertFrom-Json).version -ne $env:RELEASE_VERSION){throw '单一产品版本不符'}
$entry=Join-Path $source 'scripts/release/build-native-candidate.ps1'
if(!(Test-Path -LiteralPath $entry)){throw '该源码Tag不包含原生发行入口；不构建旧应用'}
$cache='I:/DevCache'
$env:TEMP=Join-Path $cache 'Temp';$env:TMP=$env:TEMP
$env:CARGO_HOME=Join-Path $cache 'cargo';$env:CARGO_TARGET_DIR=Join-Path $cache 'lees-pdf-native-target';$env:CARGO_INCREMENTAL='0'
$env:PYTHONPYCACHEPREFIX=Join-Path $cache 'python-pycache';$env:PYTHONUTF8='1';$env:NPM_CONFIG_CACHE=Join-Path $cache 'npm-cache'
$private=Join-Path $cache 'lees-pdf-private-signing'
$null=New-Item -ItemType Directory -Force -Path $private,$env:TEMP,$env:CARGO_HOME
if(!$env:LEESPDF_WINDOWS_PFX -or !$env:LEESPDF_WINDOWS_PFX_PASSWORD){throw '缺少受保护的Windows签名凭据'}
[IO.File]::WriteAllBytes((Join-Path $private 'lees-pdf-windows-signing.pfx'),[Convert]::FromBase64String($env:LEESPDF_WINDOWS_PFX))
[IO.File]::WriteAllText((Join-Path $private 'lees-pdf-windows-signing.txt'),$env:LEESPDF_WINDOWS_PFX_PASSWORD,[Text.UTF8Encoding]::new($false))
$certificate=[Security.Cryptography.X509Certificates.X509Certificate2]::new((Join-Path $private 'lees-pdf-windows-signing.pfx'),$env:LEESPDF_WINDOWS_PFX_PASSWORD,[Security.Cryptography.X509Certificates.X509KeyStorageFlags]::EphemeralKeySet)
try {
    $pinned=Get-Content -Raw -Encoding UTF8 (Join-Path $source 'crates/desktop-update/assets/public-config.json') | ConvertFrom-Json
    $public=Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'public-config.json') | ConvertFrom-Json
    if($public.releasePublicKey -ne $pinned.releasePublicKey -or $public.updaterPublicKey -ne $pinned.updaterPublicKey -or [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($certificate.RawData)).ToLowerInvariant() -ne $pinned.windowsCertificateSha256){throw '公私仓签名身份不一致'}
    # Trust only the hash-verified public certificate on this disposable CI user.
    $certFile=Join-Path $private 'publisher.cer';[IO.File]::WriteAllBytes($certFile,$certificate.RawData)
    $null=Import-Certificate -FilePath $certFile -CertStoreLocation Cert:\CurrentUser\Root
    $null=Import-Certificate -FilePath $certFile -CertStoreLocation Cert:\CurrentUser\TrustedPeople
}finally{$certificate.Dispose()}
$tools=Get-Content -Raw -Encoding UTF8 (Join-Path $source 'native/dependencies/windows-tools.json') | ConvertFrom-Json
$diagnostics=Join-Path $cache 'lees-pdf-native-build.log'
$candidate=Join-Path $cache 'lees-pdf-native-candidate'
$nativePreference=$PSNativeCommandUseErrorActionPreference
$PSNativeCommandUseErrorActionPreference=$false
try {
    Push-Location $source
    try {
        & cargo fetch --locked *> $diagnostics
        if($LASTEXITCODE){throw '原生锁定依赖准备失败，私有诊断留在runner'}
        & python -m pip install cryptography==50.0.2 *>> $diagnostics
        if($LASTEXITCODE){throw '签名工具依赖准备失败'}
        $signer=Join-Path $cache 'lees-pdf-updater-signer'
        & npm install --prefix $signer --no-audit --no-fund --ignore-scripts "$($tools.updaterSigner.package)@$($tools.updaterSigner.version)" *>> $diagnostics
        if($LASTEXITCODE){throw '版本绑定签名工具准备失败'}
        $archive=Join-Path $cache 'nsis-3.11.zip'
        Invoke-WebRequest -Uri $tools.nsis.url -OutFile $archive
        if((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $tools.nsis.sha256){throw 'NSIS固定来源校验失败'}
        $nsis=Join-Path $cache 'nsis-3.11';Expand-Archive -LiteralPath $archive -DestinationPath $nsis
        $compiler=@(Get-ChildItem -LiteralPath $nsis -Recurse -File -Filter makensis.exe)
        if($compiler.Count -ne 1){throw 'NSIS入口不唯一'}
        $clang=Split-Path (Get-Command clang.exe -ErrorAction Stop).Source -Parent
        if(!(Test-Path -LiteralPath (Join-Path $clang 'libclang.dll'))){throw 'runner缺少现有LLVM libclang'}
        & pwsh -NoProfile -File $entry -OutputRoot $candidate -SignBackup $private -Makensis $compiler[0].FullName -UpdaterSigner (Join-Path $signer 'node_modules/@tauri-apps/cli/tauri.js') -ClangDirectory $clang *>> $diagnostics
        if($LASTEXITCODE){throw '原生候选构建/验签失败，私有诊断留在runner'}
    }finally{Pop-Location}
}finally{$PSNativeCommandUseErrorActionPreference=$nativePreference}
$row=Get-Content -Raw -Encoding UTF8 (Join-Path $candidate 'windows-x86_64.json') | ConvertFrom-Json
if(!$row.native -or $row.sourceDirty -or $row.sourceRevision -ne $revision -or $row.version -ne $env:RELEASE_VERSION){throw '候选源码或生产身份不符'}
$null=New-Item -ItemType Directory -Path $output
$allowed=Get-Content -Raw -Encoding UTF8 (Join-Path $candidate 'candidate-files.json') | ConvertFrom-Json
if($allowed.Count -gt 10){throw '候选材料超过边界'}
foreach($name in $allowed){
    if($name -ne [IO.Path]::GetFileName($name) -or $name -match '(?i)\.(pfx|pem|key|log|pdb|rs|java|ts|tsx)$'){throw '候选输出含私有材料'}
    Copy-Item -LiteralPath (Join-Path $candidate $name) -Destination (Join-Path $output $name)
}
Write-Output 'Windows原生候选与版本绑定签名已核对；未发布，macOS待验。'
