#Requires -Version 7.0
param([Parameter(Mandatory)][string]$SourceRoot,[Parameter(Mandatory)][string]$OutputRoot)
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$true
$source=[IO.Path]::GetFullPath($SourceRoot)
$output=[IO.Path]::GetFullPath($OutputRoot)
$version=$env:RELEASE_VERSION
$target=$env:RELEASE_TARGET
if ($target -notin @('darwin-aarch64','windows-x86_64') -or $version -notmatch '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') {throw '发行输入无效'}
if (($IsMacOS -and $target -ne 'darwin-aarch64') -or ($IsWindows -and $target -ne 'windows-x86_64') -or (!$IsMacOS -and !$IsWindows)) {throw '构建平台不匹配'}
# The hash-pinned private runtime is extracted into this disposable hosted runner.
if (!$env:LEESPDF_RUNTIME_ROOT -or !$env:JAVA_HOME) {throw 'runner 缺少 LEESPDF_RUNTIME_ROOT 或完整 JAVA_HOME'}
$seed=[IO.Path]::GetFullPath($env:LEESPDF_RUNTIME_ROOT)
$seedIndex=Get-Content (Join-Path $seed 'files.sha256.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($seedIndex.schemaVersion -ne 1 -or $seedIndex.target -ne $target) {throw '冻结运行时清单不匹配'}
$work=Join-Path $env:RUNNER_TEMP ('lees-pdf-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work,$output | Out-Null
$diagnostics=Join-Path $work 'private-build.log'
function Run([string]$Command,[string[]]$Arguments) {
    & $Command @Arguments *> $diagnostics
    if ($LASTEXITCODE -ne 0) {throw '构建或验证失败；私有诊断仅保留在隔离 runner'}
}
function Hash([string]$File) {(Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant()}
Push-Location $source
try {
    # Match native source bytes to the Windows checkout used for the frozen worker build.
    if($IsWindows){Run git @('-c','core.autocrlf=true','checkout-index','--force','--all')}
    $revision=(& git rev-parse HEAD).Trim()
    if ((& git rev-parse "$($env:SOURCE_TAG)^{commit}").Trim() -ne $revision) {throw 'Tag 与源码不一致'}
    Run git @('merge-base','--is-ancestor',$revision,'origin/main')
    $tauri=Get-Content 'apps/desktop/src-tauri/tauri.conf.json' -Raw -Encoding UTF8 | ConvertFrom-Json
    $desktop=Get-Content 'apps/desktop/package.json' -Raw -Encoding UTF8 | ConvertFrom-Json
    $cargo=Get-Content 'apps/desktop/src-tauri/Cargo.toml' -Raw -Encoding UTF8
    if ($tauri.version -ne $version -or $desktop.version -ne $version -or $cargo -notmatch ('(?m)^version\s*=\s*"'+[regex]::Escape($version)+'"') -or $tauri.identifier -ne 'app.lees.pdf') {throw '单一发行版本与配置不同步'}
    $public=Get-Content 'apps/desktop/src-tauri/updater/public-config.json' -Raw -Encoding UTF8 | ConvertFrom-Json
    $expected=Get-Content (Join-Path $PSScriptRoot 'public-config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($public.releasePublicKey -ne $expected.releasePublicKey -or $public.updaterPublicKey -ne $expected.updaterPublicKey) {throw '公私仓发行公钥不一致'}
    $runtime=Join-Path $work 'runtime'
    New-Item -ItemType Directory -Path $runtime | Out-Null
    foreach ($entry in $seedIndex.files) {
        if ($entry.path -match '(^/|^[A-Za-z]:|\\|(^|/)\.\.(/|$))' -or $entry.path -match '(?i)\.(pdb|map|java|cpp|rs|ts|tsx|key|pem|pfx|log)$') {throw '运行时包含不允许公开的文件'}
        $file=Join-Path $seed $entry.path
        if ((Hash $file) -ne $entry.sha256) {throw '冻结运行时哈希不匹配'}
        $destination=Join-Path $runtime $entry.path
        New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
        Copy-Item -LiteralPath $file -Destination $destination
    }
    $sourceHashes=@{}
    if($env:LEESPDF_RUNTIME_SOURCE_INDEX){
        $identity=Get-Content $env:LEESPDF_RUNTIME_SOURCE_INDEX -Raw -Encoding UTF8 | ConvertFrom-Json
        if($target -ne 'windows-x86_64' -or $identity.schemaVersion -ne 1 -or $identity.target -ne $target -or $identity.runtimeArchiveSha256 -ne $env:LEESPDF_RUNTIME_ARCHIVE_SHA256 -or $identity.sourceRevision -ne $revision){throw 'Canonical source identity does not bind this runtime and source Tag'}
        foreach($item in $identity.nativeSources){
            if($sourceHashes.ContainsKey($item.path)){throw 'Duplicate canonical native source'}
            $sourceHashes[$item.path]=$item
        }
        if($sourceHashes.Count -ne $seedIndex.nativeSources.Count){throw 'Canonical source coverage differs'}
    }
    # Worker source hashes bind frozen native binaries to this exact source revision.

    foreach ($entry in $seedIndex.nativeSources) {
        if ($entry.path -notmatch '^native/(scan-worker|font-worker)/' -or $entry.path.Contains('..')){throw 'Invalid native source path'}
        if($sourceHashes.Count){
            $expected=$sourceHashes[$entry.path]
            if(!$expected -or $expected.frozenSha256 -ne $entry.sha256){throw 'Canonical source is not tied to the frozen compiler input'}
            $content=[Text.UTF8Encoding]::new($false,$true).GetString([IO.File]::ReadAllBytes((Join-Path $source $entry.path))).Replace("`r`n","`n")
            $actual=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($content))).ToLowerInvariant()
            if($actual -ne $expected.sha256){throw 'Native source differs beyond line endings'}
        }elseif((Hash (Join-Path $source $entry.path)) -ne $entry.sha256){throw 'Native worker source identity mismatch'}
    }
    $nativeFiles=@(& git ls-files native/scan-worker native/font-worker | Sort-Object)
    $boundFiles=@($seedIndex.nativeSources | ForEach-Object path | Sort-Object -Unique)
    if ($nativeFiles.Count -lt 2 -or @(Compare-Object $nativeFiles $boundFiles).Count -ne 0) {throw '冻结运行时必须绑定完整 worker 来源清单'}
    $dependencies=Get-Content 'services/pdf-core/DEPENDENCIES.json' -Raw -Encoding UTF8 | ConvertFrom-Json
    $jars=@($dependencies.runtimeJars | ForEach-Object {Join-Path $runtime ('m2/'+(Split-Path $_ -Leaf))})
    foreach($jar in $jars) {if((Hash $jar) -ne $dependencies.sha256.(Split-Path $jar -Leaf)){throw 'Java 依赖哈希不匹配'}}
    $classes=Join-Path $work 'classes';New-Item -ItemType Directory -Path $classes | Out-Null
    $javaSources=@(Get-ChildItem 'services/pdf-core/src/main/java' -Recurse -Filter '*.java' | ForEach-Object FullName)
    $argumentFile=Join-Path $work 'javac.args'
    @('--release','25','-encoding','UTF-8','-cp',('"'+(($jars -join [IO.Path]::PathSeparator).Replace('\','/'))+'"'),'-d',('"'+$classes.Replace('\','/')+'"'))+@($javaSources | ForEach-Object {'"'+$_.Replace('\','/')+'"'}) | Set-Content $argumentFile -Encoding utf8NoBOM
    Run (Join-Path $env:JAVA_HOME 'bin/javac') @('@'+$argumentFile)
    Run (Join-Path $env:JAVA_HOME 'bin/jar') @('--create','--file',(Join-Path $runtime 'lees-pdf-core.jar'),'--main-class','pdf.lees.core.Main','-C',$classes,'.')
    Run npm @('ci','--no-audit','--no-fund')
    Run node @('node_modules/typescript/bin/tsc','-p','apps/desktop/tsconfig.json','--noEmit')
    Run cargo @('fetch','--manifest-path','apps/desktop/src-tauri/Cargo.toml')
    Run python @('scripts/release/collect-licenses.py',$source,$runtime)
    # Complete license material is a prerequisite, including JDK, PDFium, fonts, native SDKs and models.
    if (!(Test-Path (Join-Path $runtime 'licenses/THIRD-PARTY-NOTICES.txt'))) {throw '冻结运行时缺少完整第三方分发材料'}
    $runtimeFiles=@(Get-ChildItem $runtime -File -Recurse | ForEach-Object {@{path=[IO.Path]::GetRelativePath($runtime,$_.FullName).Replace('\','/');sha256=Hash $_.FullName;size=$_.Length}} | Sort-Object path)
    @{schemaVersion=1;target=$target;files=$runtimeFiles} | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $runtime 'files.sha256.json') -Encoding utf8NoBOM
    $config=@{bundle=@{resources=@{};createUpdaterArtifacts=$true};plugins=@{updater=@{pubkey=$public.updaterPublicKey}}}
    $config.bundle.resources[$runtime+'/']='runtime/'
    if ($IsMacOS) {$config.bundle.targets=@('app','dmg');$config.bundle.macOS=@{signingIdentity='-';minimumSystemVersion='26.0'}}
    else {
        if (!$env:LEESPDF_WINDOWS_PFX -or !$env:LEESPDF_WINDOWS_PFX_PASSWORD) {throw '公开仓缺少本产品 Windows 签名证书 Secret'}
        $pfx=Join-Path $work 'publisher.pfx';[IO.File]::WriteAllBytes($pfx,[Convert]::FromBase64String($env:LEESPDF_WINDOWS_PFX))
        $cert=Import-PfxCertificate -FilePath $pfx -CertStoreLocation Cert:\CurrentUser\My -Password (ConvertTo-SecureString $env:LEESPDF_WINDOWS_PFX_PASSWORD -AsPlainText -Force)
        if ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($cert.RawData)).ToLowerInvariant() -ne $public.windowsCertificateSha256) {throw 'Windows 发行证书身份错误'}
        $certificateName="lees-pdf-$version-$target-publisher.cer"
        $certificateFile=Join-Path $output $certificateName
        Export-Certificate -Cert $cert -FilePath $certificateFile | Out-Null
        # Trust only the already hash-verified public certificate on this disposable runner.
        Import-Certificate -FilePath $certificateFile -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
        Import-Certificate -FilePath $certificateFile -CertStoreLocation Cert:\CurrentUser\TrustedPeople | Out-Null
        $config.bundle.targets=@('nsis');$config.bundle.windows=@{certificateThumbprint=$cert.Thumbprint;digestAlgorithm='sha256';timestampUrl='http://timestamp.digicert.com';minimumWebview2Version='109.0.1518.78';nsis=@{installerHooks='windows/file-association-hooks.nsh'}}
    }
    $platformConfig=if($IsMacOS){'apps/desktop/src-tauri/tauri.macos.conf.json'}else{'apps/desktop/src-tauri/tauri.windows.conf.json'}
    # Replace this disposable checkout's platform resource mapping, so old .tools paths cannot be merged in.
    $config | ConvertTo-Json -Depth 9 | Set-Content $platformConfig -Encoding utf8NoBOM
    $configFile=Join-Path $work 'release-config.json';$config | ConvertTo-Json -Depth 9 | Set-Content $configFile -Encoding utf8NoBOM
    $env:LEESPDF_RELEASE_BUILD='1';$env:CARGO_TARGET_DIR=Join-Path $work 'cargo'
    Run npm @('run','tauri','--workspace','@lees/desktop','--','build','--config',$configFile)
    $bundle=Join-Path $env:CARGO_TARGET_DIR 'release/bundle'
    $updater=if($IsMacOS){Get-ChildItem $bundle -Recurse -Filter '*.app.tar.gz'}else{Get-ChildItem $bundle -Recurse -Filter '*-setup.exe'}
    $installer=if($IsMacOS){Get-ChildItem $bundle -Recurse -Filter '*.dmg'}else{$updater}
    if (@($updater).Count -ne 1 -or @($installer).Count -ne 1) {throw '安装包不唯一'}
    if($IsWindows){if((Get-AuthenticodeSignature $installer.FullName).Status -ne 'Valid'){throw 'Windows 签名未通过系统信任核对'}}
    else { $app=Get-ChildItem (Join-Path $bundle 'macos') -Directory -Filter '*.app';Run codesign @('--verify','--deep','--strict',$app.FullName) }
    $updateName="lees-pdf-$version-$target"+$(if($IsMacOS){'.app.tar.gz'}else{'-setup.exe'})
    $installName=if($IsMacOS){"lees-pdf-$version-$target.dmg"}else{$updateName}
    Copy-Item $updater.FullName (Join-Path $output $updateName)
    if($IsMacOS){Copy-Item $installer.FullName (Join-Path $output $installName)}
    $noticeName="lees-pdf-$version-$target-NOTICES.txt"
    Copy-Item (Join-Path $runtime 'licenses/THIRD-PARTY-NOTICES.txt') (Join-Path $output $noticeName)
    $inventoryName="lees-pdf-$version-$target-runtime.json"
    Copy-Item (Join-Path $runtime 'files.sha256.json') (Join-Path $output $inventoryName)
    @{target=$target;version=$version;sourceRevision=$revision;bundleId='app.lees.pdf';updater=$updateName;installer=$installName;updaterSignature=(Get-Content ($updater.FullName+'.sig') -Raw -Encoding UTF8).Trim();runtimeManifestSha256=Hash (Join-Path $runtime 'files.sha256.json');signerCertificateSha256=$(if($IsWindows){$public.windowsCertificateSha256}else{$null});materials=@($noticeName,$inventoryName)+$(if($IsWindows){@($certificateName)}else{@()})} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $output "$target.json") -Encoding utf8NoBOM
    Copy-Item 'apps/desktop/src-tauri/updater/public-config.json' (Join-Path $output "$target-public-config.json")
} finally {Pop-Location}
Write-Output "Lee’s PDF $target $version 发行资产已核对；尚未发布"
