#Requires -Version 7.0
param([Parameter(Mandatory)][string]$SourceRoot)
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$true
$source=[IO.Path]::GetFullPath($SourceRoot)
$target=$env:RELEASE_TARGET
if(($IsWindows -and $target -ne 'windows-x86_64') -or ($IsMacOS -and $target -ne 'darwin-aarch64') -or (!$IsWindows -and !$IsMacOS)){throw 'Dependency preparation target mismatch'}
if($env:SOURCE_TAG -notmatch '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'){throw 'Invalid source Tag'}
$revision=(& git -C $source rev-parse HEAD).Trim()
if((& git -C $source rev-parse "$($env:SOURCE_TAG)^{commit}").Trim() -ne $revision){throw 'Source Tag differs from checkout'}
& git -C $source merge-base --is-ancestor $revision origin/main
if($LASTEXITCODE){throw 'Source Tag is not on main'}
# Normalize before compilation and indexing, never after native inputs have been hashed.
if($IsWindows){& git -C $source -c core.autocrlf=true checkout-index --force --all}
$output=Join-Path $env:RUNNER_TEMP 'pdf-runtime'
$diagnostics=Join-Path $env:RUNNER_TEMP "lees-pdf-prepare-$target.log"
$elapsed=[Diagnostics.Stopwatch]::StartNew()
Write-Output 'Build stage: dependency-preparation'
$nativePreference=$PSNativeCommandUseErrorActionPreference
$PSNativeCommandUseErrorActionPreference=$false
try {
    if($IsWindows){
        & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'prepare-windows.ps1') -SourceRoot $source -OutputRoot $output *> $diagnostics
    }else{
        & npm --prefix $source ci --no-audit --no-fund *> $diagnostics
        if($LASTEXITCODE -eq 0){& bash (Join-Path $source 'scripts/release/prepare-macos.sh') *>> $diagnostics}
    }
    $commandExit=$LASTEXITCODE
}finally{
    $PSNativeCommandUseErrorActionPreference=$nativePreference
    $elapsed.Stop()
    Write-Output ('Build stage duration: dependency-preparation {0:F1}s' -f $elapsed.Elapsed.TotalSeconds)
}
if($commandExit -ne 0){
    if($env:LEESPDF_DIAGNOSTICS_PUBLIC_KEY){
        $encrypted=Join-Path $env:RUNNER_TEMP "lees-pdf-diagnostics-prepare-$target-$($env:GITHUB_RUN_ID).json"
        & node (Join-Path $PSScriptRoot 'encrypt-diagnostics.mjs') $diagnostics $encrypted
        if($LASTEXITCODE){throw 'Dependency diagnostic encryption failed'}
        & gh release upload $env:PUBLIC_TAG $encrypted --repo lyq2010/lee-releases --clobber
        if($LASTEXITCODE){throw 'Encrypted dependency diagnostic transfer failed'}
    }
    throw 'Dependency preparation failed; plaintext stays on the disposable runner'
}
$runtime=Join-Path $output 'runtime'
$indexFile=Join-Path $runtime 'files.sha256.json'
$index=Get-Content -LiteralPath $indexFile -Raw -Encoding UTF8 | ConvertFrom-Json
if($index.schemaVersion -ne 1 -or $index.target -ne $target){throw 'Prepared runtime target mismatch'}
. (Join-Path $PSScriptRoot 'runtime-inputs.ps1')
Assert-LeesPdfNativeSources $source $index
$index | Add-Member -NotePropertyName sourceRevision -NotePropertyValue $revision
$index | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $indexFile -Encoding utf8NoBOM
$jdk=if($IsWindows){Join-Path $runtime 'jdk'}else{Join-Path $source '.tools/release-sdk/jdk/Contents/Home'}
"JAVA_HOME=$jdk" | Out-File $env:GITHUB_ENV -Encoding utf8 -Append
"LEESPDF_RUNTIME_ROOT=$runtime" | Out-File $env:GITHUB_ENV -Encoding utf8 -Append
"LEESPDF_RUNTIME_INDEX_SHA256=$((Get-FileHash -LiteralPath $indexFile).Hash.ToLowerInvariant())" | Out-File $env:GITHUB_ENV -Encoding utf8 -Append
