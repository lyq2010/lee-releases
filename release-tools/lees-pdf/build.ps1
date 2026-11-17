#Requires -Version 7.0
param([Parameter(Mandatory)][string]$SourceRoot,[Parameter(Mandatory)][string]$OutputRoot)
$ErrorActionPreference='Stop'
$source=[IO.Path]::GetFullPath($SourceRoot)
$output=[IO.Path]::GetFullPath($OutputRoot)
$version=$env:RELEASE_VERSION
$target=$env:RELEASE_TARGET
if($env:SOURCE_TAG -notmatch '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' -or $env:RELEASE_VERSION -ne $env:SOURCE_TAG.Substring(1)){throw '源码Tag或版本无效'}
if ($target -notin @('darwin-aarch64','windows-x86_64') -or $version -notmatch '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') {throw '发行输入无效'}
if (($IsMacOS -and $target -ne 'darwin-aarch64') -or ($IsWindows -and $target -ne 'windows-x86_64') -or (!$IsMacOS -and !$IsWindows)) {throw '构建平台不匹配'}
# Match the shared mirror convention: a bare COS hostname is an HTTPS base.
$cosBase=([string]$env:LEESPDF_COS_BASE_URL).Trim().TrimEnd('/')
if(!$cosBase.Contains('://')){$cosBase='https://'+$cosBase}
$cosUri=$null
if(![Uri]::TryCreate($cosBase,[UriKind]::Absolute,[ref]$cosUri) -or $cosUri.Scheme -ne 'https' -or !$cosUri.Host -or $cosUri.UserInfo -or $cosUri.Query -or $cosUri.Fragment){throw 'Clean HTTPS COS base URL is required'}
$env:LEESPDF_COS_BASE_URL=$cosUri.AbsoluteUri.TrimEnd('/')+'/'
$revision=(& git -C $source rev-parse HEAD).Trim()
if((& git -C $source rev-parse "$($env:SOURCE_TAG)^{commit}").Trim() -ne $revision){throw '源码Tag与检出不符'}
& git -C $source merge-base --is-ancestor $revision origin/main
if($LASTEXITCODE){throw '源码Tag不在主线'}
if((Get-Content -Raw -Encoding UTF8 (Join-Path $source 'package.json') | ConvertFrom-Json).version -ne $env:RELEASE_VERSION){throw '单一产品版本不符'}
$notesFile=Join-Path $env:RUNNER_TEMP ("lees-pdf-release-notes-$target.txt")
$extractNotes=@'
import pathlib,re,sys
source=pathlib.Path(sys.argv[1]); version=sys.argv[2]; output=pathlib.Path(sys.argv[3])
text=source.joinpath("CHANGELOG.md").read_text(encoding="utf-8").lstrip("\ufeff").replace("\r\n","\n").replace("\r","\n")
headings=[(m.start(),m.group(1)) for m in re.finditer(r"^## (.+)$",text,re.M)]
matching=[item for item in headings if item[1]==version or re.fullmatch(re.escape(version)+r" \(\d{4}-\d{2}-\d{2}\)",item[1])]
if len(matching)!=1: raise SystemExit("目标版本更新说明缺失或无效")
index=headings.index(matching[0])
end=headings[index+1][0] if index+1<len(headings) else len(text)
body=text[matching[0][0]:end].strip()+"\n"
if not re.match(rf"^## {re.escape(version)}(?: \(\d{{4}}-\d{{2}}-\d{{2}}\))?$",body.splitlines()[0]) or not re.search(r"^[-*] \S",body,re.M) or len(re.findall(r"^## ",body,re.M))!=1 or len(body.encode())>16000:
    raise SystemExit("目标版本更新说明缺失或无效")
output.write_text(body,encoding="utf-8")
'@
$extractFile=Join-Path $env:RUNNER_TEMP ("lees-pdf-extract-notes-$target.py")
Set-Content -LiteralPath $extractFile -Value $extractNotes -Encoding utf8NoBOM
$python=if(Get-Command python3 -ErrorAction SilentlyContinue){'python3'}elseif(Get-Command python -ErrorAction SilentlyContinue){'python'}else{throw '缺少 Python'}
& $python $extractFile $source $version $notesFile
if($LASTEXITCODE){throw '更新说明提取失败'}
$public=Get-Content -Raw -Encoding UTF8 (Join-Path $source 'crates/desktop-update/assets/public-config.json') | ConvertFrom-Json
$expected=Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'public-config.json') | ConvertFrom-Json
if($public.releasePublicKey -ne $expected.releasePublicKey -or $public.updaterPublicKey -ne $expected.updaterPublicKey){throw '公私仓发行公钥不一致'}
$null=New-Item -ItemType Directory -Force -Path $output
$nativePreference=$PSNativeCommandUseErrorActionPreference
$PSNativeCommandUseErrorActionPreference=$false
try {
if($IsWindows){
    $entry=Join-Path $source 'scripts/release/build-native-candidate.ps1'
    if(!(Test-Path -LiteralPath $entry)){throw '该源码Tag不包含原生 Windows 发行入口；不构建旧应用'}
    if(!(Test-Path -LiteralPath (Join-Path $source 'crates/desktop-update/examples/sign-native-package.rs'))){throw '该源码Tag不包含原生更新签名工具；不回落到旧签名链'}
    $cache='I:/DevCache'
    $env:TEMP=Join-Path $cache 'Temp';$env:TMP=$env:TEMP
    $env:CARGO_HOME=Join-Path $cache 'cargo';$env:CARGO_TARGET_DIR=Join-Path $cache 'lees-pdf-native-target';$env:CARGO_INCREMENTAL='0'
    $env:PYTHONPYCACHEPREFIX=Join-Path $cache 'python-pycache';$env:PYTHONUTF8='1'
    $private=Join-Path $cache 'lees-pdf-private-signing'
    $null=New-Item -ItemType Directory -Force -Path $private,$env:TEMP,$env:CARGO_HOME
    if(!$env:LEESPDF_WINDOWS_PFX -or !$env:LEESPDF_WINDOWS_PFX_PASSWORD){throw '缺少受保护的Windows签名凭据'}
    [IO.File]::WriteAllBytes((Join-Path $private 'lees-pdf-windows-signing.pfx'),[Convert]::FromBase64String($env:LEESPDF_WINDOWS_PFX))
    [IO.File]::WriteAllText((Join-Path $private 'lees-pdf-windows-signing.txt'),$env:LEESPDF_WINDOWS_PFX_PASSWORD,[Text.UTF8Encoding]::new($false))
    $certificate=[Security.Cryptography.X509Certificates.X509Certificate2]::new((Join-Path $private 'lees-pdf-windows-signing.pfx'),$env:LEESPDF_WINDOWS_PFX_PASSWORD,[Security.Cryptography.X509Certificates.X509KeyStorageFlags]::EphemeralKeySet)
    try {
        if([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($certificate.RawData)).ToLowerInvariant() -ne $public.windowsCertificateSha256){throw '公私仓签名身份不一致'}
        $certFile=Join-Path $private 'publisher.cer';[IO.File]::WriteAllBytes($certFile,$certificate.RawData)
        $null=Import-Certificate -FilePath $certFile -CertStoreLocation Cert:\CurrentUser\Root
        $null=Import-Certificate -FilePath $certFile -CertStoreLocation Cert:\CurrentUser\TrustedPeople
    }finally{$certificate.Dispose()}
    $tools=Get-Content -Raw -Encoding UTF8 (Join-Path $source 'native/dependencies/windows-tools.json') | ConvertFrom-Json
    $diagnostics=Join-Path $cache 'lees-pdf-native-build.log'
    $candidate=Join-Path $cache 'lees-pdf-native-candidate'
    Push-Location $source
    try {
        & $python (Join-Path $source 'scripts/release/logged_build.py') --log $diagnostics --phase fetch --timeout 900 -- cargo fetch --locked --target x86_64-pc-windows-msvc
        if($LASTEXITCODE){throw '原生锁定依赖准备失败，私有诊断留在runner'}
        & $python (Join-Path $source 'scripts/release/logged_build.py') --log $diagnostics --phase tools --timeout 900 -- $python -m pip install cryptography==50.0.2
        if($LASTEXITCODE){throw '签名工具依赖准备失败'}
        $archive=Join-Path $cache 'nsis-3.11.zip'
        Invoke-WebRequest -Uri $tools.nsis.url -OutFile $archive
        if((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $tools.nsis.sha256){throw 'NSIS固定来源校验失败'}
        $nsis=Join-Path $cache 'nsis-3.11';Expand-Archive -LiteralPath $archive -DestinationPath $nsis
        $compiler=@(Get-ChildItem -LiteralPath $nsis -Recurse -File -Filter makensis.exe)
        if($compiler.Count -ne 1){throw 'NSIS入口不唯一'}
        $clang=Split-Path (Get-Command clang.exe -ErrorAction Stop).Source -Parent
        if(!(Test-Path -LiteralPath (Join-Path $clang 'libclang.dll'))){throw 'runner缺少现有LLVM libclang'}
        & $python (Join-Path $source 'scripts/release/logged_build.py') --log $diagnostics --phase windows -- pwsh -NoProfile -File $entry -OutputRoot $candidate -SignBackup $private -Makensis $compiler[0].FullName -ClangDirectory $clang -ReleaseNotes $notesFile
        if($LASTEXITCODE){throw '原生 Windows 构建/验签失败，私有诊断留在runner'}
    }finally{Pop-Location}
    $row=Get-Content -Raw -Encoding UTF8 (Join-Path $candidate 'windows-x86_64.json') | ConvertFrom-Json
    if(!$row.native -or $row.sourceDirty -or $row.sourceRevision -ne $revision -or $row.version -ne $env:RELEASE_VERSION){throw '发行源码或生产身份不符'}
    $allowed=Get-Content -Raw -Encoding UTF8 (Join-Path $candidate 'release-files.json') | ConvertFrom-Json
    if($allowed.Count -gt 12){throw '发行材料超过边界'}
    foreach($name in $allowed){
        if($name -ne [IO.Path]::GetFileName($name) -or $name -match '(?i)\.(pfx|pem|key|log|pdb|rs|java|ts|tsx)$'){throw '发行输出含私有材料'}
        Copy-Item -LiteralPath (Join-Path $candidate $name) -Destination (Join-Path $output $name)
    }
} else {
    $entry=Join-Path $source 'scripts/release/build-native-macos-release.ps1'
    if(!(Test-Path -LiteralPath $entry)){throw '该源码Tag不包含原生 macOS 发行入口；不构建旧应用'}
    if(!(Test-Path -LiteralPath (Join-Path $source 'crates/desktop-update/examples/sign-native-package.rs'))){throw '该源码Tag不包含原生更新签名工具；不回落到旧签名链'}
    if(!$env:DEVELOPER_DIR -or !(Test-Path -LiteralPath $env:DEVELOPER_DIR)){throw '缺少可用的 Xcode Developer 目录'}
    $cache=Join-Path $env:RUNNER_TEMP 'lees-pdf-native-macos'
    $tools=Join-Path $cache 'tools'
    $null=New-Item -ItemType Directory -Force -Path $cache,$tools
    if(Test-Path -LiteralPath (Join-Path $source '.tools')){throw '源码检出含未知依赖目录'}
    $null=New-Item -ItemType SymbolicLink -Path (Join-Path $source '.tools') -Target $tools
    if(!$env:CARGO_HOME){$env:CARGO_HOME=Join-Path $cache 'cargo'}
    $env:CARGO_TARGET_DIR=Join-Path $cache 'cargo-target'
    $env:CARGO_INCREMENTAL='0'
    $env:MACOSX_DEPLOYMENT_TARGET='26.0'
    $env:PYTHONUTF8='1'
    $null=New-Item -ItemType Directory -Force -Path $env:CARGO_HOME,$env:CARGO_TARGET_DIR
    # The source entry validates the unresolved source/.tools prefix; create the real parent, pass the source-relative path.
    $null=New-Item -ItemType Directory -Force -Path (Join-Path $tools 'native-release')
    $candidate=Join-Path $source '.tools/native-release/candidate'
    $diagnostics=Join-Path $cache 'lees-pdf-native-build.log'
    Push-Location $source
    try {
        & $python (Join-Path $source 'scripts/release/logged_build.py') --log $diagnostics --phase fetch --timeout 900 -- cargo fetch --locked --target aarch64-apple-darwin
        if($LASTEXITCODE){throw '原生锁定依赖准备失败，私有诊断留在runner'}
        # macOS updater signing uses the Rust Minisign tool; do not install Python cryptography on the system interpreter.
        if(!(Get-Command cmake -ErrorAction SilentlyContinue)){throw 'runner缺少 cmake'}
        if(!(Get-Command python3 -ErrorAction SilentlyContinue)){throw 'runner缺少 python3'}
        & $python (Join-Path $source 'scripts/release/logged_build.py') --log $diagnostics --phase macos -- pwsh -NoProfile -File $entry -OutputRoot $candidate -ReleaseNotes $notesFile
        if($LASTEXITCODE){
            throw '原生 macOS 构建/验签失败'
        }
    }finally{Pop-Location}
    $row=Get-Content -Raw -Encoding UTF8 (Join-Path $candidate 'darwin-aarch64.json') | ConvertFrom-Json
    if(!$row.native -or $row.sourceDirty -or $row.sourceRevision -ne $revision -or $row.version -ne $env:RELEASE_VERSION){throw '发行源码或生产身份不符'}
    $allowed=Get-Content -Raw -Encoding UTF8 (Join-Path $candidate 'release-files.json') | ConvertFrom-Json
    if($allowed.Count -gt 12){throw '发行材料超过边界'}
    foreach($name in $allowed){
        if($name -ne [IO.Path]::GetFileName($name) -or $name -match '(?i)\.(pfx|pem|key|log|pdb|rs|java|ts|tsx)$'){throw '发行输出含私有材料'}
        Copy-Item -LiteralPath (Join-Path $candidate $name) -Destination (Join-Path $output $name)
    }
}
} finally { $PSNativeCommandUseErrorActionPreference=$nativePreference }
Write-Output "Lee’s PDF $target $version 原生发行资产已核对；尚未公布"
