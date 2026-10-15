#Requires -Version 7.0
param([Parameter(Mandatory)][string]$SourceRoot,[Parameter(Mandatory)][string]$OutputRoot)
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$true
if(!$IsWindows){throw 'Windows dependency preparation requires Windows'}
$source=[IO.Path]::GetFullPath($SourceRoot)
. (Join-Path $PSScriptRoot 'runtime-inputs.ps1')
Push-Location $source
try {
    $sdk=Join-Path $source '.tools/release-sdk'
    $seed=Join-Path $sdk 'seed'
    New-Item -ItemType Directory -Path $seed | Out-Null
    $jdkArchive=Join-Path $sdk 'jdk.zip'
    Get-LeesPdfPinnedInput 'https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.4.1%2B1/OpenJDK25U-jdk_x64_windows_hotspot_25.0.4.1_1.zip' $jdkArchive '00c847d804f4a78e9f04f2683faf14fed898535b177b7fc704486cb0284e9283'
    $package=Join-Path $sdk 'jdk-package'
    Expand-Archive -LiteralPath $jdkArchive -DestinationPath $package
    $jdk=@(Get-ChildItem -LiteralPath $package -Directory)
    if($jdk.Count -ne 1){throw 'JDK archive layout mismatch'}
    Move-Item -LiteralPath $jdk[0].FullName -Destination (Join-Path $seed 'jdk')
    $env:JAVA_HOME=Join-Path $seed 'jdk'
    & (Join-Path $PSScriptRoot 'prepare-jdk.ps1')
    & python -m venv (Join-Path $sdk 'python')
    $python=Join-Path $sdk 'python/Scripts/python.exe'
    & $python -m pip install fonttools==4.60.2
    & $python scripts/release/prepare-assets.py
    & npm ci --no-audit --no-fund
    & pwsh -NoProfile -File scripts/prepare-qpdf-runtime.ps1 -Platform windows-x64
    Copy-Item -LiteralPath '.tools/qpdf-runtime' -Destination (Join-Path $seed 'qpdf') -Recurse
    $onnxRoot=Join-Path $source '.tools/ocr-sdk/onnxruntime'
    $onnxArchive=Join-Path $sdk 'onnxruntime.zip'
    Get-LeesPdfPinnedInput 'https://github.com/microsoft/onnxruntime/releases/download/v1.30.0/onnxruntime-win-x64-1.30.0.zip' $onnxArchive 'c6ba983baf5681af108599675d2a89c2d145512d02de28aed0bff177cd0ba949'
    Expand-Archive -LiteralPath $onnxArchive -DestinationPath $onnxRoot
    $clipper=Join-Path $source '.tools/ocr-sdk/clipper'
    Get-LeesPdfPinnedInput 'https://raw.githubusercontent.com/skyrpex/clipper/b1f1e1672745c1e1d73dd0437d1643f9633e7508/cpp/clipper.cpp' (Join-Path $clipper 'clipper.cpp') '5c642a3668311701f72572443aa42c1a981edb037298efc015166d9d90be0755'
    Get-LeesPdfPinnedInput 'https://raw.githubusercontent.com/skyrpex/clipper/b1f1e1672745c1e1d73dd0437d1643f9633e7508/cpp/clipper.hpp' (Join-Path $clipper 'clipper.hpp') '734eba9dc9d399089b2b467017074bd24728a1b9e64c7429e827806ed10e54cc'
    & pwsh -NoProfile -File scripts/prepare-scan-opencv.ps1
    & pwsh -NoProfile -File scripts/build-scan-worker.ps1
    & pwsh -NoProfile -File scripts/build-font-worker.ps1
    # The CRT comes from the installed compiler toolchain, never an unversioned download.
    $installation=& 'C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe' -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if(!$installation){throw 'Visual C++ toolchain is missing'}
    $redistVersion=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCRedistVersion.default.txt') -Raw).Trim()
    if($redistVersion -notmatch '^14\.\d+\.\d+$'){throw 'Unexpected compiler CRT version'}
    $redist=Join-Path $installation "VC/Redist/MSVC/$redistVersion/x64/Microsoft.VC143.CRT"
    $scan=Join-Path $source '.tools/scan-runtime'
    $font=Join-Path $source '.tools/font-runtime'
    New-Item -ItemType Directory -Path (Join-Path $scan 'licenses'),(Join-Path $font 'licenses') | Out-Null
    foreach($name in @('msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','concrt140.dll')){
        $file=Join-Path $redist $name
        $signature=Get-AuthenticodeSignature -LiteralPath $file
        if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation'){throw 'Compiler CRT signature mismatch'}
        Copy-Item -LiteralPath $file -Destination $scan
        Copy-Item -LiteralPath $file -Destination $font
    }
    foreach($name in @('lees-scan-worker.exe','opencv_world4130.dll','onnxruntime.dll','onnxruntime_providers_shared.dll')){Copy-Item -LiteralPath (Join-Path '.tools/ocr-native-build' $name) -Destination $scan}
    $opencv=Join-Path $source '.tools/ocr-sdk/opencv-minimal/install'
    Copy-Item -LiteralPath (Join-Path $opencv 'LICENSE') -Destination (Join-Path $scan 'licenses/OpenCV-Apache-2.0.txt')
    Copy-Item -LiteralPath (Join-Path $opencv 'etc/licenses') -Destination (Join-Path $scan 'licenses/opencv-third-party') -Recurse
    $onnx=Join-Path $onnxRoot 'onnxruntime-win-x64-1.30.0'
    Copy-Item -LiteralPath (Join-Path $onnx 'LICENSE') -Destination (Join-Path $scan 'licenses/ONNX-Runtime-MIT.txt')
    Copy-Item -LiteralPath (Join-Path $onnx 'ThirdPartyNotices.txt') -Destination (Join-Path $scan 'licenses/ONNX-Runtime-ThirdPartyNotices.txt')
    Get-ChildItem 'native/scan-worker/licenses' -File | Copy-Item -Destination (Join-Path $scan 'licenses')
    Copy-Item -LiteralPath 'native/scan-worker/NOTICE','native/scan-worker/reference/models.json' -Destination $scan
    foreach($name in @('det','rec')){Copy-Item -LiteralPath ".tools/ocr-models/$name/README.md" -Destination (Join-Path $scan "licenses/PP-OCRv5-$name-model-card.md")}
    Copy-Item -LiteralPath '.tools/font-native-build/lees-font-worker.exe','native/font-worker/NOTICE','native/font-worker/reference/dependency.json' -Destination $font
    Copy-Item -LiteralPath 'native/font-worker/licenses/HarfBuzz.txt' -Destination (Join-Path $font 'licenses')
    & $python scripts/release/freeze-runtime.py --target windows-x86_64 --seed $seed --output $OutputRoot
}finally{Pop-Location}
