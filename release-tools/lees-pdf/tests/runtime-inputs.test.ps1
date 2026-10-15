#Requires -Version 7.0
param([Parameter(Mandatory)][string]$FixtureRoot)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../runtime-inputs.ps1')
function Reject([scriptblock]$Action,[string]$Message){
    $rejected=$false
    try{& $Action}catch{$rejected=$true}
    if(!$rejected){throw $Message}
}
New-Item -ItemType Directory -Path $FixtureRoot | Out-Null
$file=Join-Path $FixtureRoot 'dependency.bin'
[IO.File]::WriteAllText($file,'fixed input')
$hash=(Get-FileHash -LiteralPath $file).Hash.ToLowerInvariant()
Get-LeesPdfPinnedInput 'https://example.invalid/fixed' $file $hash
[IO.File]::WriteAllText($file,'tampered input')
Reject {Get-LeesPdfPinnedInput 'https://example.invalid/fixed' $file $hash} 'Changed cached dependency was accepted'
Reject {Get-LeesPdfPinnedInput 'http://example.invalid/fixed' $file $hash} 'Unsecured dependency was accepted'
& git -C $FixtureRoot init --quiet
if($LASTEXITCODE){throw 'Fixture repository failed'}
$names=@('native/scan-worker/source.cpp','native/font-worker/source.cpp')
foreach($name in $names){
    $path=Join-Path $FixtureRoot $name
    New-Item -ItemType Directory -Path (Split-Path $path) -Force | Out-Null
    [IO.File]::WriteAllText($path,$name)
}
& git -C $FixtureRoot add -- native
if($LASTEXITCODE){throw 'Fixture index failed'}
$index=@{nativeSources=@($names | ForEach-Object {@{path=$_;sha256=(Get-FileHash -LiteralPath (Join-Path $FixtureRoot $_)).Hash.ToLowerInvariant()}})}
Assert-LeesPdfNativeSources $FixtureRoot $index
$missing=@{nativeSources=@($index.nativeSources[0])}
Reject {Assert-LeesPdfNativeSources $FixtureRoot $missing} 'Missing native source coverage was accepted'
$duplicate=@{nativeSources=@($index.nativeSources[0],$index.nativeSources[0])}
Reject {Assert-LeesPdfNativeSources $FixtureRoot $duplicate} 'Duplicate native source was accepted'
[IO.File]::WriteAllText((Join-Path $FixtureRoot $names[0]),'changed after compilation')
Reject {Assert-LeesPdfNativeSources $FixtureRoot $index} 'Changed compiler input was accepted'
Write-Output 'PASS: pinned input checksum, HTTPS, full native coverage, duplicates and changed compiler inputs'

$toolchain=Join-Path $FixtureRoot 'visual-studio'
$versionFile=Join-Path $toolchain 'VC/Auxiliary/Build/Microsoft.VCRedistVersion.default.txt'
New-Item -ItemType Directory -Path (Split-Path $versionFile) -Force | Out-Null
[IO.File]::WriteAllText($versionFile,'14.51.36231')
$crt=Join-Path $toolchain 'VC/Redist/MSVC/14.51.36231/x64/Microsoft.VC145.CRT'
New-Item -ItemType Directory -Path $crt -Force | Out-Null
Reject {Get-LeesPdfCrtDirectory $toolchain} 'Incomplete CRT directory was accepted'
foreach($name in @('msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','concrt140.dll')){[IO.File]::WriteAllText((Join-Path $crt $name),'fixture')}
if((Get-LeesPdfCrtDirectory $toolchain) -ne $crt){throw 'Versioned VC145 CRT was not selected'}
Copy-Item -LiteralPath $crt -Destination (Join-Path (Split-Path $crt) 'Microsoft.VC143.CRT') -Recurse
Reject {Get-LeesPdfCrtDirectory $toolchain} 'Ambiguous CRT directory was accepted'
Write-Output 'PASS: versioned CRT discovery accepts VC145 and rejects missing or ambiguous inputs'
